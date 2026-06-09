"""Open-Meteo API client for weather data.

Weather data provided by Open-Meteo.com (CC BY 4.0)
https://open-meteo.com

Python 3.7 compatible version - uses requests directly
"""
import requests
import time
from functools import wraps


def simple_cache(ttl=300):
    """Simple cache decorator for Python 3.7 compatibility."""
    cache = {}
    cache_time = {}

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()

            if key in cache and (now - cache_time.get(key, 0)) < ttl:
                return cache[key]

            result = func(*args, **kwargs)
            cache[key] = result
            cache_time[key] = now
            return result
        return wrapper
    return decorator


class OpenMeteoClient:
    """Client for Open-Meteo weather API."""

    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.timeout = 10

    @simple_cache(ttl=300)
    def get_forecast_for_place(self, latitude, longitude):
        """Get forecast for coordinates.

        Args:
            latitude: Decimal latitude
            longitude: Decimal longitude

        Returns:
            dict with current and daily forecast data
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
            "timezone": "auto",
            "temperature_unit": "celsius"
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.5 * (2 ** attempt))

    @simple_cache(ttl=300)
    def get_geocoding(self, query):
        """Search for location by name.

        Args:
            query: City name or location search string

        Returns:
            list of matching locations with coordinates
        """
        params = {
            "name": query,
            "count": 10,
            "language": "en",
            "format": "json"
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    self.geocoding_url,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()

                if "results" not in data:
                    return []

                return data["results"]
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.5 * (2 ** attempt))
