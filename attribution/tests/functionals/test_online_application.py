from random import randint, random

import factory
import pendulum
from django.contrib.auth.models import Group, Permission
import pyvirtualdisplay

from django.core.urlresolvers import reverse

from attribution.models.attribution import Attribution
from attribution.tests.factories.attribution import AttributionFactory
from attribution.utils import permission
from base.models.enums import academic_calendar_type, learning_unit_year_subtypes, vacant_declaration_type, \
    learning_component_year_type, component_type
from base.tests.factories.academic_calendar import AcademicCalendarFactory
from base.tests.factories.academic_year import AcademicYearFactory
from base.tests.factories.learning_component_year import LearningComponentYearFactory
from base.tests.factories.learning_container_year import LearningContainerYearFactory
from base.tests.factories.learning_unit import LearningUnitFactory
from base.tests.factories.learning_unit_component import LearningUnitComponentFactory
from base.tests.factories.learning_unit_year import LearningUnitYearFactory
from base.tests.factories.person import PersonFactory
from base.tests.factories.tutor import TutorFactory
from base.tests.factories.user import UserFactory, SuperUserFactory
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from urllib import request

from selenium import webdriver

CNUM_MIN=1000


class BusinessMixin:
    #crée un utilisateur avec Faker comme générateur de valeurs + passwd123
    def create_user(self):
        user = UserFactory()
        print("User {} / {} {} created".format(user.username, user.first_name, user.last_name))
        return user
    #spécifie l'utilisateur est "super user"
    def create_super_user(self):
        superUser = SuperUserFactory()
        print("User {} {} created".format(superUser.username, superUser.last_name))
        return superUser

    #ajouter l'utilisateur dans une ou plusieurs groupes
    def add_group(self, user, *group_names):
        for name in group_names:
            group, created = Group.objects.get_or_create(name=name)
            group.user_set.add(user)

    def create_tutor(self, user):
        person = PersonFactory(user=user, language='fr-be')
        return TutorFactory(person=person)


    def create_learning_units(self,academic_year,cnum):
        #learning_unit_year = LearningUnitYearFactory(academic_year=academic_year)
        learning_unit = LearningUnitFactory(acronym="LBIOL{}".format(cnum))
        learning_unit_year = LearningUnitYearFactory(academic_year=academic_year,learning_unit=learning_unit)
        print("learning_unit created {} {}".format(learning_unit_year.learning_unit.acronym, learning_unit_year.learning_unit.title, ))
        return learning_unit_year


    #creer l'unité d'enseignement et l'attribuer
    def create_attribution(self,learning_unit_year,tutor):
        AttributionFactory(tutor=tutor, learning_unit_year=learning_unit_year)
        return learning_unit_year

    #donner à l'utilisateur une ou plusieurs permissions.
    #une permission est composée par le label et le code
    def add_permission(self, user, permission):
        #content_type = ContentType.objects.get_for_model(Attribution)
        #for permission in permissions:
            #if '.' in permission:
        label, codename = permission.split('.')
            #    print("{} {}".format(label, codename))


        permission = Permission.objects.get(codename=codename, content_type__app_label=label)
            #else:
            #    permission = Permission.objects.get(codename=permission)
        user.user_permissions.add(permission)

    def create_tutor_with_permission(self,user,permission):
        #self.add_permission(user,*permission_list)
        self.add_permission(user,permission)
        turor = self.create_tutor(user)
        print("Permission given to tutor {}, {} {} {}'".format(turor.external_id, user.last_name, user.username, user.first_name))
        return turor



SIZE =(1920, 1080)
# url = 'http://localhost:8000'
class SeleniumTest_On_Line_Application(StaticLiveServerTestCase, BusinessMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.display = pyvirtualdisplay.Display(size=SIZE) #crée un virtuel display
        #cls.display = Xvfb()
        # cls.display.start()
        options = webdriver.ChromeOptions()
        cls.driver = webdriver.Chrome(chrome_options=options)
        cls.driver.implicitly_wait(10)
        cls.driver.set_window_size(*SIZE)


    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        # cls.display.stop()
        super().tearDownClass()

        # retourne l'url de la page
    def get_url_by_name(self, url_name, *args, **kwargs):
       return request.urljoin(self.live_server_url,
                              reverse(url_name, args=args, kwargs=kwargs))

        # permet d'aller sur une vue django
    def goto(self, url_name, *args, **kwargs):
        url = self.get_url_by_name(url_name, *args, **kwargs)
        self.driver.get(url)

    def fill_by_id(self,element_id, value):
        element = self.driver.find_element_by_id(element_id)
        element.clear()
        element.send_keys(value)

    def click_on(self,element_id):
        element = self.driver.find_element_by_id(element_id)
        element.click()

    def login(self, username, password='password123'):
        self.fill_by_id('id_username', username)
        self.fill_by_id('id_password', password)
        self.click_on('post_login_btn')

    def open_browser_and_log_on_user(self,url, user):
        url = self.goto(url)
        self.login(user.username)
        # import pdb; pdb.set_trace()
        #assert 'OSIS' in self.driver.title

    def link_components_and_learning_unit_year_to_container(self,l_container, acronym,
                                                             volume_lecturing=None,
                                                             volume_practical_exercices=None,
                                                             subtype=learning_unit_year_subtypes.FULL):
        a_learning_unit_year = LearningUnitYearFactory(acronym=acronym, academic_year=l_container.academic_year,
                                                       specific_title=l_container.common_title, subtype=subtype)
        if volume_lecturing:
            a_component = LearningComponentYearFactory(
                learning_container_year=l_container,
                type=learning_component_year_type.LECTURING,
                volume_declared_vacant=volume_lecturing
            )
            LearningUnitComponentFactory(learning_unit_year=a_learning_unit_year, learning_component_year=a_component,
                                         type=component_type.LECTURING)
        if volume_practical_exercices:
            a_component = LearningComponentYearFactory(
                learning_container_year=l_container,
                type=learning_component_year_type.PRACTICAL_EXERCISES,
                volume_declared_vacant=volume_practical_exercices
            )
            LearningUnitComponentFactory(learning_unit_year=a_learning_unit_year, learning_component_year=a_component,
                                         type=component_type.PRACTICAL_EXERCISES)
        return a_learning_unit_year

    def create_learning_container(self,acronym, academic_year,type_declaration_vacant=vacant_declaration_type.RESEVED_FOR_INTERNS):

        l_container = LearningContainerYearFactory(acronym=acronym, academic_year=academic_year,
                                                   type_declaration_vacant=type_declaration_vacant)
        return l_container



    def test_01(self):
        user = self.create_user()

        groupe_list = []

        group = Group.objects.get_or_create(name='tutors')
        groupe_list.append(group)

        group = Group.objects.get_or_create(name='authorisations_manager')
        groupe_list.append(group)

        group, created = Group.objects.get_or_create(name='administrators')
        groupe_list.append(group)

        self.add_group(user, *groupe_list)
        permission ='attribution.can_access_attribution_application'

        tutor = self.create_tutor_with_permission(user,permission)

        # Create current academic year
        current_academic_year = AcademicYearFactory(year=pendulum.today().year - 1)
        # Create application year
        next_academic_year = AcademicYearFactory(year=pendulum.today().year + 1)

        # Create Event to allow teacher to register
        #start_date = pendulum.today() - pendulum.timedelta(days=10)
        #end_date = pendulum.today() + pendulum.timedelta(days=15)

        academic_calendar = AcademicCalendarFactory(academic_year=current_academic_year,
                                                    reference=academic_calendar_type.TEACHING_CHARGE_APPLICATION)
        #                                            start_date = start_date, end_date = end_date)


       # print("Annee academique : {} {}".format(academic_calendar.start_date, academic_calendar.end_date))

        # tutor = self.create_tutor_with_permission(user, permission)
        #
        learning_unit_list =[]
        cnum = CNUM_MIN
        for counter in range(1, 10):
            cnum = cnum+1
            acronym = "LBIOL{}".format(cnum)
            l_container_current = self.create_learning_container (acronym, current_academic_year)

            volume_lecturing = None
            volume_practical_exercices = None
            subtype = learning_unit_year_subtypes.FULL

            learning_unit_year_current = self.link_components_and_learning_unit_year_to_container(l_container_current,
                                                                                                  acronym,
                                                                                                  volume_lecturing,
                                                                                                  volume_practical_exercices,
                                                                                                  subtype)
            #learning_unit_year = self.create_learning_units(academic_year,cnum)

            volume_lecturing = 70
            volume_practical_exercices = 70

            type_declaration_vacant = vacant_declaration_type.DO_NOT_ASSIGN
            l_container_year_next = self.create_learning_container(acronym, next_academic_year,type_declaration_vacant)

            learning_unit_year_next = self.link_components_and_learning_unit_year_to_container(l_container_year_next,
                                                                                                acronym,
                                                                                                volume_lecturing,
                                                                                                volume_practical_exercices,
                                                                                                subtype)
            if (counter % 2 == 0):
                self.create_attribution(learning_unit_year_current, tutor)
                print("attribution {}".format(counter))
            print("attribution OK")
            learning_unit_list.append(learning_unit_year_current.acronym)
        self.open_browser_and_log_on_user('login', user)
        print("connected to : {}".format(self.driver.current_url))
        self.goto('applications_overview')
        self.click_on("lnk_submit_attribution_new")
        acronym_test = learning_unit_list[3]
        print("{}".format(acronym_test))
        self.fill_by_id("id_learning_container_acronym",acronym_test)
        self.click_on("bt_submit_vacant_attributions_search")
        self.driver.implicitly_wait(15)




