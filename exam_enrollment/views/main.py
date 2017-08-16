##############################################################################
#
#    OSIS stands for Open Student Information System. It's an application
#    designed to manage the core business of higher education institutions,
#    such as universities, faculties, institutes and professional schools.
#    The core business involves the administration of students, teachers,
#    courses, programs and so on.
#
#    Copyright (C) 2015-2017 Université catholique de Louvain (http://www.uclouvain.be)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    A copy of this license - GNU General Public License - is available
#    at the root of the source code of this program.  If not,
#    see http://www.gnu.org/licenses/.
#
##############################################################################
import json

from django.core.exceptions import MultipleObjectsReturned
import warnings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _
from django.http import response
from django.conf import settings

from base.views import layout
from base.models import student, offer_enrollment, academic_year, offer_year, learning_unit_enrollment
from exam_enrollment.models import exam_enrollment_submitted
from frontoffice.queue import queue_listener
from osis_common.queue import queue_sender
from dashboard.views import main as dash_main_view
from django.views.decorators.http import require_http_methods
import pika
import pika.exceptions
import traceback
from django.http import HttpResponse
from frontoffice.queue.queue_listener import ExamEnrollmentFormResponseClient
import datetime
from voluptuous import Schema, Any, Required, error as voluptuous_error
import logging


logger = logging.getLogger(settings.DEFAULT_LOGGER)
queue_exception_logger = logging.getLogger(settings.QUEUE_EXCEPTION_LOGGER)


@login_required
@permission_required('base.is_student', raise_exception=True)
def choose_offer(request):
    return navigation(request, False)


@login_required
@permission_required('base.is_student', raise_exception=True)
def choose_offer_direct(request):
    return navigation(request, True)


def navigation(request, navigate_direct_to_form):
    try:
        stud = student.find_by_user(request.user)
    except MultipleObjectsReturned:
        return dash_main_view.show_multiple_registration_id_error(request)
    student_programs = _get_student_programs(stud)
    if student_programs:
        if navigate_direct_to_form and len(student_programs) == 1:
            return _get_exam_enrollment_form(student_programs[0], request, stud)
        else:
            return layout.render(request, 'offer_choice.html', {'programs': student_programs,
                                                                'student': stud})
    else:
        messages.add_message(request, messages.WARNING, _('no_offer_enrollment_found'))
        return response.HttpResponseRedirect(reverse('dashboard_home'))


@login_required
@permission_required('base.is_student', raise_exception=True)
def exam_enrollment_form(request, offer_year_id):
    try:
        stud = student.find_by_user(request.user)
    except MultipleObjectsReturned:
        return dash_main_view.show_multiple_registration_id_error(request)
    off_year = offer_year.find_by_id(offer_year_id)
    if request.method == 'POST':
        return _process_exam_enrollment_form_submission(off_year, request, stud)
    else:
        return _get_exam_enrollment_form(off_year, request, stud)


def _get_exam_enrollment_form(off_year, request, stud):
    learn_unit_enrols = learning_unit_enrollment.find_by_student_and_offer_year(stud, off_year)
    if not learn_unit_enrols:
        messages.add_message(request, messages.WARNING, _('no_learning_unit_enrollment_found').format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    data = _fetch_exam_enrollment_form(stud, off_year, get_student_offer_enrollment(stud))

    if not data:
        messages.add_message(request, messages.WARNING, _('exam_enrollment_form_unavalaible_for_the_moment').format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    elif data.get('error_message'):
        messages.add_message(request, messages.WARNING, _(data.get('error_message')).format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    return layout.render(request, 'exam_enrollment_form.html', {'exam_enrollments': data.get('exam_enrollments'),
                                                                'student': stud,
                                                                'current_number_session': data.get('current_number_session'),
                                                                'academic_year': academic_year.current_academic_year(),
                                                                'program': offer_year.find_by_id(off_year.id)})


def _process_exam_enrollment_form_submission(off_year, request, stud):
    data_to_submit = _exam_enrollment_form_submission_message(off_year, request, stud)
    json_data = json.dumps(data_to_submit)
    offer_enrol = offer_enrollment.find_by_student_offer(stud, off_year)
    if json_data and offer_enrol:
        exam_enrollment_submitted.insert_or_update_document(offer_enrol, json_data)
    queue_sender.send_message(settings.QUEUES.get('QUEUES_NAME').get('EXAM_ENROLLMENT_FORM_SUBMISSION'), data_to_submit)
    messages.add_message(request, messages.SUCCESS, _('exam_enrollment_form_submitted'))
    return response.HttpResponseRedirect(reverse('dashboard_home'))


def _exam_enrollment_form_submission_message(off_year, request, stud):
    return {
        'registration_id': stud.registration_id,
        'offer_year_acronym': off_year.acronym,
        'year': off_year.academic_year.year,
        'exam_enrollments': _build_enrollments_by_learning_unit(request)
    }


def _build_enrollments_by_learning_unit(request):
    warnings.warn(
        "The field named 'etat_to_inscr' is only used to call EPC services. It should be deleted when the exam "
        "enrollment business will be implemented in Osis (not in EPC anymore). "
        "The flag 'is_enrolled' should be sufficient for Osis."
        "Do not forget to delete the hidden input field in the html template.",
        DeprecationWarning
    )
    current_number_session = request.POST['current_number_session']
    enrollments_by_learn_unit = []
    is_enrolled_by_acronym = _build_dicts_is_enrolled_by_acronym(current_number_session, request)
    etat_to_inscr_by_acronym = _build_dicts_etat_to_inscr_by_acronym(request)
    for acronym, etat_to_inscr in etat_to_inscr_by_acronym.items():
        etat_to_inscr = None if not etat_to_inscr or etat_to_inscr == 'None' else etat_to_inscr
        if etat_to_inscr:
            enrollments_by_learn_unit.append({
                'acronym': acronym,
                'is_enrolled': is_enrolled_by_acronym.get(acronym, False),
                'etat_to_inscr': etat_to_inscr
            })
    return enrollments_by_learn_unit


def _build_dicts_etat_to_inscr_by_acronym(request):
    return {_extract_acronym(html_tag_id): etat_to_inscr for html_tag_id, etat_to_inscr in request.POST.items()
            if "etat_to_inscr_current_session_" in html_tag_id}


def _build_dicts_is_enrolled_by_acronym(current_number_session, request):
    return {_extract_acronym(html_tag_id): True if value == "on" else False
            for html_tag_id, value in request.POST.items()
            if "chckbox_exam_enrol_sess{}_".format(current_number_session) in html_tag_id}


def _extract_acronym(html_tag_id):
    return html_tag_id.split("_")[-1]


def _fetch_exam_enrollment_form(stud, offer_yr, offer_enrollment):
    json_data = call_exam_enrollment_client(offer_yr, stud, offer_enrollment)
    if json_data:
        json_data = json_data.decode("utf-8")
        return json.loads(json_data)
    return None


def _exam_enrollment_form_message(registration_id, offer_year_acronym, year, offer_enrollment):
    return {
        'registration_id': registration_id,
        'offer_year_acronym': offer_year_acronym,
        'year': year,
        'offer_enrollment_id': offer_enrollment.id
    }


def _get_student_programs(stud):
    if stud:
        return [enrol.offer_year for enrol in list(
            offer_enrollment.find_by_student_academic_year(stud, academic_year.current_academic_year()))]
    return None


def call_exam_enrollment_client(offer_yr, stud, offer_enrollment):
    if hasattr(settings, 'QUEUES') and settings.QUEUES:
        exam_enrol_client = queue_listener.ExamEnrollmentClient()
        message = _exam_enrollment_form_message(stud.registration_id, offer_yr.acronym, offer_yr.academic_year.year, offer_enrollment)
        return exam_enrol_client.call(json.dumps(message))
    return None


def update_document_from_queue(body):
    json_data = body.decode("utf-8")
    data = json.loads(json_data)

    offer_enrollment_id = data.get('offer_enrollment_id')

    offer_enrol = offer_enrollment.find_by_id(offer_enrollment_id)

    if offer_enrol:
        exam_enrollment_submitted.insert_or_update_document(offer_enrol, json_data)


@login_required
@permission_required('base.is_student', raise_exception=True)
@require_http_methods(["POST"])
def ask_exam_enrollment(request):
    try:
        stud = student.find_by_user(request.user)
    except MultipleObjectsReturned:
        return dash_main_view.show_multiple_registration_id_error(request)
    offer_enrollment = get_student_offer_enrollment(stud)
    offer_yr = offer_enrollment.offer_year

    message = _exam_enrollment_form_message(stud.registration_id,
                                            offer_yr.acronym,
                                            offer_yr.academic_year.year,
                                            offer_enrollment)
    json_data = json.dumps(message)

    if request.is_ajax():
        if hasattr(settings, 'QUEUES') and settings.QUEUES:
            try:
                connect = pika.BlockingConnection(_get_rabbit_settings())
                queue_name = settings.QUEUES.get('QUEUES_NAME').get('EXAM_ENROLLMENT_FORM_REQUEST')
                channel = _create_channel(connect, queue_name)
                message_published = channel.basic_publish(exchange='',
                                                          routing_key=queue_name,
                                                          body=json_data)
                connect.close()
            except (RuntimeError, pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed,
                    pika.exceptions.AMQPError):
                return HttpResponse(status=400)

            if message_published:
                return HttpResponse(status=200)

    return HttpResponse(status=405)


@login_required
@permission_required('base.is_student', raise_exception=True)
@require_http_methods(["POST"])
def check_exam_enrollment(request):
    if request.is_ajax() and 'exam_enrollment' in settings.INSTALLED_APPS:
        stud = student.find_by_user(request.user)

        if _check_exam_enrollment_in_db(stud):
            enrollments_in_db_and_uptodate = _check_exam_enrollment_error(stud)
            return HttpResponse(status=200, content='your conent here')
        else:
            return HttpResponse(status=404)
    else:
        return HttpResponse(status=405)


def _create_channel(connect, queue_name):
    channel = connect.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    return channel


def _get_rabbit_settings():
    credentials = pika.PlainCredentials(settings.QUEUES.get('QUEUE_USER'),
                                        settings.QUEUES.get('QUEUE_PASSWORD'))
    rabbit_settings = pika.ConnectionParameters(settings.QUEUES.get('QUEUE_URL'),
                                                settings.QUEUES.get('QUEUE_PORT'),
                                                settings.QUEUES.get('QUEUE_CONTEXT_ROOT'),
                                                credentials)
    return rabbit_settings


def _check_exam_enrollment_in_db(stud):
    if stud:
        enrollments_in_db_and_uptodate = check_db_document(stud)
    else:
        enrollments_in_db_and_uptodate = False
        logger.warning("A person doesn't exist for the user {0}".format(stud.person.user))
    return enrollments_in_db_and_uptodate


def fetch_json_exam_enrollment(message):
    attestation_statuses = None
    if hasattr(settings, 'QUEUES') and settings.QUEUES and message:
        try:
            client = ExamEnrollmentFormResponseClient()
            json_data = client.call(message)
            if json_data:
                attestation_statuses = json.loads(json_data.decode("utf-8"))
        except Exception as e:
            logger.error('Error fetching student attestation statuses.\nmessage sent :  {}'.format(str(message)))
    return attestation_statuses


def get_student_offer_enrollment(stud):
    if stud:
        return offer_enrollment.find_by_student_academic_year(stud, academic_year.current_academic_year()).first()
    return None


def check_db_document(stud):
    if stud:
        oe = get_student_offer_enrollment(stud)
        exam_enrollment_sub = exam_enrollment_submitted.find_by_offer_enrollment(oe).first()
        if exam_enrollment_sub and exam_enrollment_sub.document and (_is_outdated(exam_enrollment_sub.document) or _is_in_error(exam_enrollment_sub.document)):
            exam_enrollment_sub.delete()
            return False

        if exam_enrollment_sub and exam_enrollment_sub.document and not _is_outdated(exam_enrollment_sub.document):

            try:
                validate_data_structure(json.loads(exam_enrollment_sub.document))
                return True
            except (KeyError, voluptuous_error.Invalid):
                trace = traceback.format_exc()
                logger.error(trace)
                logger.warning(
                    "A document could not be produced from the json document of the student registration id {0}".format(stud.registration_id))
                return False
        else:
            return False


def get_data_schema():
    return Schema({
        Required("error_message", default=''): Any(None, str),
        Required("registration_id"): str,
        Required("offer_enrollment_id"): str,
    }, extra=True)


def validate_data_structure(data):
    s = get_data_schema()
    return s(data)


def _check_exam_enrollment_error(stud):
    if stud:
        enrollments_in_db_and_uptodate = check_db_document(stud)
    else:
        enrollments_in_db_and_uptodate = False
        logger.warning("A person doesn't exist for the user {0}".format(stud.person.user))
    return enrollments_in_db_and_uptodate


def is_in_error(document):
    json_document = json.loads(document)
    if json_document.get('error_message', None):
        return True
    return False


def _get_exam_enrollment_form(off_year, request, stud):
    learn_unit_enrols = learning_unit_enrollment.find_by_student_and_offer_year(stud, off_year)
    if not learn_unit_enrols:
        messages.add_message(request, messages.WARNING, _('no_learning_unit_enrollment_found').format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    data = _fetch_exam_enrollment_form(stud, off_year, get_student_offer_enrollment(stud))
    if not data:
        messages.add_message(request, messages.WARNING, _('exam_enrollment_form_unavalaible_for_the_moment').format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    elif data.get('error_message'):
        messages.add_message(request, messages.WARNING, _(data.get('error_message')).format(off_year.acronym))
        return response.HttpResponseRedirect(reverse('dashboard_home'))
    return layout.render(request, 'exam_enrollment_form.html', {'exam_enrollments': data.get('exam_enrollments'),
                                                                'student': stud,
                                                                'current_number_session': data.get('current_number_session'),
                                                                'academic_year': academic_year.current_academic_year(),
                                                                'program': offer_year.find_by_id(off_year.id)})


def view_exam_enrollment(request):
    stud = student.find_by_user(request.user)
    oe = get_student_offer_enrollment(stud)
    json_document = exam_enrollment_submitted.find_by_offer_enrollment(oe).first()

    data = json.loads(json_document.document)
    off_year = oe.offer_year

    error_message = data.get('error_message')

    return layout.render_to_response(request, 'exam_enrollment_form.html',
                                     {'exam_enrollments': data.get('exam_enrollments'),
                                      'error_message': error_message,
                                      'student': stud,
                                      'current_number_session': data.get('current_number_session'),
                                      'academic_year': academic_year.current_academic_year(),
                                      'program': offer_year.find_by_id(off_year.id)})


def _is_outdated(document):
    json_document = json.loads(document)
    now = datetime.datetime.now()
    now_str = '%s/%s/%s' % (now.day, now.month, now.year)
    if json_document.get('publication_date', None) != now_str:
        return True
    return False


def _is_in_error(document):
    json_document = json.loads(document)
    if json_document.get('error_message', None):
        return True
    return False