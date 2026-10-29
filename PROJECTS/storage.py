"""
Penyimpanan foto upload (ImageField/FileField) di Cloudinary.

Kenapa: di PWS, folder media/ ikut kosong setiap kali aplikasi di-deploy ulang, sehingga foto
pakaian & foto profil hilang. Dengan storage ini file disimpan di Cloudinary, bukan di server PWS.

Dipakai hanya di production (lihat STORAGES di PROJECTS/settings.py): kalau PRODUCTION=True dan
environment variable CLOUDINARY_URL ada. Di laptop & saat test tetap memakai folder media/ biasa.

Model, form, view, dan template tidak perlu diubah: tetap memakai item.image.url, image.delete(), dst.
Nama file yang disimpan di database tetap sama formatnya (mis. "wardrobe/items/2026/10/kemeja.jpg");
di Cloudinary disimpan sebagai public_id "<CLOUDINARY_FOLDER>/wardrobe/items/2026/10/kemeja".
"""
import os
import posixpath
from urllib.request import urlopen

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from cloudinary import exceptions as cloudinary_errors
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryMediaStorage(Storage):
    """Storage Django untuk gambar di Cloudinary (kredensial dibaca SDK dari env CLOUDINARY_URL)."""

    def __init__(self, folder=None):
        self.folder = (folder if folder is not None else os.getenv('CLOUDINARY_FOLDER', 'swapdrobe')).strip('/')

    # ---------- nama file <-> public_id Cloudinary ----------
    def _public_id(self, name):
        base, _ext = posixpath.splitext(name.replace('\\', '/'))
        return f'{self.folder}/{base}' if self.folder else base

    @staticmethod
    def _format(name):
        return posixpath.splitext(name)[1].lstrip('.').lower() or None

    # ---------- operasi Storage ----------
    def _save(self, name, content):
        if hasattr(content, 'seek'):
            content.seek(0)
        cloudinary.uploader.upload(
            content,
            public_id=self._public_id(name),
            resource_type='image',
            overwrite=False,
            unique_filename=False,
            use_filename=False,
        )
        return name   # disimpan di database apa adanya

    def _open(self, name, mode='rb'):
        with urlopen(self.url(name)) as response:   # jarang dipakai; cukup baca dari URL publik
            return ContentFile(response.read(), name=name)

    def delete(self, name):
        if name:
            cloudinary.uploader.destroy(self._public_id(name), resource_type='image', invalidate=True)

    def exists(self, name):
        """Dipakai Django untuk menghindari nama file kembar saat upload."""
        try:
            cloudinary.api.resource(self._public_id(name), resource_type='image')
        except cloudinary_errors.NotFound:
            return False
        except cloudinary_errors.Error:
            return False   # API sedang bermasalah: anggap belum ada, upload tidak menimpa (overwrite=False)
        return True

    def url(self, name):
        url, _options = cloudinary.utils.cloudinary_url(self._public_id(name), format=self._format(name), secure=True)
        return url

    def size(self, name):
        return cloudinary.api.resource(self._public_id(name), resource_type='image').get('bytes', 0)
