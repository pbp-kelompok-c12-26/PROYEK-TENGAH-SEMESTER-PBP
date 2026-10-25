from django.db import migrations


class Migration(migrations.Migration):
    """Status "Pakaian tidak tersedia" sekarang dihitung dari pemilik pakaian vs pemilik outfit,
    jadi flag ini tidak dipakai lagi (flag ini ikut terbawa ke pemilik baru setelah swap)."""

    dependencies = [
        ('digital_wardrobe', '0004_clothingitem_unavailable_in_outfits'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='clothingitem',
            name='unavailable_in_outfits',
        ),
    ]
