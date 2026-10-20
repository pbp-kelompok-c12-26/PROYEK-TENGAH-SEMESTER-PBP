from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Profil user. Diisi lewat onboarding saat login pertama, bisa dilengkapi nanti."""

    STYLE_CHOICES = [
        ('casual', 'Casual'), ('korean', 'Korean'), ('y2k', 'Y2K'), ('streetwear', 'Streetwear'),
        ('minimalis', 'Minimalis'), ('vintage', 'Vintage'), ('formal', 'Formal'),
        ('sporty', 'Sporty'), ('bohemian', 'Bohemian'), ('preppy', 'Preppy'), ('feminim', 'Feminim'),
        ('monokrom', 'Monokrom'), ('modest', 'Modest'), ('old_money', 'Old Money'),
    ]
    CLOTHING_SIZE_CHOICES = [(s, s) for s in ('XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL')]
    SHOE_SIZE_CHOICES = [(str(n), str(n)) for n in range(35, 49)]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField('Display name', max_length=50, blank=True)
    avatar = models.ImageField('Foto profil', upload_to='profiles/%Y/%m/', blank=True)
    bio = models.TextField('Biografi', max_length=300, blank=True)
    favorite_styles = models.JSONField('Style favorit', default=list, blank=True)
    clothing_sizes = models.JSONField('Ukuran pakaian', default=list, blank=True)
    shoe_sizes = models.JSONField('Ukuran sepatu (EU)', default=list, blank=True)
    # True setelah onboarding ditampilkan di login pertama (diisi atau tidak)
    onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profil {self.user.username}'

    @property
    def name(self):
        """Nama yang ditampilkan: display name, atau username kalau kosong."""
        return self.display_name or self.user.username

    @property
    def style_labels(self):
        labels = dict(self.STYLE_CHOICES)
        return [labels[s] for s in self.favorite_styles if s in labels]

    @classmethod
    def for_user(cls, user):
        """Ambil profil user, buat otomatis kalau belum ada (termasuk akun lama)."""
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
