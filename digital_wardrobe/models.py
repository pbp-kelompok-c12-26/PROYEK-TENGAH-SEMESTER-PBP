from django.db import models
from django.contrib.auth.models import User

class ClothingItem(models.Model):
    CATEGORY_CHOICES = [
        ('top', 'Tops / Atasan'),
        ('bottom', 'Bottoms / Bawahan'),
        ('outerwear', 'Outerwear / Jaket & Luaran'),
        ('footwear', 'Footwear / Sepatu'),
        ('accessory', 'Accessory / Aksesoris'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wardrobe_items')
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    color = models.CharField(max_length=50, blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    size = models.CharField(max_length=20, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)  # Atau FileField/ImageField jika upload file
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"