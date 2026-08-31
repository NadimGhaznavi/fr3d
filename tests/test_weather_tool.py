from __future__ import annotations

import json
import unittest
from typing import Any

from weather_tool.weather import WeatherError, get_weather, validate_location


class WeatherToolTest(unittest.TestCase):
    def test_location_is_normalized(self) -> None:
        self.assertEqual(
            validate_location("  Hamilton,   Ontario, Canada "),
            "Hamilton, Ontario, Canada",
        )

    def test_unsafe_or_unusable_locations_are_rejected(self) -> None:
        for location in ("", "x", "https://example.com", "Paris?count=100"):
            with self.subTest(location=location), self.assertRaises(ValueError):
                validate_location(location)

    def test_location_is_geocoded_before_forecast(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.requests: list[tuple[str, dict[str, Any]]] = []

            def get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
                self.requests.append((url, params))
                if "geocoding-api" in url:
                    return {"results": [{
                        "name": "Hamilton",
                        "admin1": "Ontario",
                        "country": "Canada",
                        "latitude": 43.2557,
                        "longitude": -79.8711,
                        "timezone": "America/Toronto",
                    }]}
                return {
                    "current_units": {"temperature_2m": "°C"},
                    "current": {"temperature_2m": 22.0},
                    "daily_units": {"temperature_2m_max": "°C"},
                    "daily": {"temperature_2m_max": [24.0, 25.0, 23.0]},
                }

        client = FakeClient()
        result = json.loads(get_weather("Hamilton, Ontario, Canada", client))

        self.assertEqual(result["resolved_location"]["name"], "Hamilton")
        self.assertEqual(result["current"]["temperature_2m"], 22.0)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(client.requests[1][1]["latitude"], 43.2557)
        self.assertNotIn("name", client.requests[1][1])

    def test_unknown_location_is_rejected(self) -> None:
        class EmptyClient:
            def get_json(self, _url: str, _params: dict[str, Any]) -> dict[str, Any]:
                return {"results": []}

        with self.assertRaisesRegex(WeatherError, "location not found"):
            get_weather("Not A Real Place", EmptyClient())


if __name__ == "__main__":
    unittest.main()
