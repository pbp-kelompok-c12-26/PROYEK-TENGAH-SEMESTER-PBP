import django.db.models.deletion
from django.db import migrations, models


def fill_outfit_name(apps, schema_editor):
    OutfitSchedule = apps.get_model('outfit_calendar', 'OutfitSchedule')
    for schedule in OutfitSchedule.objects.select_related('outfit'):
        if schedule.outfit_id:
            schedule.outfit_name = schedule.outfit.name
            schedule.save(update_fields=['outfit_name'])


class Migration(migrations.Migration):
    """Riwayat jadwal tetap tersimpan walau outfit-nya dihapus."""

    dependencies = [
        ('digital_wardrobe', '0005_remove_clothingitem_unavailable_in_outfits'),
        ('outfit_calendar', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='outfitschedule',
            name='outfit_name',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='outfitschedule',
            name='outfit',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedules', to='digital_wardrobe.outfit'),
        ),
        migrations.RunPython(fill_outfit_name, migrations.RunPython.noop),
    ]
