#!/usr/bin/env python3
"""Integration test for Open-Meteo weather service."""

import sys
import json
import asyncio
from pathlib import Path

# Add nabweatherd to path
sys.path.insert(0, str(Path(__file__).parent / "nabweatherd"))

from openmeteo_client import OpenMeteoClient
from wmo_codes import get_weather_class, get_weather_description

def test_location_flow():
    """Test complete location search and selection flow."""
    print("=" * 60)
    print("Testing Location Search Flow")
    print("=" * 60)

    client = OpenMeteoClient()

    # Search for Los Angeles
    query = "Los Angeles"
    print(f"\nSearching for: {query}")
    results = client.get_geocoding(query)

    if not results:
        print("✗ No results found")
        return False

    # Simulate user selecting first result
    selected = results[0]
    print(f"✓ Found {len(results)} results")
    print(f"\nSelected location:")
    print(f"  Name: {selected['name']}")
    print(f"  Admin1: {selected.get('admin1', 'N/A')}")
    print(f"  Country: {selected['country']}")
    print(f"  Coordinates: ({selected['latitude']:.4f}, {selected['longitude']:.4f})")

    # Create location JSON as it would be stored in DB
    location_json = {
        "name": selected["name"],
        "lat": selected["latitude"],
        "lon": selected["longitude"],
        "country": selected["country"],
        "admin1": selected.get("admin1", ""),
        "timezone": selected.get("timezone", ""),
    }

    print(f"\nLocation JSON (as stored in DB):")
    print(json.dumps(location_json, indent=2))

    return location_json

def test_weather_fetch(location_json):
    """Test weather data fetch for a location."""
    print("\n" + "=" * 60)
    print("Testing Weather Data Fetch")
    print("=" * 60)

    client = OpenMeteoClient()

    lat = location_json["lat"]
    lon = location_json["lon"]

    print(f"\nFetching weather for {location_json['name']} ({lat:.2f}, {lon:.2f})")

    try:
        forecast = client.get_forecast_for_place(lat, lon)

        # Extract data as the service would
        current = forecast.get("current", {})
        daily = forecast.get("daily", {})

        current_wmo = current.get("weather_code", 3)
        current_temp = current.get("temperature_2m")
        current_precip = current.get("precipitation", 0)

        today_wmo = daily.get("weather_code", [3])[0]
        today_max = daily.get("temperature_2m_max", [20])[0]
        today_min = daily.get("temperature_2m_min", [20])[0]

        tomorrow_wmo = daily.get("weather_code", [3])[1] if len(daily.get("weather_code", [])) > 1 else 3
        tomorrow_max = daily.get("temperature_2m_max", [20])[1] if len(daily.get("temperature_2m_max", [])) > 1 else 20

        print("\n✓ Weather data retrieved successfully")
        print("\nCurrent conditions:")
        print(f"  Temperature: {current_temp:.1f}°C")
        print(f"  Weather: {get_weather_description(current_wmo)} (class: {get_weather_class(current_wmo)})")
        print(f"  Precipitation: {current_precip:.1f}mm")
        print(f"  Rain expected: {'Yes' if current_precip > 0 else 'No'}")

        print("\nToday forecast:")
        print(f"  High/Low: {today_max:.1f}°C / {today_min:.1f}°C")
        print(f"  Weather: {get_weather_description(today_wmo)} (class: {get_weather_class(today_wmo)})")

        print("\nTomorrow forecast:")
        print(f"  High: {tomorrow_max:.1f}°C")
        print(f"  Weather: {get_weather_description(tomorrow_wmo)} (class: {get_weather_class(tomorrow_wmo)})")

        # Simulate what fetch_info_data would return
        info_data = {
            "weather_animation_type": "weather_and_rain",
            "current_weather_class": get_weather_class(current_wmo),
            "next_rain": current_precip > 0,
            "today_forecast_weather_class": get_weather_class(today_wmo),
            "today_forecast_max_temp": int(today_max),
            "tomorrow_forecast_weather_class": get_weather_class(tomorrow_wmo),
            "tomorrow_forecast_max_temp": int(tomorrow_max),
        }

        print("\ninfo_data structure (as service would return):")
        print(json.dumps(info_data, indent=2))

        return True

    except Exception as e:
        print(f"✗ Error fetching weather: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_backward_compatibility():
    """Test handling of old location format."""
    print("\n" + "=" * 60)
    print("Testing Backward Compatibility")
    print("=" * 60)

    # Old Météo-France format
    old_location = {
        "insee": "75056",
        "name": "Paris 14",
        "lat": 48.8331,
        "lon": 2.3264,
        "country": "FR",
        "admin": "Île-de-France",
        "admin2": "75",
        "postCode": "75014",
    }

    print("\nOld location format:")
    print(json.dumps(old_location, indent=2))

    # Check if we can extract lat/lon
    lat = old_location.get("lat")
    lon = old_location.get("lon")

    if lat and lon:
        print(f"\n✓ Can extract coordinates: ({lat}, {lon})")
        print("  Old format locations will still work")

        # Fetch weather with old format
        client = OpenMeteoClient()
        try:
            forecast = client.get_forecast_for_place(lat, lon)
            print("✓ Weather fetch successful with old format coordinates")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    else:
        print("✗ Cannot extract coordinates from old format")
        return False

def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("Weather Service Integration Test Suite")
    print("=" * 60 + "\n")

    results = {}

    # Test 1: Location search and selection
    location_json = test_location_flow()
    results["Location Search"] = location_json is not None

    # Test 2: Weather data fetch
    if location_json:
        results["Weather Fetch"] = test_weather_fetch(location_json)
    else:
        results["Weather Fetch"] = False

    # Test 3: Backward compatibility
    results["Backward Compat"] = test_backward_compatibility()

    # Summary
    print("\n" + "=" * 60)
    print("Integration Test Summary")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:20s}: {status}")

    all_passed = all(results.values())
    print("=" * 60)
    print(f"Overall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    print("=" * 60 + "\n")

    if all_passed:
        print("✅ Weather service integration is ready!")
        print("\nNext steps:")
        print("1. Deploy updated code to Aaron's Bunny")
        print("2. Re-configure location via web UI")
        print("3. Test weather announcements")
        print("4. Monitor logs for 24 hours")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
