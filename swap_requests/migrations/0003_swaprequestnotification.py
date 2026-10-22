from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('swap_requests', '0002_request_visibility_and_status_cleanup'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SwapRequestNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('rejected', 'Rejected'), ('awaiting_exchange', 'Awaiting exchange'), ('completed', 'Completed'), ('unavailable', 'Item not available')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='swap_request_notifications', to=settings.AUTH_USER_MODEL)),
                ('swap_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='swap_requests.swaprequest')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['recipient', 'read_at'], name='swap_notif_rec_read_idx')],
            },
        ),
    ]
