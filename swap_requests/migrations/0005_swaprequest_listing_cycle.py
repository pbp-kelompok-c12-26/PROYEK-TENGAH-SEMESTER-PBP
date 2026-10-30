from django.db import migrations, models


def backfill_current_listing_cycles(apps, schema_editor):
    SwapRequest = apps.get_model('swap_requests', 'SwapRequest')
    ItemForSwap = apps.get_model('items_for_swap', 'ItemForSwap')
    database = schema_editor.connection.alias

    for listing in ItemForSwap.objects.using(database).filter(status='available').iterator():
        cycle_key = f'{listing.pk}:{listing.posted_at.isoformat()}'
        requests = SwapRequest.objects.using(database).filter(
            owner_id=listing.user_id,
            requested_item_id=listing.clothing_item_id,
            created_at__gte=listing.posted_at,
        ).filter(
            models.Q(requested_listing_cycle_key__isnull=True)
            | models.Q(requested_listing_cycle_key=''),
        )
        requests.update(requested_listing_cycle_key=cycle_key)


class Migration(migrations.Migration):
    dependencies = [
        ('swap_requests', '0004_remove_unavailable_status'),
        ('items_for_swap', '0006_itemforswap_meeting_wilayah'),
    ]

    operations = [
        migrations.AddField(
            model_name='swaprequest',
            name='requested_listing_cycle_key',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='swaprequest',
            name='requested_listing_returned_to_wardrobe',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_current_listing_cycles, migrations.RunPython.noop),
    ]
