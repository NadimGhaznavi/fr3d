"""Validated Open-Meteo location lookup and weather retrieval."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MAX_LOCATION_LENGTH = 120
MAX_RESPONSE_BYTES = 1_000_000
LOCATION_PATTERN = re.compile(r"^[\w .,'’-]+$", re.UNICODE)
CURRENT_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
)
DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
)


class WeatherError(RuntimeError):
    """Raised when a weather request cannot be completed safely."""


class WeatherClient(Protocol):
    def get_json(
        self,
        url: str,
        params: dict[str, str | int | float],
    ) -> dict[str, Any]: ...


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenMeteoClient:
    """Small bounded HTTPS client for the two fixed Open-Meteo endpoints."""

    def get_json(
        self,
        url: str,
        params: dict[str, str | int | float],
    ) -> dict[str, Any]:
        request = Request(f"{url}?{urlencode(params)}", headers={"Accept": "application/json"})
        try:
            with build_opener(_NoRedirects()).open(request, timeout=10) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                    raise WeatherError("Open-Meteo response is too large")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise WeatherError("Open-Meteo response is too large")
                payload = json.loads(body)
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            raise WeatherError(f"Open-Meteo request failed: {error}") from error
        return _object(payload, "JSON")


def validate_location(location: str) -> str:
    """Return a normalized, bounded location query or reject it."""
    if not isinstance(location, str):
        raise TypeError("location must be a string")
    normalized = " ".join(location.strip().split())
    if len(normalized) < 2 or len(normalized) > MAX_LOCATION_LENGTH:
        raise ValueError(
            f"location must contain 2 to {MAX_LOCATION_LENGTH} characters"
        )
    if "_" in normalized or not LOCATION_PATTERN.fullmatch(normalized):
        raise ValueError(
            "location may contain letters, numbers, spaces, commas, periods, "
            "apostrophes, and hyphens only"
        )
    if not any(character.isalnum() for character in normalized):
        raise ValueError("location must contain a letter or number")
    return normalized


def _object(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WeatherError(f"Open-Meteo returned invalid {context} data")
    return payload


def _request_json(
    client: WeatherClient,
    url: str,
    params: dict[str, str | int | float],
) -> dict[str, Any]:
    return _object(client.get_json(url, params), "JSON")


def geocode(client: WeatherClient, location: str) -> dict[str, Any]:
    """Resolve a validated location using Open-Meteo geocoding."""
    query = validate_location(location)
    payload = _request_json(
        client,
        GEOCODING_URL,
        {"name": query, "count": 1, "language": "en", "format": "json"},
    )
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise WeatherError(f"location not found: {query}")
    result = _object(results[0], "location")

    latitude = result.get("latitude")
    longitude = result.get("longitude")
    name = result.get("name")
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not -90 <= latitude <= 90
        or isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not -180 <= longitude <= 180
        or not isinstance(name, str)
        or not name
    ):
        raise WeatherError("Open-Meteo returned an invalid location match")
    return result


def get_weather(location: str, client: WeatherClient | None = None) -> str:
    """Return current conditions and a three-day forecast for a location."""
    if client is None:
        client = OpenMeteoClient()
    match = geocode(client, location)
    forecast = _request_json(
        client,
        FORECAST_URL,
        {
            "latitude": match["latitude"],
            "longitude": match["longitude"],
            "current": ",".join(CURRENT_VARIABLES),
            "daily": ",".join(DAILY_VARIABLES),
            "forecast_days": 3,
            "timezone": "auto",
        },
    )

    current = _object(forecast.get("current"), "current-weather")
    daily = _object(forecast.get("daily"), "forecast")
    resolved_location = {
        key: match[key]
        for key in ("name", "admin1", "country", "latitude", "longitude", "timezone")
        if key in match
    }
    result = {
        "requested_location": validate_location(location),
        "resolved_location": resolved_location,
        "current_units": forecast.get("current_units", {}),
        "current": current,
        "daily_units": forecast.get("daily_units", {}),
        "daily": daily,
    }
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
