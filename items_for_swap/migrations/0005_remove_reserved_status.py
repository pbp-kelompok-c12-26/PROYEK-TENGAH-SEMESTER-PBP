from django.db import migrations, models


def release_reserved_listings(apps, schema_editor):
    ItemForSwap = apps.get_model('items_for_swap', 'ItemForSwap')
    ItemForSwap.objects.filter(status='reserved').update(status='available')


class Migration(migrations.Migration):

    dependencies = [
        ('items_for_swap', '0004_itemforswap_reserved_status'),
    ]

    operations = [
        migrations.RunPython(release_reserved_listings, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='itemforswap',
            name='status',
            field=models.CharField(
                choices=[('available', 'Available'), ('swapped', 'Swapped')],
                default='available',
                max_length=10,
            ),
        ),
    ]
