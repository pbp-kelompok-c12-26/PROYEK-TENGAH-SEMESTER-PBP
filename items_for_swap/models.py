from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver

from digital_wardrobe.models import ClothingItem


def get_photo_url(item):
    """URL foto pakaian. Nama field foto di ClothingItem dicoba satu per satu,
    jadi tidak error kalau namanya photo / image / foto."""
    for attr in ('photo', 'image', 'foto'):
        f = getattr(item, attr, None)
        if f:
            try:
                return f.url
            except ValueError:
                return ''
    return ''


class ItemForSwapQuerySet(models.QuerySet):
    def available(self):
        return self.filter(status='available')

    def swapped(self):
        return self.filter(status='swapped')

    def mine(self, user):
        """Item Swap Saya."""
        return self.filter(user=user).select_related('clothing_item')

    def catalog_for(self, user):
        """Katalog Jelajahi: listing available milik orang lain."""
        return self.available().exclude(user=user).select_related('clothing_item', 'user')


class ItemForSwap(models.Model):
    AVAILABLE = 'available'
    SWAPPED = 'swapped'
    STATUS_CHOICES = [(AVAILABLE, 'Available'), (SWAPPED, 'Swapped')]

    # Data baju TIDAK diduplikat: foto/nama/ukuran/kondisi diambil dari clothing_item.
    clothing_item = models.ForeignKey(ClothingItem, on_delete=models.CASCADE, related_name='swap_listings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='swap_listings')
    # Teks lokasi yang ditampilkan, mis. "Stasiun UI, Kota Depok, Jawa Barat".
    meeting_location = models.CharField('Lokasi bertemu', max_length=255)
    # Pilihan terstruktur dari API Wilayah Indonesia (lihat home/wilayah.py) + detail tempat.
    # Kosong untuk listing lama yang dulu diisi sebagai teks bebas.
    meeting_city_code = models.CharField('Kode kab/kota bertemu', max_length=20, blank=True)
    meeting_city = models.CharField('Kab/kota bertemu', max_length=100, blank=True)
    meeting_province = models.CharField('Provinsi bertemu', max_length=100, blank=True)
    meeting_place = models.CharField('Detail tempat bertemu', max_length=150, blank=True)
    reason = models.TextField('Deskripsi', blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=AVAILABLE)
    posted_at = models.DateTimeField(auto_now_add=True)

    objects = ItemForSwapQuerySet.as_manager()

    class Meta:
        ordering = ['-posted_at']
        constraints = [
            # 1 baju hanya boleh punya 1 listing berstatus available
            models.UniqueConstraint(
                fields=['clothing_item'],
                condition=Q(status='available'),
                name='one_available_listing_per_item',
            ),
        ]

    def __str__(self):
        return f'{self.clothing_item.name} oleh {self.user}'

    # ---------- properti bantu ----------
    @property
    def is_available(self):
        return self.status == self.AVAILABLE

    @property
    def photo_url(self):
        return get_photo_url(self.clothing_item)

    @property
    def request_count(self):
        from swap_requests.models import SwapRequest
        return SwapRequest.objects.filter(
            requested_item_id=self.clothing_item_id,
            status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
        ).count()

    # ---------- validasi & simpan ----------
    def clean(self):
        if self.clothing_item_id and self.user_id and self.clothing_item.user_id != self.user_id:
            raise ValidationError('Pakaian ini bukan milik pengguna tersebut.')
        if self.clothing_item_id and not self.pk:
            manager = self._swap_request_manager()
            has_active_request = getattr(manager, 'has_active_request', None)
            if has_active_request and has_active_request(self.clothing_item):
                raise ValidationError('Pakaian ini sedang dipakai dalam swap request. Batalkan request terlebih dahulu.')

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.user_id and self.clothing_item_id:
                self.user_id = self.clothing_item.user_id
            super().save(*args, **kwargs)
            if self.status == self.AVAILABLE:
                ClothingItem.objects.filter(pk=self.clothing_item_id).update(is_listed_for_swap=True)

    # ---------- Lokasi bertemu ----------
    def set_meeting_location(self, location, place=''):
        """Isi lokasi bertemu dari dict lokasi hasil home.wilayah.LocationField."""
        place = (place or '').strip()
        self.meeting_city_code = location['code']
        self.meeting_city = location['city']
        self.meeting_province = location['province']
        self.meeting_place = place
        self.meeting_location = f"{place}, {location['label']}" if place else location['label']

    @property
    def meeting_area(self):
        """Lokasi singkat untuk kartu: nama kab/kota, atau teks lama kalau belum terstruktur."""
        return self.meeting_city or self.meeting_location

    # ---------- Create ----------
    @classmethod
    def list_item(cls, clothing_item, user, meeting_location='', reason='', location=None, meeting_place=''):
        """Tawarkan pakaian dari lemari: buat listing + set flag, atomic."""
        with transaction.atomic():
            item = ClothingItem.objects.select_for_update().get(pk=clothing_item.pk)
            if item.user_id != user.pk:
                raise ValidationError('Pakaian ini bukan milikmu.')
            if item.deleted_at is not None:
                raise ValidationError('Pakaian ini sudah dihapus dari lemari.')
            if item.is_listed_for_swap:
                raise ValidationError('Pakaian ini sudah ditawarkan.')
            manager = cls._swap_request_manager()
            has_active_request = getattr(manager, 'has_active_request', None)
            if has_active_request and has_active_request(item):
                raise ValidationError('Pakaian ini sedang dipakai dalam swap request. Batalkan request terlebih dahulu.')
            listing = cls(clothing_item=item, user=user, meeting_location=meeting_location, reason=reason)
            if location:
                listing.set_meeting_location(location, meeting_place)
            listing.save()
            return listing

    # ---------- Delete ("Kembalikan ke wardrobe") ----------
    @staticmethod
    def _swap_request_manager():
        try:
            from swap_requests.models import SwapRequest
        except ImportError:   # modul Zahran belum jadi
            return None
        return SwapRequest.objects

    def has_locking_request(self):
        """True kalau ada request Awaiting exchange untuk pakaian ini."""
        manager = self._swap_request_manager()
        checker = getattr(manager, 'is_locked', None)
        return bool(checker and checker(self.clothing_item))

    def return_to_wardrobe(self):
        if self.status != self.AVAILABLE:
            raise ValidationError('Item yang sudah swapped tidak bisa dikembalikan.')
        if self.has_locking_request():
            raise ValidationError('Pakaian ini sedang dalam proses tukar, belum bisa dikembalikan.')
        with transaction.atomic():
            # flag is_listed_for_swap direset oleh signal post_delete di bawah
            self.delete()


@receiver(post_delete, sender=ItemForSwap)
def reset_listed_flag(sender, instance, **kwargs):
    """Listing available dihapus (lewat view maupun admin) -> baju kembali ke lemari."""
    if instance.status == ItemForSwap.AVAILABLE:
        ClothingItem.objects.filter(pk=instance.clothing_item_id).update(is_listed_for_swap=False)
        manager = ItemForSwap._swap_request_manager()
        sync = getattr(manager, 'sync_availability', None)
        if sync:
            sync()  # Request aktif terkait listing ini berubah menjadi Rejected.
