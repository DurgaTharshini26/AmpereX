"""
forecasting.py
---------------
Prophet-based forecasting for the three signals the Optimization Engine
needs to look ahead on:

    - Future Solar Generation (kW)
    - Future Wind Generation (kW)
    - Future Campus Load (kW)

Design notes
------------
* One independent Prophet model per signal. Solar/wind/load have very
  different drivers, so a single multivariate model would fight itself;
  three specialized models are simpler to reason about and tune.

* Weather is passed in as Prophet *extra regressors* rather than baked into
  seasonality, because the whole point of the upstream Open-Meteo feed is
  that weather (cloud cover, wind speed, temperature) is genuinely
  predictive and known in advance for the forecast horizon.

    - solar_kw   <- cloud_cover_percent, shortwave_radiation_w_m2 (if present)
    - wind_kw    <- wind_speed_m_s
    - load_kw    <- temperature_c (heating/cooling demand proxy)

* Daily + weekly seasonality is left on (captures the solar day/night curve
  and weekday/weekend campus load pattern). Yearly seasonality defaults to
  off in config.py because it needs a full year of history to be reliable -
  flip it on once enough historical data has accumulated in InfluxDB.

* Output is shaped directly into the `schemas.ForecastResult` common
  contract so the FastAPI layer can serialize it without any translation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from prophet import Prophet

from .config import FORECAST
from .schemas import ForecastPoint, MetricForecast, ForecastResult

# Prophet/cmdstanpy are chatty by default - keep the demo output readable.
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


REGRESSORS = {
    "solar_kw": ["cloud_cover_percent"],
    "wind_kw": ["wind_speed_m_s"],
    "load_kw": ["temperature_c"],
}


class SignalForecaster:
    """Wraps a single Prophet model for one signal (solar, wind, or load)."""

    def __init__(self, metric: str):
        if metric not in REGRESSORS:
            raise ValueError(f"Unknown metric '{metric}', expected one of {list(REGRESSORS)}")
        self.metric = metric
        self.regressors = REGRESSORS[metric]
        self.model: Prophet | None = None

    def fit(self, history: pd.DataFrame) -> "SignalForecaster":
        """
        history: DataFrame with columns ['timestamp', <metric>, *regressors]
        """
        df = pd.DataFrame({
            "ds": pd.to_datetime(history["timestamp"]).dt.tz_localize(None),
            "y": history[self.metric].astype(float),
        })
        for reg in self.regressors:
            df[reg] = history[reg].astype(float)

        model = Prophet(
            daily_seasonality=FORECAST.daily_seasonality,
            weekly_seasonality=FORECAST.weekly_seasonality,
            yearly_seasonality=FORECAST.yearly_seasonality,
            interval_width=FORECAST.interval_width,
        )
        for reg in self.regressors:
            model.add_regressor(reg)

        model.fit(df)
        self.model = model
        return self

    def predict(self, horizon_hours: int, future_weather: pd.DataFrame) -> MetricForecast:
        """
        future_weather: DataFrame with ['timestamp', *regressors] covering at
        least `horizon_hours` hourly steps starting from "now".
        """
        if self.model is None:
            raise RuntimeError(f"SignalForecaster({self.metric}) has not been fit yet")

        future = pd.DataFrame({
            "ds": pd.to_datetime(future_weather["timestamp"]).dt.tz_localize(None).iloc[:horizon_hours],
        })
        for reg in self.regressors:
            future[reg] = future_weather[reg].astype(float).iloc[:horizon_hours].values

        forecast = self.model.predict(future)

        # Solar/wind/load can never physically be negative - Prophet's linear
        # trend + seasonality can dip below zero, especially overnight for
        # solar. Clip at the schema boundary, not inside Prophet.
        forecast[["yhat", "yhat_lower", "yhat_upper"]] = forecast[
            ["yhat", "yhat_lower", "yhat_upper"]
        ].clip(lower=0)

        points = [
            ForecastPoint(
                timestamp=row.ds.to_pydatetime().replace(tzinfo=timezone.utc),
                yhat=round(float(row.yhat), 3),
                yhat_lower=round(float(row.yhat_lower), 3),
                yhat_upper=round(float(row.yhat_upper), 3),
            )
            for row in forecast.itertuples()
        ]
        return MetricForecast(metric=self.metric, points=points)


class EnergyForecaster:
    """
    Trains and serves all three forecasts (solar, wind, load) together.
    This is the class the rest of the pipeline (pipeline.py) talks to.
    """

    def __init__(self):
        self.forecasters = {metric: SignalForecaster(metric) for metric in REGRESSORS}

    def train(self, history: pd.DataFrame) -> "EnergyForecaster":
        """
        history: output of a HistoryProvider.fetch_history(...) call -
        must contain columns ['timestamp', 'solar_kw', 'wind_kw', 'load_kw',
        'temperature_c', 'cloud_cover_percent', 'wind_speed_m_s'].
        """
        required = {"timestamp", "solar_kw", "wind_kw", "load_kw",
                    "temperature_c", "cloud_cover_percent", "wind_speed_m_s"}
        missing = required - set(history.columns)
        if missing:
            raise ValueError(f"History is missing required columns: {missing}")

        for metric, forecaster in self.forecasters.items():
            forecaster.fit(history)
        return self

    def predict(self, site_id: str, horizon_hours: int,
                future_weather: pd.DataFrame) -> ForecastResult:
        """
        future_weather: DataFrame with ['timestamp', 'temperature_c',
        'cloud_cover_percent', 'wind_speed_m_s'] covering `horizon_hours`.
        Typically sourced from OpenMeteoForecastProvider in production, or
        SyntheticDataProvider.fetch_forecast(...) for local dev/demo.
        """
        results = {
            metric: forecaster.predict(horizon_hours, future_weather)
            for metric, forecaster in self.forecasters.items()
        }
        return ForecastResult(
            site_id=site_id,
            generated_at=datetime.now(timezone.utc),
            horizon_hours=horizon_hours,
            solar_kw=results["solar_kw"],
            wind_kw=results["wind_kw"],
            load_kw=results["load_kw"],
        )
