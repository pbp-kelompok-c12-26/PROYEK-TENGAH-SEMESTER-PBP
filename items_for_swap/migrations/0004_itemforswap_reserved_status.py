from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items_for_swap', '0003_remove_itemforswap_unique_available_listing_per_clothing_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='itemforswap',
            name='status',
            field=models.CharField(
                choices=[('available', 'Available'), ('reserved', 'Reserved'), ('swapped', 'Swapped')],
                default='available',
                max_length=10,
            ),
        ),
    ]
