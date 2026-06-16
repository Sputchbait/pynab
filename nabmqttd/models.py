from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):
    broker_host = models.CharField(max_length=255, default="192.168.1.195")
    broker_port = models.IntegerField(default=1883)
    broker_username = models.CharField(max_length=255, blank=True, default="")
    broker_password = models.CharField(max_length=255, blank=True, default="")
    topic_prefix = models.CharField(max_length=255, default="nabaztag")
    enabled = models.BooleanField(default=False)
    publish_button_events = models.BooleanField(default=True)
    publish_rfid_events = models.BooleanField(default=True)
    publish_ears_state = models.BooleanField(default=True)
    publish_led_state = models.BooleanField(default=True)
    client_id = models.CharField(max_length=255, default="nabaztag_aaron")
    json_data_base = models.TextField(null=True, default="{}")

    # Phase 2: Voice recognition options
    enable_voice = models.BooleanField(default=False)
    voice_on_button = models.BooleanField(default=True)
    asr_language = models.CharField(max_length=5, default="en_US")

    # Audio URL security settings
    # Comma-separated list of allowed domains for HTTP audio playback
    # Leave empty ("*") to allow all domains (less secure)
    # Example: "localhost,192.168.1.195,example.com"
    allowed_audio_domains = models.TextField(default="localhost,192.168.1.234,192.168.1.195")

    class Meta:
        app_label = "nabmqttd"
