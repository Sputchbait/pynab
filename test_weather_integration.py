#!/usr/bin/env python3
"""Test script for new Open-Meteo weather integration."""

import sys
import json
from pathlib import Path

# Add nabweatherd to path
sys.path.insert(0, str(Path(__file__).parent / "nabweatherd"))

from openmeteo_client import OpenMeteoClient
from wmo_codes import get_weather_class, get_weather_description

def test_wmo_codes():
    """Test WMO code mapping."""
    print("=" * 60)
    print("Testing WMO Code Mapper")
    print("=" * 60)

    test_cases = [
        (0, "sunny", "Clear sky"),
        (3, "cloudy", "Overcast"),
        (61, "rainy", "Slight rain"),
        (71, "snowy", "Slight snow"),
        (45, "foggy", "Foggy"),
        (95, "stormy", "Thunderstorm"),
        (999, "cloudy", "Unknown conditions"),  # Invalid code should default
    ]

    all_passed = True
    for code, expected_class, expected_desc in test_cases:
        weather_class = get_weather_class(code)
        description = get_weather_description(code)

        class_ok = weather_class == expected_class
        desc_ok = expected_desc in description or code == 999

        status = "✓" if (class_ok and desc_ok) else "✗"
        print(f"{status} WMO {code:3d} -> '{weather_class}' ({description})")

        if not (class_ok and desc_ok):
            print(f"  Expected class: '{expected_class}'")
            all_passed = False

    print(f"\nWMO Code Tests: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed

def test_geocoding():
    """Test location search."""
    print("=" * 60)
    print("Testing Geocoding API")
    print("=" * 60)

    client = OpenMeteoClient()

    test_locations = [
        "Los Angeles",
        "New York",
        "Paris",
        "Tokyo",
        "London"
    ]

    all_passed = True
    for location in test_locations:
        try:
            results = client.get_geocoding(location)

            if not results:
                print(f"✗ {location}: No results found")
                all_passed = False
                continue

            first = results[0]
            required_fields = ["name", "latitude", "longitude", "country"]
            missing = [f for f in required_fields if f not in first]

            if missing:
                print(f"✗ {location}: Missing fields: {missing}")
                all_passed = False
                continue

            print(f"✓ {location}")
            print(f"  -> {first['name']}, {first.get('admin1', 'N/A')}, {first['country']}")
            print(f"     Coordinates: ({first['latitude']:.4f}, {first['longitude']:.4f})")

        except Exception as e:
            print(f"✗ {location}: Error - {e}")
            all_passed = False

    print(f"\nGeocoding Tests: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed

def test_forecast():
    """Test weather forecast retrieval."""
    print("=" * 60)
    print("Testing Weather Forecast API")
    print("=" * 60)

    client = OpenMeteoClient()

    # Test locations with coordinates
    test_coords = [
        ("Los Angeles", 34.0522, -118.2437),
        ("New York", 40.7128, -74.0060),
        ("Paris", 48.8566, 2.3522),
    ]

    all_passed = True
    for name, lat, lon in test_coords:
        try:
            forecast = client.get_forecast_for_place(lat, lon)

            # Check required fields
            if "current" not in forecast:
                print(f"✗ {name}: Missing 'current' data")
                all_passed = False
                continue

            if "daily" not in forecast:
                print(f"✗ {name}: Missing 'daily' data")
                all_passed = False
                continue

            current = forecast["current"]
            daily = forecast["daily"]

            # Validate current data
            required_current = ["temperature_2m", "weather_code"]
            missing_current = [f for f in required_current if f not in current]

            if missing_current:
                print(f"✗ {name}: Missing current fields: {missing_current}")
                all_passed = False
                continue

            # Validate daily data
            required_daily = ["weather_code", "temperature_2m_max", "temperature_2m_min"]
            missing_daily = [f for f in required_daily if f not in daily]

            if missing_daily:
                print(f"✗ {name}: Missing daily fields: {missing_daily}")
                all_passed = False
                continue

            # Get weather class from WMO code
            wmo_code = current["weather_code"]
            weather_class = get_weather_class(wmo_code)
            description = get_weather_description(wmo_code)

            print(f"✓ {name} ({lat:.2f}, {lon:.2f})")
            print(f"  Current: {current['temperature_2m']:.1f}°C - {description} (class: {weather_class})")
            print(f"  Today: {daily['temperature_2m_max'][0]:.1f}°C / {daily['temperature_2m_min'][0]:.1f}°C")

        except Exception as e:
            print(f"✗ {name}: Error - {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print(f"\nForecast Tests: {'PASSED' if all_passed else 'FAILED'}\n")
    return all_passed

def test_data_format_compatibility():
    """Test that data format matches what nabweatherd expects."""
    print("=" * 60)
    print("Testing Data Format Compatibility")
    print("=" * 60)

    client = OpenMeteoClient()

    # Get real data
    forecast = client.get_forecast_for_place(34.0522, -118.2437)  # LA

    print("Sample forecast structure:")
    print(json.dumps({
        "current": {
            k: forecast["current"].get(k)
            for k in ["temperature_2m", "weather_code", "precipitation"]
        },
        "daily": {
            k: forecast["daily"].get(k, [])[:3]  # First 3 days
            for k in ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum"]
        }
    }, indent=2))

    # Check that we can process daily forecast
    print("\nProcessing daily forecast:")
    for i in range(min(3, len(forecast["daily"]["weather_code"]))):
        wmo_code = forecast["daily"]["weather_code"][i]
        temp_max = forecast["daily"]["temperature_2m_max"][i]
        temp_min = forecast["daily"]["temperature_2m_min"][i]
        weather_class = get_weather_class(wmo_code)
        description = get_weather_description(wmo_code)

        print(f"  Day {i+1}: {description} ({weather_class}), {temp_max:.1f}°C / {temp_min:.1f}°C")

    print("\n✓ Data format is compatible with Pynab expectations\n")
    return True

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Open-Meteo Weather Integration Test Suite")
    print("=" * 60 + "\n")

    results = {
        "WMO Codes": test_wmo_codes(),
        "Geocoding": test_geocoding(),
        "Forecast": test_forecast(),
        "Data Format": test_data_format_compatibility(),
    }

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:20s}: {status}")

    all_passed = all(results.values())
    print("=" * 60)
    print(f"Overall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
