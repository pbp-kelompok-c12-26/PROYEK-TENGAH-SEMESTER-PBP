from django.db import migrations, models


def convert_unavailable_to_rejected(apps, schema_editor):
    SwapRequest = apps.get_model('swap_requests', 'SwapRequest')
    SwapRequestNotification = apps.get_model('swap_requests', 'SwapRequestNotification')
    SwapRequest.objects.filter(status='unavailable').exclude(status='completed').update(status='rejected')
    SwapRequestNotification.objects.filter(status='unavailable').update(status='rejected')


class Migration(migrations.Migration):
    dependencies = [
        ('swap_requests', '0003_swaprequestnotification'),
    ]

    operations = [
        migrations.RunPython(convert_unavailable_to_rejected, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='swaprequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('rejected', 'Rejected'),
                    ('awaiting_exchange', 'Awaiting exchange'),
                    ('completed', 'Completed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='swaprequestnotification',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('rejected', 'Rejected'),
                    ('awaiting_exchange', 'Awaiting exchange'),
                    ('completed', 'Completed'),
                ],
                max_length=20,
            ),
        ),
    ]
