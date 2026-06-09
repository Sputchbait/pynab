from django.core import validators
from django.db import models

from nabcommon import singleton_model


def default_location():
    """Default location using Open-Meteo format."""
    return dict(
        name="Paris",
        lat=48.8566,
        lon=2.3522,
        country="France",
        admin1="Île-de-France",
        timezone="Europe/Paris",
    )


class Config(singleton_model.SingletonModel):
    location = models.JSONField(null=True, default=default_location)

    location_user_friendly = models.TextField(
        null=True, default="Paris, Île-de-France, France"
    )

    unit = models.IntegerField(null=False, default=1)
    next_performance_date = models.DateTimeField(null=True)
    next_performance_type = models.TextField(null=True)
    weather_animation_type = models.TextField(
        null=True, default="weather_and_rain"
    )
    weather_frequency = models.IntegerField(default=0)

    next_performance_weather_vocal_date = models.DateTimeField(null=True)
    next_performance_weather_vocal_flag = models.IntegerField(
        null=False, default=0
    )

    weather_playtime_hour = models.IntegerField(
        default=7,
        validators=[
            validators.MinValueValidator(0),
            validators.MaxValueValidator(23),
        ],
    )
    weather_playtime_min = models.IntegerField(
        default=0,
        validators=[
            validators.MinValueValidator(0),
            validators.MaxValueValidator(59),
        ],
    )

    class Meta:
        app_label = "nabweatherd"


class ScheduledMessage(models.Model):
    hour = models.IntegerField(null=False)
    minute = models.IntegerField(null=False)
    type = models.TextField(null=False)

    class Meta:
        app_label = "nabweatherd"
