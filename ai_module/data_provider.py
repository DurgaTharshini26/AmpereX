"""
data_provider.py
-----------------
The AI Engine does not own historical data - upstream components
(Python Sensor Simulator -> MQTT -> FastAPI -> InfluxDB) do. This module
defines the *interface* the AI Engine expects historical data to come
through, plus:

  - `InfluxDBHistoryProvider`: a thin adapter stub to be completed by
    whoever wires this engine into the real InfluxDB instance. Kept here
    (rather than assumed) so the AI Engine can be developed, tested and
    demoed with zero external services running.

  - `OpenMeteoForecastProvider`: a real, working adapter for fetching future
    weather (used as Prophet regressors for the forecast horizon). Uses the
    same Open-Meteo API the Python Sensor Simulator is fed from upstream.

  - `SyntheticDataProvider`: generates a realistic synthetic history
    (solar / wind / load / weather) so `demo.py` and the test suite can run
    completely standalone. This mirrors the physics-based logic the
    "Python Sensor Simulator" uses, just re-implemented here for local
    development of the AI Engine only.

All providers return plain pandas DataFrames with a `timestamp` column
plus one column per signal - this is the internal working format. Only
at the API boundary (schemas.py) does data get wrapped into the common
JSON contract.
"""

from __future__ import annotations

import abc
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

class HistoryProvider(abc.ABC):
    """Abstract source of historical sensor + weather data for training Prophet."""

    @abc.abstractmethod
    def fetch_history(self, site_id: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Returns a DataFrame indexed by hourly timestamp with columns:
        ['timestamp', 'solar_kw', 'wind_kw', 'load_kw',
         'temperature_c', 'cloud_cover_percent', 'wind_speed_m_s']
        """
        raise NotImplementedError


class WeatherForecastProvider(abc.ABC):
    """Abstract source of *future* weather, used as Prophet regressors."""

    @abc.abstractmethod
    def fetch_forecast(self, latitude: float, longitude: float, hours: int) -> pd.DataFrame:
        """
        Returns a DataFrame with columns:
        ['timestamp', 'temperature_c', 'cloud_cover_percent', 'wind_speed_m_s',
         'shortwave_radiation_w_m2']
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Real adapters (to be finished by whoever owns the infra in this project)
# ---------------------------------------------------------------------------

class InfluxDBHistoryProvider(HistoryProvider):
    """
    Adapter stub for pulling historical sensor readings out of InfluxDB.

    Not implemented here because this component (AI Engine) is scoped to
    NOT include the backend/DB layer. Wire this up with the `influxdb-client`
    package once the FastAPI backend + InfluxDB are available, e.g.:

        from influxdb_client import InfluxDBClient
        client = InfluxDBClient(url=..., token=..., org=...)
        query_api = client.query_api()
        flux = f'''
          from(bucket: "ampx")
            |> range(start: {start.isoformat()}, stop: {end.isoformat()})
            |> filter(fn: (r) => r.site_id == "{site_id}")
        '''
        tables = query_api.query_data_frame(flux)
        # ... pivot into the common columns documented in HistoryProvider ...
    """

    def __init__(self, url: str, token: str, org: str, bucket: str):
        self.url, self.token, self.org, self.bucket = url, token, org, bucket

    def fetch_history(self, site_id: str, start: datetime, end: datetime) -> pd.DataFrame:
        raise NotImplementedError(
            "InfluxDBHistoryProvider is a stub - implement fetch_history() against "
            "your live InfluxDB bucket. The AI Engine only requires the DataFrame "
            "shape documented on HistoryProvider.fetch_history."
        )


class OpenMeteoForecastProvider(WeatherForecastProvider):
    """
    Real adapter for Open-Meteo's free forecast API (no API key required).
    This is the same public data source the upstream Python Sensor Simulator
    consumes, so forecast-time weather regressors line up with how the
    training data's weather columns were derived.
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def fetch_forecast(self, latitude: float, longitude: float, hours: int) -> pd.DataFrame:
        import requests  # local import: optional dependency, only needed here

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,cloud_cover,wind_speed_10m,shortwave_radiation",
            "forecast_hours": hours,
            "timezone": "UTC",
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
        return pd.DataFrame({
            "timestamp": pd.to_datetime(hourly["time"], utc=True),
            "temperature_c": hourly["temperature_2m"],
            "cloud_cover_percent": hourly["cloud_cover"],
            "wind_speed_m_s": hourly["wind_speed_10m"],
            "shortwave_radiation_w_m2": hourly["shortwave_radiation"],
        })


# ---------------------------------------------------------------------------
# Synthetic provider - for local development, unit tests and the demo script
# ---------------------------------------------------------------------------

class SyntheticDataProvider(HistoryProvider, WeatherForecastProvider):
    """
    Generates physically-plausible synthetic history so the forecasting and
    optimization logic can be built/tested/demoed without any live MQTT
    broker, InfluxDB, or physical sensors.

    Solar: bell-curve daylight profile modulated by cloud cover.
    Wind:  diurnal-ish pattern with noise, floor at 0.
    Load:  campus-shaped weekday/weekend + morning/evening peaks.
    Weather: synthetic temperature/cloud/wind consistent with the above.
    """

    def __init__(self, seed: int = 42,
                 solar_capacity_kw: float = 150.0,
                 wind_capacity_kw: float = 80.0,
                 base_load_kw: float = 90.0):
        self.rng = np.random.default_rng(seed)
        self.solar_capacity_kw = solar_capacity_kw
        self.wind_capacity_kw = wind_capacity_kw
        self.base_load_kw = base_load_kw

    # -- internal physics-ish helpers -------------------------------------

    def _cloud_cover_series(self, n_hours: int) -> np.ndarray:
        # Slow-moving cloud cover (0-100%), autocorrelated via random walk + clipping
        walk = np.cumsum(self.rng.normal(0, 6, n_hours))
        cloud = 40 + walk
        return np.clip(cloud, 0, 100)

    def _temperature_series(self, timestamps: pd.DatetimeIndex) -> np.ndarray:
        hour = timestamps.hour.values
        day_of_year = timestamps.dayofyear.values
        seasonal = 8 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
        diurnal = 6 * np.sin(2 * np.pi * (hour - 9) / 24)
        return 24 + seasonal + diurnal + self.rng.normal(0, 1.0, len(timestamps))

    def _wind_speed_series(self, n_hours: int) -> np.ndarray:
        walk = np.cumsum(self.rng.normal(0, 0.3, n_hours))
        speed = 5 + walk
        return np.clip(speed, 0, None)

    def _solar_kw_series(self, timestamps: pd.DatetimeIndex, cloud_cover: np.ndarray) -> np.ndarray:
        hour = timestamps.hour.values + timestamps.minute.values / 60.0
        # Daylight bell curve between ~06:00 and ~18:30, peak at solar noon
        daylight = np.clip(np.sin(np.pi * (hour - 6) / 12.5), 0, None)
        cloud_factor = 1 - 0.75 * (cloud_cover / 100.0)
        solar = self.solar_capacity_kw * daylight * cloud_factor
        solar *= (1 + self.rng.normal(0, 0.03, len(timestamps)))
        return np.clip(solar, 0, self.solar_capacity_kw)

    def _wind_kw_series(self, wind_speed: np.ndarray) -> np.ndarray:
        # Simple cubic-ish power curve, saturating at rated capacity
        cut_in, rated = 3.0, 12.0
        frac = np.clip((wind_speed - cut_in) / (rated - cut_in), 0, 1) ** 2
        wind = self.wind_capacity_kw * frac
        wind *= (1 + self.rng.normal(0, 0.05, len(wind_speed)))
        return np.clip(wind, 0, self.wind_capacity_kw)

    def _load_kw_series(self, timestamps: pd.DatetimeIndex) -> np.ndarray:
        hour = timestamps.hour.values + timestamps.minute.values / 60.0
        is_weekend = timestamps.dayofweek.values >= 5
        # Two peaks: ~09:00 and ~19:00, lower overnight, lower on weekends
        morning = 22 * np.exp(-0.5 * ((hour - 9.5) / 2.4) ** 2)
        evening = 16 * np.exp(-0.5 * ((hour - 19) / 2.8) ** 2)
        midday = 10 * np.exp(-0.5 * ((hour - 13) / 3.5) ** 2)
        weekday_load = self.base_load_kw + morning + evening + midday
        weekend_load = self.base_load_kw * 0.55 + 0.4 * (morning + evening + midday)
        load = np.where(is_weekend, weekend_load, weekday_load)
        load *= (1 + self.rng.normal(0, 0.04, len(timestamps)))
        return np.clip(load, self.base_load_kw * 0.3, None)

    # -- public interface ---------------------------------------------------

    def fetch_history(self, site_id: str, start: datetime, end: datetime) -> pd.DataFrame:
        timestamps = pd.date_range(start, end, freq="h", tz=timezone.utc)
        n = len(timestamps)
        cloud = self._cloud_cover_series(n)
        wind_speed = self._wind_speed_series(n)
        temperature = self._temperature_series(timestamps)
        solar_kw = self._solar_kw_series(timestamps, cloud)
        wind_kw = self._wind_kw_series(wind_speed)
        load_kw = self._load_kw_series(timestamps)

        return pd.DataFrame({
            "timestamp": timestamps,
            "solar_kw": solar_kw,
            "wind_kw": wind_kw,
            "load_kw": load_kw,
            "temperature_c": temperature,
            "cloud_cover_percent": cloud,
            "wind_speed_m_s": wind_speed,
        })

    def fetch_forecast(self, latitude: float, longitude: float, hours: int) -> pd.DataFrame:
        # Signature kept identical to OpenMeteoForecastProvider so the two
        # are drop-in interchangeable; lat/lon are accepted but unused here
        # since this is a synthetic generator (kept for interface parity).
        start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=hours - 1)
        timestamps = pd.date_range(start, end, freq="h", tz=timezone.utc)
        n = len(timestamps)
        cloud = self._cloud_cover_series(n)
        wind_speed = self._wind_speed_series(n)
        temperature = self._temperature_series(timestamps)
        # rough proxy for shortwave radiation, useful only as a regressor
        hour = timestamps.hour.values + timestamps.minute.values / 60.0
        daylight = np.clip(np.sin(np.pi * (hour - 6) / 12.5), 0, None)
        radiation = 900 * daylight * (1 - 0.75 * (cloud / 100.0))

        return pd.DataFrame({
            "timestamp": timestamps,
            "temperature_c": temperature,
            "cloud_cover_percent": cloud,
            "wind_speed_m_s": wind_speed,
            "shortwave_radiation_w_m2": radiation,
        })

    def current_snapshot(self, site_id: str) -> dict:
        """Convenience helper: produce a single 'right now' reading matching
        the CurrentState schema, for demo purposes."""
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        hist = self.fetch_history(site_id, now - timedelta(hours=1), now)
        row = hist.iloc[-1]
        return {
            "site_id": site_id,
            "timestamp": row["timestamp"].isoformat(),
            "solar": {"power_kw": round(float(row["solar_kw"]), 2)},
            "wind": {"power_kw": round(float(row["wind_kw"]), 2),
                     "wind_speed_m_s": round(float(row["wind_speed_m_s"]), 2)},
            "battery": {"soc_percent": 55.0, "capacity_kwh": 500.0, "power_kw": 0.0, "state": "idle"},
            "load": {"power_kw": round(float(row["load_kw"]), 2)},
            "grid": {"power_kw": 10.0, "direction": "import"},
            "weather": {
                "temperature_c": round(float(row["temperature_c"]), 1),
                "cloud_cover_percent": round(float(row["cloud_cover_percent"]), 1),
                "wind_speed_m_s": round(float(row["wind_speed_m_s"]), 2),
            },
        }
