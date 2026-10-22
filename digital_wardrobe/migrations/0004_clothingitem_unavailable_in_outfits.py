from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('digital_wardrobe', '0003_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='clothingitem',
            name='unavailable_in_outfits',
            field=models.BooleanField(default=False),
        ),
    ]
