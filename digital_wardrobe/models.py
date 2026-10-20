from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ClothingItemQuerySet(models.QuerySet):
    """Query bantu yang bisa dipakai juga oleh modul lain."""

    def in_wardrobe(self, user):
        """Pakaian yang tampil di Lemari Saya: milik user dan tidak sedang ditawarkan di Items for Swap."""
        return self.filter(user=user, is_listed_for_swap=False)

    def available_for_swap(self, user):
        """Pakaian yang boleh dipilih untuk ditawarkan di Items for Swap (dipakai modul Items for Swap)."""
        return self.in_wardrobe(user)

    def listed_for_swap(self, user):
        """Pakaian milik user yang sedang ditawarkan di Items for Swap."""
        return self.filter(user=user, is_listed_for_swap=True)


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
    def status_label(self):
        """Label status untuk ditampilkan di outfit & Kalender Outfit ('' jika ada di lemari)."""
        return 'Sedang ditawarkan' if self.is_listed_for_swap else ''


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
