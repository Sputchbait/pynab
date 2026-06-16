# Generated migration for allowed_audio_domains field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nabmqttd', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='config',
            name='allowed_audio_domains',
            field=models.TextField(default='localhost,192.168.1.234,192.168.1.195'),
        ),
    ]
