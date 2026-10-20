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
    meeting_location = models.CharField('Lokasi bertemu', max_length=255)
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
        # TODO (Zahran): hitung request aktif (Pending/Nego) untuk listing ini
        # setelah model SwapRequest jadi.
        return 0

    # ---------- validasi & simpan ----------
    def clean(self):
        if self.clothing_item_id and self.user_id and self.clothing_item.user_id != self.user_id:
            raise ValidationError('Pakaian ini bukan milik pengguna tersebut.')

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.user_id and self.clothing_item_id:
                self.user_id = self.clothing_item.user_id
            super().save(*args, **kwargs)
            if self.status == self.AVAILABLE:
                ClothingItem.objects.filter(pk=self.clothing_item_id).update(is_listed_for_swap=True)

    # ---------- Create ----------
    @classmethod
    def list_item(cls, clothing_item, user, meeting_location, reason=''):
        """Tawarkan pakaian dari lemari: buat listing + set flag, atomic."""
        with transaction.atomic():
            item = ClothingItem.objects.select_for_update().get(pk=clothing_item.pk)
            if item.user_id != user.pk:
                raise ValidationError('Pakaian ini bukan milikmu.')
            if item.deleted_at is not None:
                raise ValidationError('Pakaian ini sudah dihapus dari lemari.')
            if item.is_listed_for_swap:
                raise ValidationError('Pakaian ini sudah ditawarkan.')
            return cls.objects.create(
                clothing_item=item, user=user,
                meeting_location=meeting_location, reason=reason,
            )

    # ---------- Delete ("Kembalikan ke wardrobe") ----------
    @staticmethod
    def _swap_request_manager():
        try:
            from swap_requests.models import SwapRequest
        except ImportError:   # modul Zahran belum jadi
            return None
        return SwapRequest.objects

    def has_locking_request(self):
        """True kalau ada request Awaiting exchange / Accepted.
        TODO (Zahran): sampai SwapRequest.objects.is_locked() ada, selalu False."""
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
            manager = self._swap_request_manager()
            sync = getattr(manager, 'sync_availability', None)
            if sync:
                sync()   # request Pending/Nego -> "Item not available"


@receiver(post_delete, sender=ItemForSwap)
def reset_listed_flag(sender, instance, **kwargs):
    """Listing available dihapus (lewat view maupun admin) -> baju kembali ke lemari."""
    if instance.status == ItemForSwap.AVAILABLE:
        ClothingItem.objects.filter(pk=instance.clothing_item_id).update(is_listed_for_swap=False)