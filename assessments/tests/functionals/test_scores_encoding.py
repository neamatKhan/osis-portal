import time

import pyvirtualdisplay
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.urlresolvers import reverse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from base.tests.factories.person import PersonRandomGlobalIdFactory
from base.tests.factories.user import UserFactory, SuperUserFactory

SIZE = (1280, 1280)


class BusinessMixin:
    def create_user(self):
        return UserFactory()

    def create_super_user(self):
        return SuperUserFactory()


class SeleniumTestCase(StaticLiveServerTestCase):
    def setUp(self):
        self.display = pyvirtualdisplay.Display(visible=0, size=SIZE)
        self.display.start()

        self.driver = webdriver.Chrome()
        self.driver.set_window_size(*SIZE)

    def tearDown(self):
        self.driver.quit()
        self.display.stop()

    def get_url_by_name(self, url_name, *args, **kwargs):
        url = '{}{}'.format(self.live_server_url, reverse(url_name, args=args, kwargs=kwargs))
        return url

    def goto(self, url_name, *args, **kwargs):
        url = self.get_url_by_name(url_name, *args, **kwargs)
        self.driver.get(url)

    def fill_by_id(self, field_id, value):
        field = self.driver.find_element_by_id(field_id)
        field.clear()
        field.send_keys(value)

    def login(self, username, password='password123'):
        self.goto('login')
        self.fill_by_id('id_username', username)
        self.fill_by_id('id_password', password)
        self.click_on('post_login_btn')

    def click_on(self, id_):
        self.driver.find_element_by_id(id_).click()


class Scenario2FunctionalTest(SeleniumTestCase, BusinessMixin):
    def test(self):
        user = self.create_user()

        perm = Permission.objects.get(codename="is_tutor")
        user.user_permissions.add(perm)

        person = PersonRandomGlobalIdFactory(user=user)

        self.login(user.username)
        self.goto('home')

        self.click_on('lnk_score_encoding')
        self.click_on('lnk_scores_download')
        self.click_on('lnk_ask_papersheet')

        WebDriverWait(self.driver, 2).until(
            EC.text_to_be_present_in_element(
                (By.ID, 'status_message'),
                'scores_sheet_loading'
            )
        )

        WebDriverWait(self.driver, 2).until(
            EC.text_to_be_present_in_element(
                (By.ID, 'status_message'),
                'Les feuilles de notes ne sont pas disponibles'
            )
        )
