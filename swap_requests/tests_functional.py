"""Browser-level Swap Request flows using Selenium and Django's live test server.

Run with: python manage.py test swap_requests.tests_functional
Selenium is optional when developing without Chrome: the class is skipped when
the package or a usable Chrome/Chromium installation is unavailable.
"""
import os
import unittest

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse

from accounts.models import UserProfile
from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap
from .models import SwapRequest

try:
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:
    webdriver = None


PASSWORD = 'SwapRequestTest123!'


def build_driver():
    options = webdriver.ChromeOptions()
    if os.getenv('SELENIUM_HEADLESS', '1') != '0':
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1400,1000')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    if os.getenv('SELENIUM_CHROME_BINARY'):
        options.binary_location = os.environ['SELENIUM_CHROME_BINARY']
    service = webdriver.ChromeService(executable_path=os.getenv('SELENIUM_CHROMEDRIVER') or None)
    return webdriver.Chrome(options=options, service=service)


@unittest.skipIf(webdriver is None, 'Selenium belum tersedia di environment ini.')
@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'])
class SwapRequestFunctionalTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.browser = build_driver()
        except WebDriverException as error:
            super().tearDownClass()
            message = getattr(error, 'msg', str(error))
            raise unittest.SkipTest(f'Chrome/Chromium tidak tersedia untuk Selenium: {message}')
        cls.browser.implicitly_wait(0)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    def setUp(self):
        self.owner = self.make_user('e2e-owner')
        self.requester = self.make_user('e2e-requester')
        self.outsider = self.make_user('e2e-outsider')
        self.wait = WebDriverWait(self.browser, 12)

    def tearDown(self):
        self.browser.delete_all_cookies()

    def make_user(self, username):
        user = User.objects.create_user(username, password=PASSWORD)
        UserProfile.for_user(user)
        return user

    def make_item(self, name, user, *, listed=False):
        item = ClothingItem.objects.create(
            user=user, name=name, category='top', size='M', gender='unisex',
            condition='good', color='neutral', is_listed_for_swap=listed,
        )
        if listed:
            ItemForSwap.objects.create(
                clothing_item=item, user=user, meeting_location='Depok',
                status=ItemForSwap.AVAILABLE,
            )
        return item

    def make_swap(self, wanted, offered, *, status=SwapRequest.PENDING):
        return SwapRequest.objects.create(
            requester=offered.user, owner=wanted.user,
            requested_item=wanted, offered_item=offered,
            requested_item_name=wanted.name, offered_item_name=offered.name,
            status=status,
        )

    def login(self, user):
        self.client.force_login(user)
        self.browser.get(self.live_server_url + reverse('accounts:login'))
        self.browser.add_cookie({
            'name': 'sessionid', 'value': self.client.cookies['sessionid'].value, 'path': '/',
        })

    def open(self, path):
        self.browser.get(self.live_server_url + path)

    def find(self, selector):
        return self.browser.find_element(By.CSS_SELECTOR, selector)

    def wait_for_text(self, selector, expected_text):
        """Re-query the node each poll; HTMX may replace it between polls."""
        def contains_text(driver):
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                return expected_text in element.text
            except StaleElementReferenceException:
                return False

        self.wait.until(contains_text)

    def wait_for_active(self, selector):
        def is_active(driver):
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                return 'is-active' in (element.get_attribute('class') or '').split()
            except StaleElementReferenceException:
                return False

        self.wait.until(is_active)

    def click(self, selector):
        element = self.find(selector)
        self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'})", element)
        element.click()

    def confirm_popup(self):
        dialog = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'dialog[open]')))
        dialog.find_element(By.CSS_SELECTOR, '[data-confirm-ok], [data-sr-confirm-accept]').click()

    def create_request_from_form(self, wanted, offered, message='Suka modelnya'):
        self.open(reverse('swap_requests:create') + f'?item={wanted.pk}')
        form = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form.sw-fmodal__panel')))
        Select(form.find_element(By.NAME, 'offered_item')).select_by_value(str(offered.pk))
        form.find_element(By.NAME, 'message').send_keys(message)
        form.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-modal-success]')))
        return SwapRequest.objects.get(requester=self.requester, requested_item=wanted)

    def submit_confirmation(self, swap, choice):
        form = self.wait_for_confirmation_form(swap)
        Select(form.find_element(By.NAME, 'choice')).select_by_value(choice)
        form.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        self.confirm_popup()

    def wait_for_confirmation_form(self, swap):
        """Wait for the server-rendered form after an optimistic HTMX status update."""
        selector = f'form[action="{reverse("swap_requests:confirm", args=[swap.pk])}"]'
        # visibility_of_element_located re-finds the element on every poll and
        # retries if HTMX replaces the panel while the response is being applied.
        return self.wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, selector)),
        )

    def test_open_page_switch_tabs_and_filter_status_without_full_page_navigation(self):
        wanted = self.make_item('Jaket untuk ditukar', self.owner, listed=True)
        offered = self.make_item('Kemeja penawar', self.requester)
        incoming_swap = self.make_swap(wanted, offered)
        outgoing_wanted = self.make_item('Jaket tujuan keluar', self.outsider, listed=True)
        outgoing_offer = self.make_item('Kemeja untuk ditukar', self.owner)
        outgoing_swap = self.make_swap(outgoing_wanted, outgoing_offer)
        self.login(self.owner)
        self.open(reverse('swap_requests:index'))
        self.wait.until(EC.visibility_of_element_located((By.ID, 'sr-index-content')))
        self.wait.until(lambda driver: driver.execute_script('return Boolean(window.htmx)'))
        self.browser.execute_script('window.__swapRequestNoReload = true')

        self.click('.sr-tab[href="?tab=kamu"]')
        self.wait_for_active('.sr-tab[href="?tab=kamu"]')
        self.wait_for_text('#sr-index-content', outgoing_swap.code)
        self.click('.sr-filter[href="?tab=kamu&status=pending"]')
        self.wait_for_active('.sr-filter[href="?tab=kamu&status=pending"]')
        self.wait_for_text('#sr-index-content', outgoing_swap.code)
        self.assertTrue(self.browser.execute_script('return window.__swapRequestNoReload === true'))

        self.click('.sr-tab[href="?tab=masuk"]')
        self.wait_for_active('.sr-tab[href="?tab=masuk"]')
        self.wait_for_text('#sr-index-content .sr-row__title', wanted.name)
        self.wait_for_text('#sr-index-content .sr-row__count', '1 request masuk')

        # The incoming tab groups requests by clothing item. Individual SR codes
        # live in the folder detail, not in the visible group card (its per-request
        # selection list is hidden until bulk-select mode is opened).
        self.click('#sr-index-content .sr-row a.sr-btn-all')
        self.wait.until(EC.visibility_of_element_located((By.ID, 'sr-item-list-content')))
        self.wait_for_text('#sr-item-list-content .sr-row__meta', incoming_swap.code)

    def test_user_submits_request_then_both_parties_complete_the_swap(self):
        wanted = self.make_item('Cardigan e2e', self.owner, listed=True)
        offered = self.make_item('Kemeja e2e', self.requester)
        self.login(self.requester)
        swap = self.create_request_from_form(wanted, offered)
        self.assertEqual(swap.status, SwapRequest.PENDING)
        self.assertIn('Request kamu sudah terkirim', self.find('[data-modal-success]').text)

        self.login(self.owner)
        self.open(reverse('swap_requests:detail', args=[swap.pk]))
        self.click(f'form[action="{reverse("swap_requests:respond", args=[swap.pk])}"] button[value="accept"]')
        self.confirm_popup()
        self.wait_for_text('#sr-detail-state', 'Awaiting exchange')
        # The badge can change optimistically before HTMX returns the panel
        # containing the confirmation form. Wait for that server-rendered form
        # before asserting the persisted status or interacting with it.
        self.wait_for_confirmation_form(swap)
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)

        self.submit_confirmation(swap, SwapRequest.DONE)
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)

        self.login(self.requester)
        self.open(reverse('swap_requests:detail', args=[swap.pk]))
        self.submit_confirmation(swap, SwapRequest.DONE)
        self.wait.until(lambda driver: 'Completed' in self.find('#sr-detail-state').text)
        swap.refresh_from_db()
        wanted.refresh_from_db()
        offered.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.COMPLETED)
        self.assertEqual(wanted.user, self.requester)
        self.assertEqual(offered.user, self.owner)

    def test_owner_rejects_request_and_requester_can_delete_it(self):
        wanted = self.make_item('Cardigan ditolak', self.owner, listed=True)
        offered = self.make_item('Kemeja ditawarkan', self.requester)
        swap = self.make_swap(wanted, offered)
        self.login(self.owner)
        self.open(reverse('swap_requests:detail', args=[swap.pk]))
        self.click(f'form[action="{reverse("swap_requests:respond", args=[swap.pk])}"] button[value="reject"]')
        self.confirm_popup()
        self.wait_for_text('#sr-detail-state', 'Rejected')
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.REJECTED)

        self.login(self.requester)
        self.open(reverse('swap_requests:detail', args=[swap.pk]))
        self.click(f'form[action="{reverse("swap_requests:delete", args=[swap.pk])}"] button[type="submit"]')
        self.confirm_popup()
        self.wait_for_text('#sr-detail-root', 'Aksi sudah diproses')
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.REJECTED)
        self.assertTrue(swap.requester_hidden)
        self.assertFalse(swap.owner_hidden)

    def test_bulk_delete_selects_multiple_requests_and_waits_for_modal_confirmation(self):
        wanted = self.make_item('Jaket bulk', self.owner, listed=True)
        first_offer = self.make_item('Atasan bulk A', self.requester)
        second_offer = self.make_item('Atasan bulk B', self.requester)
        first = self.make_swap(wanted, first_offer)
        second = self.make_swap(wanted, second_offer)
        self.login(self.requester)
        self.open(reverse('swap_requests:index') + '?tab=kamu')
        self.wait.until(EC.presence_of_element_located((By.ID, 'sr-index-content')))
        self.click('[data-sr-selection-toggle]')
        for swap in (first, second):
            self.click(f'[data-sr-bulk-checkbox][value="{swap.pk}"]')
        self.assertEqual(self.find('[data-sr-selected-count]').text, '2 dipilih')
        self.click('[data-sr-bulk-submit]')
        dialog = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-sr-bulk-dialog][open]')))
        self.assertIn('2 request', dialog.text)
        self.assertTrue(SwapRequest.objects.filter(pk=first.pk).exists(), 'Data berubah sebelum konfirmasi.')
        dialog.find_element(By.CSS_SELECTOR, '[data-sr-confirm-accept]').click()
        # Database updates can finish before HTMX swaps the response into the page.
        # Wait for the server-rendered empty state, re-querying in case HTMX replaces it.
        self.wait_for_text('#sr-index-content .sr-empty__title', 'Belum ada request')
        self.assertFalse(SwapRequest.objects.filter(pk=first.pk).exists())
        self.assertFalse(SwapRequest.objects.filter(pk=second.pk).exists())

