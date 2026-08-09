"""
Weather data fetcher using the Open-Meteo Forecast API.

Retrieves current weather conditions (temperature, cloud cover, wind speed,
humidity, weather code) for the configured geographic coordinates. Includes
retry logic with exponential backoff and comprehensive error handling.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from config import (
    LATITUDE,
    LONGITUDE,
    OPEN_METEO_BASE_URL,
    WEATHER_FETCH_TIMEOUT,
    WEATHER_RETRY_ATTEMPTS,
    WEATHER_RETRY_DELAY,
)
from utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class WeatherData:
    """Container for current weather observations.

    Attributes:
        temperature_c: Air temperature in degrees Celsius.
        cloud_cover_pct: Cloud cover as a percentage (0–100).
        wind_speed_kmh: Wind speed in kilometers per hour.
        humidity_pct: Relative humidity as a percentage (0–100).
        weather_code: WMO weather interpretation code.
        is_valid: Whether the data was successfully fetched.
    """

    temperature_c: float = 25.0
    cloud_cover_pct: float = 50.0
    wind_speed_kmh: float = 10.0
    humidity_pct: float = 60.0
    weather_code: int = 0
    is_valid: bool = False


class WeatherFetcher:
    """Fetches live weather data from the Open-Meteo API.

    Implements retry logic with exponential backoff to handle transient
    network failures. Falls back to the last known good reading when
    the API is unreachable.

    Attributes:
        latitude: Geographic latitude for weather queries.
        longitude: Geographic longitude for weather queries.
    """

    def __init__(
        self,
        latitude: float = LATITUDE,
        longitude: float = LONGITUDE,
    ) -> None:
        """Initialize the weather fetcher.

        Args:
            latitude: Latitude of the campus location.
            longitude: Longitude of the campus location.
        """
        self.latitude = latitude
        self.longitude = longitude
        self._last_valid: WeatherData = WeatherData()

        logger.info(
            "WeatherFetcher initialized for (%.4f, %.4f)",
            self.latitude,
            self.longitude,
        )

    def fetch(self) -> WeatherData:
        """Fetch current weather data from Open-Meteo.

        Retries up to WEATHER_RETRY_ATTEMPTS times with exponential
        backoff on failure. Returns the last known good data if all
        retries are exhausted.

        Returns:
            WeatherData with current conditions (or fallback values).
        """
        params: dict[str, Any] = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current_weather": True,
            "hourly": "cloud_cover,relative_humidity_2m",
            "forecast_days": 1,
        }

        for attempt in range(1, WEATHER_RETRY_ATTEMPTS + 1):
            try:
                response = requests.get(
                    OPEN_METEO_BASE_URL,
                    params=params,
                    timeout=WEATHER_FETCH_TIMEOUT,
                )
                response.raise_for_status()

                data = response.json()
                weather = self._parse_response(data)

                if weather.is_valid:
                    self._last_valid = weather
                    logger.info(
                        "Weather fetched: %.1f°C | Cloud: %.0f%% | "
                        "Wind: %.1f km/h | Humidity: %.0f%%",
                        weather.temperature_c,
                        weather.cloud_cover_pct,
                        weather.wind_speed_kmh,
                        weather.humidity_pct,
                    )
                    return weather

                logger.warning(
                    "Attempt %d/%d: Invalid API response structure",
                    attempt,
                    WEATHER_RETRY_ATTEMPTS,
                )

            except requests.exceptions.Timeout:
                logger.warning(
                    "Attempt %d/%d: Request timed out after %ds",
                    attempt,
                    WEATHER_RETRY_ATTEMPTS,
                    WEATHER_FETCH_TIMEOUT,
                )
            except requests.exceptions.ConnectionError:
                logger.warning(
                    "Attempt %d/%d: Connection error (broker/network down?)",
                    attempt,
                    WEATHER_RETRY_ATTEMPTS,
                )
            except requests.exceptions.HTTPError as exc:
                logger.warning(
                    "Attempt %d/%d: HTTP %s",
                    attempt,
                    WEATHER_RETRY_ATTEMPTS,
                    exc,
                )
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "Attempt %d/%d: Response parsing failed: %s",
                    attempt,
                    WEATHER_RETRY_ATTEMPTS,
                    exc,
                )

            if attempt < WEATHER_RETRY_ATTEMPTS:
                backoff = WEATHER_RETRY_DELAY * (2 ** (attempt - 1))
                logger.info("Retrying in %.1f seconds...", backoff)
                time.sleep(backoff)

        logger.error(
            "All %d weather fetch attempts failed. Using last known data.",
            WEATHER_RETRY_ATTEMPTS,
        )
        return self._last_valid

    def _parse_response(self, data: dict[str, Any]) -> WeatherData:
        """Parse the Open-Meteo JSON response into a WeatherData object.

        Extracts current weather fields and matches the closest hourly
        cloud cover and humidity values to the current time index.

        Args:
            data: Raw JSON response dictionary from Open-Meteo.

        Returns:
            Populated WeatherData instance with is_valid=True on success.

        Raises:
            KeyError: If expected keys are missing from the response.
            ValueError: If data types are unexpected.
        """
        current = data["current_weather"]
        hourly = data.get("hourly", {})

        # Determine current hour index for hourly data
        from utils import get_local_hour

        hour_index = get_local_hour()

        # Extract cloud cover from hourly data
        cloud_cover_list = hourly.get("cloud_cover", [])
        cloud_cover = (
            float(cloud_cover_list[hour_index])
            if hour_index < len(cloud_cover_list)
            else 50.0
        )

        # Extract humidity from hourly data
        humidity_list = hourly.get("relative_humidity_2m", [])
        humidity = (
            float(humidity_list[hour_index])
            if hour_index < len(humidity_list)
            else 60.0
        )

        return WeatherData(
            temperature_c=float(current["temperature"]),
            cloud_cover_pct=cloud_cover,
            wind_speed_kmh=float(current["windspeed"]),
            humidity_pct=humidity,
            weather_code=int(current["weathercode"]),
            is_valid=True,
        )
