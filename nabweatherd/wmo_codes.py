"""WMO Weather Code to Pynab Animation Mapper.

Maps WMO codes (0-99) to Pynab weather animation classes.
WMO codes from: https://open-meteo.com/en/docs

Weather data provided by Open-Meteo.com (CC BY 4.0)
"""

WMO_CODE_MAPPING = {
    # Clear sky
    0: "sunny",
    1: "sunny",  # Mainly clear
    2: "cloudy",  # Partly cloudy
    3: "cloudy",  # Overcast

    # Fog
    45: "foggy",
    48: "foggy",  # Depositing rime fog

    # Drizzle
    51: "rainy",  # Light
    53: "rainy",  # Moderate
    55: "rainy",  # Dense
    56: "rainy",  # Light freezing
    57: "rainy",  # Dense freezing

    # Rain
    61: "rainy",  # Slight
    63: "rainy",  # Moderate
    65: "rainy",  # Heavy
    66: "rainy",  # Light freezing
    67: "rainy",  # Heavy freezing

    # Snow
    71: "snowy",  # Slight
    73: "snowy",  # Moderate
    75: "snowy",  # Heavy
    77: "snowy",  # Snow grains

    # Showers
    80: "rainy",  # Slight
    81: "rainy",  # Moderate
    82: "rainy",  # Violent
    85: "snowy",  # Slight snow showers
    86: "snowy",  # Heavy snow showers

    # Thunderstorm
    95: "stormy",
    96: "stormy",  # With slight hail
    99: "stormy",  # With heavy hail
}

def get_weather_class(wmo_code):
    """Get Pynab weather class from WMO code.

    Args:
        wmo_code: WMO weather code (0-99)

    Returns:
        str: Weather class (sunny, cloudy, rainy, snowy, foggy, stormy)
    """
    return WMO_CODE_MAPPING.get(wmo_code, "cloudy")

def get_weather_description(wmo_code):
    """Get human-readable description from WMO code.

    Args:
        wmo_code: WMO weather code (0-99)

    Returns:
        str: English description
    """
    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return descriptions.get(wmo_code, "Unknown conditions")
