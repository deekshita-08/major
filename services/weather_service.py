from datetime import datetime, timedelta
import os
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"


def get_weather_data(latitude, longitude, timezone="Asia/Kolkata"):
    api_key = os.getenv("VISUAL_CROSSING_API_KEY")
    if not api_key:
        raise ValueError("VISUAL_CROSSING_API_KEY is not configured")

    local_now = datetime.now(ZoneInfo(timezone))
    start_date = (local_now - timedelta(days=1)).date().isoformat()
    end_date = local_now.date().isoformat()
    url = f"{BASE_URL}/{latitude},{longitude}/{start_date}/{end_date}"
    params = {
        "key": api_key,
        "unitGroup": "metric",
        "include": "hours,current",
        "timezone": timezone,
        "contentType": "json",
    }
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
    except requests.Timeout:
        raise requests.Timeout("Visual Crossing weather request timed out") from None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise requests.HTTPError(f"Visual Crossing returned HTTP {status}") from None
    except requests.RequestException:
        raise requests.RequestException("Visual Crossing weather request failed") from None

    data = response.json()
    current = data.get("currentConditions", {})
    days = data.get("days", [])
    if not current or not days:
        raise ValueError("Visual Crossing response is missing current weather")

    current_epoch = _epoch(
        current.get("datetimeEpoch"), current.get("datetime"),
        days[-1].get("datetime"), timezone,
    )
    now = datetime.fromtimestamp(current_epoch, ZoneInfo(timezone))
    observations = []
    for day in days:
        date = day.get("datetime")
        for hour in day.get("hours", []):
            epoch = _epoch(hour.get("datetimeEpoch"), hour.get("datetime"), date, timezone)
            if epoch <= current_epoch:
                precipitation = hour.get("precip")
                observations.append((epoch, {
                    "time": datetime.fromtimestamp(epoch, ZoneInfo(timezone)).isoformat(),
                    "rain_mm": _rain_amount(precipitation, hour.get("preciptype")),
                    "precipitation_mm": precipitation,
                    "showers_mm": None,
                }))

    rows = [row for _, row in observations]
    rain_windows = {}
    for hours in (1, 3, 6, 24):
        cutoff = current_epoch - hours * 3600
        window = [row for epoch, row in observations if cutoff < epoch <= current_epoch]
        values = [row["precipitation_mm"] for row in window if row["precipitation_mm"] is not None]
        rain_windows[f"last_{hours}h_precipitation_mm"] = sum(values) if len(values) == hours else None
        rain_windows[f"last_{hours}h_observations"] = len(values)

    precipitation = current.get("precip")
    return {
        "current": {
            "time": now.isoformat(),
            "temperature_c": current.get("temp"),
            "humidity_pct": current.get("humidity"),
            "precipitation_mm": precipitation,
            "rain_mm": _rain_amount(precipitation, current.get("preciptype")),
            "showers_mm": None,
            "wind_speed_kmh": current.get("windspeed"),
            "wind_direction_deg": current.get("winddir"),
            "surface_pressure_hpa": current.get("pressure"),
        },
        "hourly_observations": rows,
        "rainfall_windows": rain_windows,
        "source": "Visual Crossing",
    }


def _epoch(epoch, time_value, date_value, timezone):
    if epoch is not None:
        return float(epoch)
    if time_value is None or date_value is None:
        raise ValueError("Visual Crossing response is missing a timestamp")
    parsed = datetime.fromisoformat(f"{date_value}T{time_value}")
    return parsed.replace(tzinfo=ZoneInfo(timezone)).timestamp()


def _rain_amount(precipitation, precipitation_types):
    if precipitation is None:
        return None
    if float(precipitation) == 0:
        return 0
    if isinstance(precipitation_types, str):
        precipitation_types = [precipitation_types]
    if not precipitation_types or "rain" in {kind.lower() for kind in precipitation_types}:
        return precipitation
    return 0

def get_current_weather(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["current"]

def get_hourly_rainfall(latitude, longitude, timezone="Asia/Kolkata"):
    return get_weather_data(latitude, longitude, timezone)["hourly_observations"]
