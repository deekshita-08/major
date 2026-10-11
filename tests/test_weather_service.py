from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
import requests

from services.weather_service import get_weather_data


def _epoch(date, time):
    return datetime.fromisoformat(f"{date}T{time}").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")
    ).timestamp()


def test_visual_crossing_response_is_normalized(monkeypatch):
    monkeypatch.setenv("VISUAL_CROSSING_API_KEY", "test-key")
    now = _epoch("2026-01-02", "12:00:00")
    hours = [
        {"datetime": f"{hour:02}:00:00", "datetimeEpoch": _epoch("2026-01-02", f"{hour:02}:00:00"),
         "precip": amount, "preciptype": ["rain"]}
        for hour, amount in ((9, 1), (10, 2), (11, 3), (12, 4), (13, 99))
    ]
    response = Mock()
    response.json.return_value = {
        "days": [
            {"datetime": "2026-01-01", "hours": []},
            {"datetime": "2026-01-02", "hours": hours},
        ],
        "currentConditions": {
            "datetime": "12:00:00", "datetimeEpoch": now, "temp": 23,
            "humidity": 80, "precip": 4, "preciptype": ["rain"],
            "windspeed": 12, "winddir": 90, "pressure": 1008,
        },
    }
    with patch("services.weather_service.requests.get", return_value=response) as get:
        weather = get_weather_data(17.0, 78.0)

    get.assert_called_once()
    assert get.call_args.kwargs["params"]["key"] == "test-key"
    assert weather["source"] == "Visual Crossing"
    assert weather["current"]["temperature_c"] == 23
    assert weather["current"]["wind_speed_kmh"] == 12
    assert [row["precipitation_mm"] for row in weather["hourly_observations"]] == [1, 2, 3, 4]
    assert weather["rainfall_windows"]["last_1h_precipitation_mm"] == 4
    assert weather["rainfall_windows"]["last_3h_precipitation_mm"] == 9
    assert weather["rainfall_windows"]["last_24h_precipitation_mm"] is None


def test_visual_crossing_request_error_does_not_expose_key(monkeypatch):
    monkeypatch.setenv("VISUAL_CROSSING_API_KEY", "test-key")
    with patch(
        "services.weather_service.requests.get",
        side_effect=requests.Timeout("request failed for test-key"),
    ), pytest.raises(requests.Timeout) as error:
        get_weather_data(17.0, 78.0)

    assert "test-key" not in str(error.value)


def test_visual_crossing_requires_api_key(monkeypatch):
    monkeypatch.delenv("VISUAL_CROSSING_API_KEY", raising=False)

    with pytest.raises(ValueError, match="VISUAL_CROSSING_API_KEY"):
        get_weather_data(17.0, 78.0)
