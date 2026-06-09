# Weather Feature Update - Deployment Comparison

**Date**: 2026-06-09
**Branch**: weather-source-update
**Target Device**: Aaron's Bunny (192.168.1.234)

## Executive Summary

The weather service has been completely migrated from Météo-France API (France-only) to Open-Meteo API (global coverage). This enables US and worldwide location support while removing the API key requirement.

---

## Files Changed

### 1. New Files Created

#### `/opt/pynab/nabweatherd/openmeteo_client.py` (NEW)
**Purpose**: API client for Open-Meteo weather service

**Key Features**:
- No API key required
- 5-minute caching for rate limit compliance
- Automatic retry with exponential backoff
- Global coverage via geocoding API

**Methods**:
- `get_forecast_for_place(latitude, longitude)` - Fetch weather forecast
- `get_geocoding(query)` - Search for locations by name

**Current Status**: ❌ Does not exist on Aaron's Bunny
**Action Required**: Deploy new file

---

#### `/opt/pynab/nabweatherd/wmo_codes.py` (NEW)
**Purpose**: WMO weather code mapper

**Key Features**:
- Maps WMO codes (0-99) to Pynab animation classes
- Provides human-readable descriptions
- Handles invalid codes gracefully

**Functions**:
- `get_weather_class(wmo_code)` - Returns animation class (sunny, cloudy, rainy, etc.)
- `get_weather_description(wmo_code)` - Returns English description

**Current Status**: ❌ Does not exist on Aaron's Bunny
**Action Required**: Deploy new file

---

### 2. Modified Files

#### `/opt/pynab/nabweatherd/nabweatherd.py`

**Changes**:

| Section | Old (Météo-France) | New (Open-Meteo) |
|---------|-------------------|------------------|
| **Imports** | `from meteofrance_api.client import MeteoFranceClient, Place` | `from .openmeteo_client import OpenMeteoClient`<br>`from .wmo_codes import get_weather_class, get_weather_description` |
| **Weather Classes** | 90+ French weather descriptions mapped to animations | 6 animation classes mapped directly |
| **Data Source** | `MeteoFranceClient().get_forecast_for_place(Place)` | `OpenMeteoClient().get_forecast_for_place(lat, lon)` |
| **Location Format** | Expects `Place` object with INSEE codes | Expects `{"lat": float, "lon": float}` |
| **Weather Code** | French text descriptions | WMO standard codes (0-99) |
| **Rain Detection** | Separate `get_rain()` API call (France-only) | Precipitation from main forecast |

**Key Code Changes**:

```python
# OLD (lines ~406-433)
place = Place(location)
client = await sync_to_async(MeteoFranceClient)()
my_place_weather_forecast = client.get_forecast_for_place(place)
data = my_place_weather_forecast.daily_forecast
raininfo = client.get_rain(place.latitude, place.longitude)
current_weather_class = self.normalize_weather_class(data[0]["weather12H"]["desc"])

# NEW
latitude = location.get("lat")
longitude = location.get("lon")
client = OpenMeteoClient()
forecast = await sync_to_async(client.get_forecast_for_place)(latitude, longitude)
current_wmo = forecast.get("current", {}).get("weather_code", 3)
current_weather_class = get_weather_class(current_wmo)
```

**Impact**: Complete rewrite of weather data fetching logic

---

#### `/opt/pynab/nabweatherd/views.py`

**Changes**:

| Section | Old (Météo-France) | New (Open-Meteo) |
|---------|-------------------|------------------|
| **Imports** | `from meteofrance_api.client import MeteoFranceClient, Place` | `from .openmeteo_client import OpenMeteoClient` |
| **Location Search** | `MeteoFranceClient().search_places()` | `OpenMeteoClient().get_geocoding()` |
| **Search Results** | Place objects with INSEE codes | JSON with lat/lon/country/admin1 |
| **Display Format** | "Paris 14 - Île-de-France (75) - FR" | "Paris, Île-de-France, France" |

**Key Code Changes**:

```python
# OLD (lines ~37-53)
client = MeteoFranceClient()
list_places = client.search_places(search_location)
for one_place in list_places:
    json_item["value"] = str(one_place.raw_data)
    json_item["text"] = one_place.__str__()

# NEW
client = OpenMeteoClient()
list_places = client.get_geocoding(search_location)
for place in list_places:
    location_data = {
        "name": place.get("name"),
        "lat": place.get("latitude"),
        "lon": place.get("longitude"),
        "country": place.get("country"),
        "admin1": place.get("admin1"),
        "timezone": place.get("timezone"),
    }
    json_item["value"] = json.dumps(location_data)
```

**Impact**: Location search now returns global results instead of France-only

---

#### `/opt/pynab/nabweatherd/models.py`

**Changes**:

| Section | Old (Météo-France) | New (Open-Meteo) |
|---------|-------------------|------------------|
| **Default Location** | Paris with INSEE code 75056 | Paris with lat/lon |
| **Location Fields** | insee, admin, admin2, postCode | admin1, timezone (no INSEE) |
| **Display Format** | "Paris 14 - Île-de-France (75) - FR" | "Paris, Île-de-France, France" |

**Key Code Changes**:

```python
# OLD
def default_location():
    return dict(
        insee="75056",
        name="Paris 14",
        lat=48.8331,
        lon=2.3264,
        country="FR",
        admin="Île-de-France",
        admin2="75",
        postCode="75014",
    )

# NEW
def default_location():
    return dict(
        name="Paris",
        lat=48.8566,
        lon=2.3522,
        country="France",
        admin1="Île-de-France",
        timezone="Europe/Paris",
    )
```

**Impact**: Database default updated to new format

---

#### `/opt/pynab/requirements.txt`

**Changes**:

| Dependency | Status | Reason |
|-----------|--------|--------|
| `meteofrance-api==1.0.2` | ❌ REMOVED | Replaced with Open-Meteo |
| `openmeteo-requests==1.1.0` | ✅ ADDED | New weather API client |
| `requests-cache==1.1.1` | ✅ ADDED | Rate limit compliance |
| `retry-requests==2.0.0` | ✅ ADDED | Reliability |

**Current Status on Aaron's Bunny**:
- ✅ `meteofrance-api` is currently installed
- ❌ Open-Meteo dependencies NOT installed

**Action Required**: 
```bash
pip uninstall meteofrance-api
pip install openmeteo-requests requests-cache retry-requests
```

---

## Functional Comparison

### Before (Météo-France)

**Supported Locations**:
- ❌ France only
- ❌ Requires INSEE codes
- ❌ French postal codes

**Weather Data**:
- ✅ Current conditions
- ✅ Daily forecast (2 days)
- ✅ Rain forecast (France only)
- ❌ French weather descriptions

**API Requirements**:
- ✅ No API key required
- ❌ France-specific endpoints

**Example Location Search**:
```
Query: "Los Angeles"
Result: No results found (not in France)
```

---

### After (Open-Meteo)

**Supported Locations**:
- ✅ Worldwide coverage (200+ countries)
- ✅ US locations fully supported
- ✅ Global coordinate-based system

**Weather Data**:
- ✅ Current conditions
- ✅ Daily forecast (7 days available, using 2)
- ✅ Precipitation probability
- ✅ WMO standard weather codes
- ✅ English descriptions

**API Requirements**:
- ✅ No API key required
- ✅ 10,000 free calls/day
- ✅ 5-minute caching implemented

**Example Location Search**:
```
Query: "Los Angeles"
Result: 
  - Los Angeles, California, United States (34.05, -118.24)
  - Los Angeles, Metro Manila, Philippines
  - Los Angeles, Biobío Region, Chile
  (10 results total)
```

---

## Backward Compatibility

### Old Location Format Support

**Old format** (Météo-France):
```json
{
  "insee": "75056",
  "name": "Paris 14",
  "lat": 48.8331,
  "lon": 2.3264,
  "country": "FR",
  "admin": "Île-de-France",
  "admin2": "75",
  "postCode": "75014"
}
```

**Compatibility**: ✅ **MAINTAINED**
- Code extracts `lat` and `lon` from old format
- Weather fetch continues to work
- Users with existing locations do NOT need to reconfigure

**Recommendation**: Users should re-select location for improved accuracy and new format benefits

---

## Testing Results

### Integration Tests (Local)

| Test | Status | Details |
|------|--------|---------|
| WMO Code Mapping | ✅ PASSED | All weather codes map correctly |
| Geocoding API | ✅ PASSED | Global location search works |
| Forecast API | ✅ PASSED | Weather data retrieved correctly |
| Data Format | ✅ PASSED | Compatible with Pynab expectations |
| Location Search Flow | ✅ PASSED | US locations found and selected |
| Weather Fetch | ✅ PASSED | LA weather retrieved successfully |
| Backward Compatibility | ✅ PASSED | Old locations still work |

**Overall**: ✅ **7/7 TESTS PASSED**

---

## Deployment Plan

### Phase 1: Backup Current System
```bash
ssh pi@192.168.1.234
cd /opt/pynab
sudo cp -r nabweatherd nabweatherd.backup-$(date +%Y%m%d)
```

### Phase 2: Update Dependencies
```bash
cd /opt/pynab
sudo -u pi /opt/pynab/venv/bin/pip uninstall -y meteofrance-api
sudo -u pi /opt/pynab/venv/bin/pip install openmeteo-requests==1.1.0 requests-cache==1.1.1 retry-requests==2.0.0
```

### Phase 3: Deploy New Files
```bash
# Copy from development machine to Aaron's Bunny
scp nabweatherd/openmeteo_client.py pi@192.168.1.234:/opt/pynab/nabweatherd/
scp nabweatherd/wmo_codes.py pi@192.168.1.234:/opt/pynab/nabweatherd/
```

### Phase 4: Deploy Updated Files
```bash
scp nabweatherd/nabweatherd.py pi@192.168.1.234:/opt/pynab/nabweatherd/
scp nabweatherd/views.py pi@192.168.1.234:/opt/pynab/nabweatherd/
scp nabweatherd/models.py pi@192.168.1.234:/opt/pynab/nabweatherd/
scp requirements.txt pi@192.168.1.234:/opt/pynab/
```

### Phase 5: Restart Service
```bash
ssh pi@192.168.1.234
sudo systemctl restart nabweatherd
sudo journalctl -u nabweatherd -f
```

### Phase 6: Verification
1. Open web interface: http://192.168.1.234/nabweatherd/settings
2. Search for "Los Angeles" - should return US results
3. Select location and save
4. Check logs for successful weather fetch
5. Trigger weather announcement to verify animations

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| API rate limiting | Low | 5-minute caching implemented |
| Existing locations break | Low | Backward compatibility maintained |
| Service fails to start | Medium | Backup available for rollback |
| Weather animations wrong | Low | WMO mapping thoroughly tested |
| Network issues | Low | Retry logic with exponential backoff |

---

## Rollback Plan

If weather service fails after deployment:

```bash
ssh pi@192.168.1.234
cd /opt/pynab
sudo systemctl stop nabweatherd

# Restore backup
sudo rm -rf nabweatherd
sudo cp -r nabweatherd.backup-YYYYMMDD nabweatherd

# Restore dependencies
sudo -u pi /opt/pynab/venv/bin/pip install meteofrance-api==1.0.2
sudo -u pi /opt/pynab/venv/bin/pip uninstall -y openmeteo-requests requests-cache retry-requests

sudo systemctl start nabweatherd
```

---

## Success Criteria

- [ ] Location search returns US results
- [ ] Weather forecast displays correctly
- [ ] Animations match weather conditions
- [ ] No errors in logs for 24 hours
- [ ] Memory usage remains stable
- [ ] Old French locations still work

---

## Additional Notes

**Weather data attribution**:
- All weather data provided by Open-Meteo.com (CC BY 4.0)
- Attribution included in code comments

**API limits**:
- 10,000 calls/day per IP
- 5-minute caching ensures ~288 calls/day maximum
- Well within limits for single device

**Future enhancements**:
- 7-day forecast support (API provides, currently using 2 days)
- Hourly precipitation forecast
- UV index and air quality (available from Open-Meteo)
- Weather alerts for severe conditions
