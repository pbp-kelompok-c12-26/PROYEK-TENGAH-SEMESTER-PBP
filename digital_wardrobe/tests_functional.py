"""
Functional test (end-to-end) Lemari Saya dengan Selenium: browser Chrome sungguhan membuka
server test Django lalu menjalankan alur seperti pengguna (klik, ketik, upload, konfirmasi).

Menjalankan:
    pip install -r requirements-dev.txt          # memasang selenium
    python manage.py test digital_wardrobe.tests_functional

Pengaturan lewat environment variable (opsional):
    SELENIUM_HEADLESS=0          tampilkan jendela Chrome (bagus untuk demo); default tanpa jendela
    SELENIUM_CHROME_BINARY=...   lokasi Chrome/Chromium kalau tidak di tempat standar
    SELENIUM_CHROMEDRIVER=...    lokasi chromedriver (default: diunduh otomatis oleh Selenium Manager)

Kalau Selenium atau Chrome tidak ada (mis. di PWS / laptop tanpa requirements-dev), test ini
otomatis dilewati (skipped), jadi `python manage.py test` tetap lolos.
"""
import os
import shutil
import tempfile
import unittest

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from .models import ClothingItem, Outfit

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:   # selenium belum dipasang
    webdriver = None

TEMP_MEDIA = tempfile.mkdtemp()
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'wardrobe-e2e'}}
PASSWORD = 'Password123!'


def build_driver():
    options = webdriver.ChromeOptions()
    if os.getenv('SELENIUM_HEADLESS', '1') != '0':
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1400,900')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    if os.getenv('SELENIUM_CHROME_BINARY'):
        options.binary_location = os.environ['SELENIUM_CHROME_BINARY']
    service = webdriver.ChromeService(executable_path=os.getenv('SELENIUM_CHROMEDRIVER') or None)
    return webdriver.Chrome(options=options, service=service)


@unittest.skipIf(webdriver is None, 'Selenium belum terpasang: pip install -r requirements-dev.txt')
@override_settings(CACHES=LOCMEM_CACHE, MEDIA_ROOT=TEMP_MEDIA)
class WardrobeFunctionalTests(StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            cls.browser = build_driver()
        except WebDriverException as error:   # Chrome tidak ditemukan / tidak bisa dijalankan
            super().tearDownClass()
            raise unittest.SkipTest(f'Chrome untuk Selenium tidak tersedia: {error.msg}')
        cls.browser.implicitly_wait(0)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('fanny', password=PASSWORD)
        self.other = User.objects.create_user('rico', password=PASSWORD)
        self.wait = WebDriverWait(self.browser, 10)

    def tearDown(self):
        self.browser.delete_all_cookies()

    # ---------- bantuan ----------
    def make_item(self, name, user=None, **extra):
        fields = {'category': 'top', 'size': 'M', 'color': 'neutral', 'condition': 'good', 'gender': 'unisex', **extra}
        return ClothingItem.objects.create(user=user or self.user, name=name, **fields)

    def open(self, path):
        self.browser.get(self.live_server_url + path)

    def login(self):
        """Login lewat cookie sesi (lebih cepat; alur login lewat form diuji di test pertama)."""
        self.client.force_login(self.user)
        self.open('/accounts/login/')
        self.browser.add_cookie({'name': 'sessionid', 'value': self.client.cookies['sessionid'].value, 'path': '/'})

    def open_wardrobe(self, query=''):
        self.open(reverse('digital_wardrobe:index') + query)
        self.wait.until(lambda d: d.execute_script('return Boolean(window.htmx)'))
        # Penanda: kalau halaman dimuat ulang, variabel ini hilang
        self.browser.execute_script('window.__noReload = true')

    def assert_no_reload(self):
        self.assertTrue(self.browser.execute_script('return window.__noReload === true'),
                        'Halaman dimuat ulang, padahal seharusnya tanpa reload')

    def find(self, css):
        return self.browser.find_element(By.CSS_SELECTOR, css)

    def click(self, css):
        """Gulir elemen ke tengah layar dulu (tidak tertutup bar bawah), lalu klik seperti pengguna."""
        element = self.find(css)
        self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'})", element)
        element.click()

    def texts(self, css):
        # Dibaca lewat JavaScript sekaligus, supaya aman walau HTMX sedang mengganti isi grid
        return self.browser.execute_script(
            'return [...document.querySelectorAll(arguments[0])].map((el) => el.textContent.trim())', css)

    def card_names(self):
        return self.texts('#item-grid .wd-card__name')

    def toast_text(self):
        self.wait.until(lambda d: self.texts('#wardrobe-toast .wd-toast'))
        return ' '.join(self.texts('#wardrobe-toast .wd-toast'))

    # ---------- skenario ----------
    def test_login_and_add_item_without_reload(self):
        # Login lewat form seperti pengguna
        self.open('/accounts/login/')
        self.find('input[name=username]').send_keys('fanny')
        self.find('input[name=password]').send_keys(PASSWORD)
        self.find('input[name=password]').submit()
        self.wait.until(lambda d: '/accounts/login/' not in d.current_url)

        self.open_wardrobe()
        self.find('[data-open-modal$="items/add/"]').click()
        form = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-item-form]')))

        photo = os.path.join(TEMP_MEDIA, 'kemeja.png')
        Image.new('RGB', (40, 40), (215, 136, 178)).save(photo)
        form.find_element(By.CSS_SELECTOR, 'input[type=file]').send_keys(photo)
        form.find_element(By.NAME, 'name').send_keys('Kemeja Linen Selenium')
        for field, value in (('category', 'top'), ('size', 'M'), ('gender', 'unisex'),
                             ('condition', 'good'), ('color', 'neutral')):
            Select(form.find_element(By.NAME, field)).select_by_value(value)
        form.find_element(By.CSS_SELECTOR, '[data-submit]').click()

        self.wait.until(lambda d: 'Kemeja Linen Selenium' in self.card_names())
        self.assertIn('masuk ke lemarimu', self.toast_text())
        self.assertEqual(self.find('[data-total-items]').text, '1')
        self.assert_no_reload()
        self.assertTrue(ClothingItem.objects.filter(user=self.user, name='Kemeja Linen Selenium').exists())

    def test_add_item_with_empty_form_shows_errors(self):
        self.login()
        self.open_wardrobe()
        self.find('[data-open-modal$="items/add/"]').click()
        form = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-item-form]')))
        form.find_element(By.CSS_SELECTOR, '[data-submit]').click()
        self.wait.until(lambda d: 'Wajib diisi.' in d.find_element(By.ID, 'modal-root').text)
        self.assertFalse(ClothingItem.objects.exists())

    def test_search_and_category_filter_with_htmx(self):
        self.make_item('Kemeja Linen')
        self.make_item('Kaos Polos')
        self.make_item('Celana Kulot', category='bottom')
        self.login()
        self.open_wardrobe()

        self.find('input[name=q]').send_keys('linen')
        self.wait.until(lambda d: self.card_names() == ['Kemeja Linen'])
        self.assertIn('q=linen', self.browser.current_url)

        self.find('input[name=q]').clear()
        self.wait.until(lambda d: len(self.card_names()) == 3)
        Select(self.find('select[name=category]')).select_by_value('bottom')
        self.wait.until(lambda d: self.card_names() == ['Celana Kulot'])
        self.assertIn('category=bottom', self.browser.current_url)
        self.assert_no_reload()

    def test_switch_tab_to_outfit_without_reload(self):
        outfit = Outfit.objects.create(user=self.user, name='Outfit Kampus')
        outfit.items.add(self.make_item('Kemeja'))
        self.login()
        self.open_wardrobe()
        self.browser.find_element(By.XPATH, "//a[contains(@class,'wd-tab') and contains(., 'Koleksi Outfit')]").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, 'outfit-grid')))
        self.assertIn('Outfit Kampus', self.find('#outfit-grid').text)
        self.assertIn('tab=outfit', self.browser.current_url)
        self.assert_no_reload()

    def test_delete_item_with_optimistic_ui(self):
        self.make_item('Kaos Polos')
        doomed = self.make_item('Kemeja Lama')
        self.login()
        self.open_wardrobe()
        card = self.find(f'#item-{doomed.pk}')
        card.find_element(By.CSS_SELECTOR, '[data-delete-url]').click()
        self.wait.until(EC.visibility_of_element_located((By.ID, 'delete-modal')))
        self.find('#delete-modal button[type=submit]').click()

        self.wait.until(EC.staleness_of(card))
        self.assertEqual(self.card_names(), ['Kaos Polos'])
        self.assertIn('"Kemeja Lama" sudah dihapus', self.toast_text())
        self.assertEqual(self.find('[data-total-items]').text, '1')
        self.assert_no_reload()
        self.assertFalse(ClothingItem.objects.filter(pk=doomed.pk).exists())

    def test_bulk_delete_with_select_mode(self):
        keep = self.make_item('Disimpan')
        first, second = self.make_item('Hapus Satu'), self.make_item('Hapus Dua')
        self.login()
        self.open_wardrobe()
        self.find('[data-select-toggle].wd-chip--select').click()
        self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.wd-bulkbar')))
        self.click(f'#item-{first.pk} .wd-card__body')
        self.click(f'#item-{second.pk} .wd-card__body')
        self.assertEqual(self.find('[data-bulk-count]').text, '2')

        self.find('[data-bulk-submit]').click()
        self.wait.until(EC.visibility_of_element_located((By.ID, 'bulk-delete-modal')))
        self.find('[data-bulk-confirm]').click()

        self.wait.until(lambda d: self.card_names() == ['Disimpan'])
        self.assertIn('2 pakaian dihapus', self.toast_text())
        self.assert_no_reload()
        self.assertEqual(list(ClothingItem.objects.filter(user=self.user)), [keep])

    def test_other_users_item_shows_forbidden_page(self):
        theirs = self.make_item('Jaket Rico', user=self.other)
        self.login()
        with self.assertLogs('swapdrobe.security', 'WARNING'):   # percobaan akses tercatat di log
            self.open(reverse('digital_wardrobe:item_detail', args=[theirs.pk]))
        heading = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '.wd-error h1')))
        self.assertEqual(heading.text, 'Akses ditolak')
        self.assertIn('Kamu tidak punya akses ke pakaian ini.', self.find('.wd-error').text)
        self.find('.wd-error a').click()
        self.wait.until(lambda d: d.current_url.endswith(reverse('digital_wardrobe:index')))
