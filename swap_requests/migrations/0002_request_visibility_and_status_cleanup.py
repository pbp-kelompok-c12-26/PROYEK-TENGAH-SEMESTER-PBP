from django.db import migrations, models


def convert_cancelled_to_rejected(apps, schema_editor):
    SwapRequest = apps.get_model('swap_requests', 'SwapRequest')
    SwapRequest.objects.filter(status='cancelled').update(status='rejected')


class Migration(migrations.Migration):

    dependencies = [
        ('swap_requests', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(convert_cancelled_to_rejected, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='swaprequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('rejected', 'Rejected'),
                    ('awaiting_exchange', 'Awaiting exchange'),
                    ('completed', 'Completed'),
                    ('unavailable', 'Item not available'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='swaprequest',
            name='requester_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='swaprequest',
            name='owner_hidden',
            field=models.BooleanField(default=False),
        ),
    ]
