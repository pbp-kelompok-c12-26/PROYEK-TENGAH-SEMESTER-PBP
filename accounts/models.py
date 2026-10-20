
from django.conf import settings
from django.db import models


STYLE_CHOICES = [
    ("casual", "Casual"),
    ("korean", "Korean"),
    ("streetwear", "Streetwear"),
    ("minimalist", "Minimalist"),
    ("y2k", "Y2K"),
    ("vintage", "Vintage"),
    ("formal", "Formal"),
    ("coquette", "Coquette"),
    ("sporty", "Sporty"),
    ("old_money", "Old Money"),
    ("grunge", "Grunge"),
    ("chic", "Chic"),
    ("preppy", "Preppy"),
    ("bohemian", "Bohemian"),
]

CLOTHING_SIZE_CHOICES = [
    ("XXS", "XXS"),
    ("XS", "XS"),
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
    ("XXL", "XXL"),
]

SHOE_SIZE_CHOICES = [
    (size, str(size))
    for size in range(35, 49)
]


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    # Wajib
    display_name = models.CharField(max_length=15)
    phone_number = models.CharField(
        max_length=20,
        unique=True,
    )
    domicile = models.CharField(max_length=100)

    # Opsional
    profile_picture = models.FileField(
        upload_to="profile_pictures/",
        blank=True,
        null=True,
    )
    bio = models.TextField(blank=True)

    # Preferensi: boleh memilih beberapa
    preferred_styles = models.JSONField(default=list, blank=True)
    preferred_clothing_sizes = models.JSONField(default=list, blank=True)
    preferred_shoe_sizes = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.display_name
