from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ClothingItemQuerySet(models.QuerySet):
    """Query bantu yang bisa dipakai juga oleh modul lain."""

    def active(self):
        """Pakaian yang belum dihapus dari lemari."""
        return self.filter(deleted_at__isnull=True)

    def in_wardrobe(self, user):
        """Pakaian yang tampil di Lemari Saya: milik user, belum dihapus, dan tidak sedang ditawarkan di Items for Swap."""
        return self.active().filter(user=user, is_listed_for_swap=False)

    def available_for_swap(self, user):
        """Pakaian yang boleh dipilih untuk ditawarkan di Items for Swap (dipakai modul Items for Swap)."""
        return self.in_wardrobe(user)

    def listed_for_swap(self, user):
        """Pakaian milik user yang sedang ditawarkan di Items for Swap."""
        return self.active().filter(user=user, is_listed_for_swap=True)

    def refresh_idle(self, user):
        """
        Perbarui is_idle semua pakaian milik user (2 query UPDATE).
        Idle = tidak dipakai lebih dari IDLE_AFTER_DAYS hari. Pakaian yang belum
        pernah dipakai dihitung sejak ditambahkan ke lemari, jadi baju baru tidak langsung idle.
        """
        cutoff = timezone.localdate() - timedelta(days=ClothingItem.IDLE_AFTER_DAYS)
        idle = Q(last_worn_date__lt=cutoff) | Q(last_worn_date__isnull=True, created_at__date__lt=cutoff)
        mine = self.active().filter(user=user)
        mine.filter(idle, is_idle=False).update(is_idle=True)
        mine.filter(is_idle=True).exclude(idle).update(is_idle=False)


class ClothingItem(models.Model):
    """
    Satu pakaian di lemari digital milik seorang user.

    Tabel ini adalah sumber data pakaian bersama untuk semua modul
    (Outfit Calendar, Items for Swap, Swap Request hanya mereferensikan
    baris di tabel ini).
    """

    CATEGORY_CHOICES = [
        ('top', 'Atasan'),
        ('bottom', 'Bawahan'),
        ('outerwear', 'Luaran'),
        ('dress', 'Dress'),
        ('footwear', 'Sepatu'),
        ('accessory', 'Aksesori'),
    ]

    SIZE_CHOICES = [
        ('XS', 'XS'),
        ('S', 'S'),
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
        ('XXL', 'XXL'),
        ('ALL', 'Satu ukuran'),
    ]

    GENDER_CHOICES = [
        ('men', 'Pria'),
        ('women', 'Wanita'),
        ('unisex', 'Unisex'),
    ]

    CONDITION_CHOICES = [
        ('brand_new', 'Brand New'),
        ('like_new', 'Like New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
    ]

    SHOE_SIZE_MIN = 20
    SHOE_SIZE_MAX = 50
    IDLE_AFTER_DAYS = 90  # pakaian dianggap "jarang dipakai" setelah 90 hari tidak dipakai

    COLOR_CHOICES = [
        ('neutral', 'Netral'),
        ('earth', 'Earth'),
        ('bright', 'Bright'),
        ('pastel', 'Pastel'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wardrobe_items')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    # Ukuran pakaian (XS–XXL / Satu ukuran). Dikosongkan untuk sepatu.
    size = models.CharField(max_length=5, choices=SIZE_CHOICES, blank=True)
    # Ukuran sepatu (EU), hanya untuk kategori Sepatu.
    shoe_size = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(SHOE_SIZE_MIN), MaxValueValidator(SHOE_SIZE_MAX)],
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='wardrobe/items/%Y/%m/')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Diisi/diubah oleh modul lain (lihat panduan §7)
    last_worn_date = models.DateField(null=True, blank=True)        # Outfit Calendar
    is_idle = models.BooleanField(default=False)                    # penanda "jarang dipakai"
    is_listed_for_swap = models.BooleanField(default=False)         # Items for Swap
    # Diisi saat pakaian dihapus padahal sudah dipakai di outfit / Kalender Outfit:
    # pakaian hilang dari lemari, tapi tetap tampil di outfit & kalender dengan status.
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ClothingItemQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pakaian'
        verbose_name_plural = 'Pakaian'

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def is_footwear(self):
        return self.category == 'footwear'

    @property
    def size_label(self):
        """Ukuran siap tampil: 'EU 38' untuk sepatu, 'M' / 'Satu ukuran' untuk lainnya."""
        if self.is_footwear:
            return f'EU {self.shoe_size}' if self.shoe_size else '-'
        return self.get_size_display() or '-'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def seen_by(self, owner_id):
        """Tandai pemilik outfit/jadwal tempat pakaian ini ditampilkan.
        Dipakai status_label untuk tahu apakah pakaian sudah berpindah lewat swap."""
        self.context_owner_id = owner_id
        return self

    @property
    def is_swapped_away(self):
        """True kalau pakaian ini tampil di outfit/jadwal milik orang yang sudah
        tidak memilikinya lagi (sudah ditukar lewat Swap Request)."""
        owner_id = getattr(self, 'context_owner_id', None)
        return owner_id is not None and owner_id != self.user_id

    @property
    def status_label(self):
        """Label status untuk ditampilkan di outfit & Kalender Outfit ('' jika ada di lemari)."""
        if self.is_swapped_away:
            return 'Pakaian tidak tersedia'
        if self.is_deleted:
            return 'Sudah dihapus dari lemari'
        return 'Sedang ditawarkan' if self.is_listed_for_swap else ''

    def is_in_use(self):
        """Sudah dipakai di outfit, jadwal Kalender Outfit, atau punya riwayat swap?
        Pakaian seperti ini hanya disembunyikan saat dihapus, supaya riwayatnya tetap ada."""
        if self.outfits.exists():
            return True
        scheduled = getattr(self, 'scheduled_entries', None)  # dari modul Kalender Outfit
        if scheduled is not None and scheduled.exists():
            return True
        listings = getattr(self, 'swap_listings', None)  # dari modul Items for Swap
        return bool(listings is not None and listings.exists())

    def remove_from_wardrobe(self):
        """
        Hapus pakaian dari lemari.
        Pakaian yang masih dipakai request Pending/Awaiting harus dilepas dari request dulu.
        - Sudah dipakai di outfit/kalender: disembunyikan saja (deleted_at diisi), foto & data tetap.
        - Belum pernah dipakai: dihapus permanen beserta fotonya.
        Mengembalikan 'archived' atau 'deleted'.
        """
        from swap_requests.models import SwapRequest
        if SwapRequest.objects.has_active_request(self):
            raise ValidationError('Pakaian ini sedang dipakai dalam swap request. Batalkan request terlebih dahulu sebelum menghapusnya.')
        if self.is_in_use():
            self.deleted_at = timezone.now()
            self.is_listed_for_swap = False
            self.save(update_fields=['deleted_at', 'is_listed_for_swap', 'updated_at'])
            return 'archived'
        if self.image:
            self.image.delete(save=False)
        self.delete()
        return 'deleted'


class Outfit(models.Model):
    """
    Kombinasi maksimal 5 pakaian dari lemari user yang sama.
    """

    MAX_ITEMS = 5

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='outfits')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    items = models.ManyToManyField(ClothingItem, related_name='outfits')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Outfit'
        verbose_name_plural = 'Outfit'

    def __str__(self):
        return self.name

    @classmethod
    def validate_items(cls, user, items):
        """
        Dipakai oleh form: pastikan 1–5 pakaian dan semuanya milik user yang sama.
        """
        items = list(items)
        if not items:
            raise ValidationError('Pilih minimal 1 pakaian.')
        if len(items) > cls.MAX_ITEMS:
            raise ValidationError(f'Satu outfit maksimal {cls.MAX_ITEMS} pakaian.')
        if any(item.user_id != user.id for item in items):
            raise ValidationError('Outfit hanya boleh berisi pakaian dari lemarimu sendiri.')
