
# Create your models here.

from datetime import date

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Max

from digital_wardrobe.models import ClothingItem, Outfit


class OutfitSchedule(models.Model):
    """Satu outfit yang dijadwalkan di satu tanggal (1 jadwal per hari per user)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='outfit_schedules')
    # Outfit dihapus di Digital Wardrobe -> jadwal mendatang ikut dihapus (lihat outfit_delete),
    # riwayat jadwal tetap ada dengan nama outfit dari outfit_name.
    outfit = models.ForeignKey(Outfit, on_delete=models.SET_NULL, null=True, related_name='schedules')
    outfit_name = models.CharField(max_length=100, blank=True)
    date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['user', 'date'], name='one_outfit_per_day'),
        ]

    def __str__(self):
        return f'{self.user.username} - {self.display_name} ({self.date})'

    def save(self, *args, **kwargs):
        if self.outfit_id:
            self.outfit_name = self.outfit.name
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.outfit.name if self.outfit_id else (self.outfit_name or 'Outfit sudah dihapus')

    @property
    def outfit_deleted(self):
        return self.outfit_id is None

    def save_snapshot(self):
        """Catat daftar baju outfit saat ini, supaya kalau baju dihapus dari lemari
        jadwal tetap bisa menampilkan 'Sudah dihapus dari lemari'."""
        self.worn_items.all().delete()
        ScheduledItem.objects.bulk_create([
            ScheduledItem(schedule=self, clothing_item=item, name=item.name)
            for item in self.outfit.items.all()
        ])

    def update_last_worn(self):
        """Tanggal hari ini/lampau = outfit dianggap sudah dipakai."""
        recompute_last_worn([w.clothing_item_id for w in self.worn_items.all()])


def recompute_last_worn(item_ids):
    """Hitung ulang last_worn_date dari jadwal (hari ini & sebelumnya) milik pemilik pakaian sekarang.
    Dipakai saat jadwal dibuat, diubah, atau dihapus. Jadwal milik pemilik lama
    (sebelum pakaian ditukar) tidak ikut dihitung."""
    today = date.today()
    for item in ClothingItem.objects.filter(pk__in=[pk for pk in item_ids if pk]):
        latest = (ScheduledItem.objects
                  .filter(clothing_item=item, schedule__user_id=item.user_id, schedule__date__lte=today)
                  .aggregate(latest=Max('schedule__date'))['latest'])
        if item.last_worn_date != latest:
            item.last_worn_date = latest
            item.save(update_fields=['last_worn_date'])


class ScheduledItem(models.Model):
    """Snapshot baju di sebuah jadwal."""
    schedule = models.ForeignKey(OutfitSchedule, on_delete=models.CASCADE, related_name='worn_items')
    # Baju dihapus dari lemari -> jadi NULL, nama tetap tersimpan
    clothing_item = models.ForeignKey(ClothingItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_entries')
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    @property
    def is_deleted(self):
        return self.clothing_item_id is None