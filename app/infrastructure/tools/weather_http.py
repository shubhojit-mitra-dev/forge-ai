"""Keyless Open-Meteo weather HTTP tool."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.domain.value_objects.enums import ToolName

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _validate_coordinate(value: Any, *, name: str, min_val: float, max_val: float) -> float:
    """Validate numeric coordinate bounds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Argument '{name}' must be a number.")
    coord = float(value)
    if not (min_val <= coord <= max_val):
        raise ValueError(f"Argument '{name}' must be between {min_val} and {max_val}.")
    return coord


class WeatherHttpTool:
    """Queries the keyless Open-Meteo forecast API for current weather at coordinates."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client = client
        self._timeout = timeout

    @property
    def name(self) -> ToolName:
        return ToolName.WEATHER_HTTP

    @property
    def description(self) -> str:
        return (
            "Fetch current weather conditions (temperature, windspeed, weathercode) "
            "from Open-Meteo for a given latitude and longitude."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude in decimal degrees (-90 to 90).",
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude in decimal degrees (-180 to 180).",
                },
            },
            "required": ["latitude", "longitude"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        """Fetch current weather from Open-Meteo and return a JSON string."""
        latitude = _validate_coordinate(
            kwargs.get("latitude"),
            name="latitude",
            min_val=-90.0,
            max_val=90.0,
        )
        longitude = _validate_coordinate(
            kwargs.get("longitude"),
            name="longitude",
            min_val=-180.0,
            max_val=180.0,
        )
        params: dict[str, str | float] = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
        }

        if self._client is not None:
            response = await self._client.get(OPEN_METEO_FORECAST_URL, params=params)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(OPEN_METEO_FORECAST_URL, params=params)

        response.raise_for_status()
        data = response.json()
        return json.dumps(data)
