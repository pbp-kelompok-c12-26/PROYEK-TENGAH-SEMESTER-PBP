"""
Test penyimpanan foto di Cloudinary (PROJECTS/storage.py).
API Cloudinary tidak benar-benar dipanggil: fungsi upload/destroy/resource disimulasikan (mock),
jadi test ini jalan tanpa internet & tanpa akun Cloudinary.
"""
import io
from unittest import mock

import cloudinary
from cloudinary import exceptions as cloudinary_errors
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage, storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from digital_wardrobe.models import ClothingItem
from PROJECTS.storage import CloudinaryMediaStorage

CLOUDINARY_STORAGES = {
    'default': {'BACKEND': 'PROJECTS.storage.CloudinaryMediaStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class CloudinaryConfigMixin:
    """Cloud name palsu supaya URL bisa dibentuk tanpa akun asli."""

    def setUp(self):
        super().setUp()
        self._old_cloud_name = cloudinary.config().cloud_name
        cloudinary.config(cloud_name='swapdrobe-test')

    def tearDown(self):
        cloudinary.config(cloud_name=self._old_cloud_name)
        super().tearDown()


@mock.patch('PROJECTS.storage.cloudinary.uploader')
@mock.patch('PROJECTS.storage.cloudinary.api')
class CloudinaryMediaStorageTests(CloudinaryConfigMixin, SimpleTestCase):
    def setUp(self):
        super().setUp()
        self.storage = CloudinaryMediaStorage(folder='swapdrobe')

    def test_url_uses_folder_and_keeps_extension(self, api, uploader):
        url = self.storage.url('wardrobe/items/2026/10/kemeja.jpg')
        self.assertEqual(url, 'https://res.cloudinary.com/swapdrobe-test/image/upload/v1/swapdrobe/wardrobe/items/2026/10/kemeja.jpg')

    def test_save_uploads_with_public_id_and_returns_same_name(self, api, uploader):
        api.resource.side_effect = cloudinary_errors.NotFound('tidak ada')
        name = self.storage.save('wardrobe/items/2026/10/kemeja.jpg', SimpleUploadedFile('kemeja.jpg', b'isi'))
        self.assertEqual(name, 'wardrobe/items/2026/10/kemeja.jpg')
        _file, options = uploader.upload.call_args
        self.assertEqual(options['public_id'], 'swapdrobe/wardrobe/items/2026/10/kemeja')
        self.assertEqual(options['resource_type'], 'image')
        self.assertFalse(options['overwrite'])

    def test_save_avoids_name_clash(self, api, uploader):
        # Nama pertama sudah ada di Cloudinary -> Django otomatis memilih nama lain
        api.resource.side_effect = [{'public_id': 'ada'}, cloudinary_errors.NotFound('tidak ada')]
        name = self.storage.save('wardrobe/kemeja.jpg', SimpleUploadedFile('kemeja.jpg', b'isi'))
        self.assertNotEqual(name, 'wardrobe/kemeja.jpg')
        self.assertTrue(name.startswith('wardrobe/kemeja_') and name.endswith('.jpg'))

    def test_delete_calls_destroy(self, api, uploader):
        self.storage.delete('profile_pictures/fanny.png')
        uploader.destroy.assert_called_once_with('swapdrobe/profile_pictures/fanny', resource_type='image', invalidate=True)
        self.storage.delete('')
        self.assertEqual(uploader.destroy.call_count, 1)

    def test_exists(self, api, uploader):
        api.resource.return_value = {'public_id': 'swapdrobe/a'}
        self.assertTrue(self.storage.exists('a.jpg'))
        api.resource.side_effect = cloudinary_errors.NotFound('tidak ada')
        self.assertFalse(self.storage.exists('a.jpg'))
        api.resource.side_effect = cloudinary_errors.RateLimited('sibuk')
        self.assertFalse(self.storage.exists('a.jpg'))

    def test_size(self, api, uploader):
        api.resource.return_value = {'bytes': 2048}
        self.assertEqual(self.storage.size('a.jpg'), 2048)

    def test_folder_from_environment(self, api, uploader):
        with mock.patch.dict('os.environ', {'CLOUDINARY_FOLDER': '/swapdrobe-pws/'}):
            self.assertEqual(CloudinaryMediaStorage()._public_id('x/y.png'), 'swapdrobe-pws/x/y')
        self.assertEqual(CloudinaryMediaStorage(folder='')._public_id('x/y.png'), 'x/y')


class StorageSettingsTests(SimpleTestCase):
    def test_local_and_tests_use_media_folder(self):
        # Cloudinary hanya aktif kalau PRODUCTION=True dan CLOUDINARY_URL ada (di PWS)
        self.assertFalse(settings.USE_CLOUDINARY)
        self.assertIsInstance(storages['default'], FileSystemStorage)


@override_settings(STORAGES=CLOUDINARY_STORAGES)
@mock.patch('PROJECTS.storage.cloudinary.uploader')
@mock.patch('PROJECTS.storage.cloudinary.api')
class CloudinaryWithModelsTests(CloudinaryConfigMixin, TestCase):
    """Model yang sudah ada (ImageField) langsung memakai Cloudinary tanpa diubah."""

    def test_clothing_item_photo_goes_to_cloudinary(self, api, uploader):
        api.resource.side_effect = cloudinary_errors.NotFound('tidak ada')
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), (215, 136, 178)).save(buffer, format='PNG')
        user = User.objects.create_user('fanny', password='Password123!')
        item = ClothingItem.objects.create(
            user=user, name='Kemeja', category='top', size='M', color='neutral', condition='good', gender='unisex',
            image=SimpleUploadedFile('kemeja.png', buffer.getvalue(), content_type='image/png'))

        self.assertTrue(uploader.upload.called)
        self.assertTrue(item.image.url.startswith('https://res.cloudinary.com/swapdrobe-test/image/upload/'))
        self.assertTrue(item.image.url.endswith('/kemeja.png'))

        item.remove_from_wardrobe()   # belum pernah dipakai -> dihapus permanen beserta fotonya
        self.assertTrue(uploader.destroy.called)
