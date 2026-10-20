
# Create your models here.

from datetime import date

from django.contrib.auth.models import User
from django.db import models

from digital_wardrobe.models import ClothingItem, Outfit


class OutfitSchedule(models.Model):
    """Satu outfit yang dijadwalkan di satu tanggal (1 jadwal per hari per user)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='outfit_schedules')
    # Outfit dihapus di Digital Wardrobe -> jadwalnya ikut terhapus
    outfit = models.ForeignKey(Outfit, on_delete=models.CASCADE, related_name='schedules')
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
        return f'{self.user.username} - {self.outfit.name} ({self.date})'

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
        if self.date > date.today():
            return
        for item in self.outfit.items.all():
            if item.last_worn_date is None or item.last_worn_date < self.date:
                item.last_worn_date = self.date
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