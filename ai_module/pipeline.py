"""
pipeline.py
------------
Orchestration layer - the ONLY module a FastAPI backend needs to import.
Ties together forecasting.py + decision_engine.py + explainability.py +
insights.py + impact.py into a small set of plain functions/one class,
returning JSON-serializable dicts.

Typical FastAPI usage:

    from ai_module.pipeline import AmpereXAIModule
    from ai_module.data_provider import InfluxDBHistoryProvider, OpenMeteoForecastProvider

    ai_module = AmpereXAIModule(
        history_provider=InfluxDBHistoryProvider(url=..., token=..., org=..., bucket="ampx"),
        weather_provider=OpenMeteoForecastProvider(),
    )

    # Run on a schedule (e.g. nightly cron), NOT per-request:
    ai_module.refresh_models(site_id="campus_01", lookback_days=30)

    # Called from a FastAPI route per request / polling interval:
    @app.post("/ai/recommendation")
    def get_recommendation(current_state: dict, latitude: float, longitude: float):
        return ai_module.get_report(current_state, latitude, longitude)

`get_report(...)` returns a dict shaped exactly like `schemas.AmpereXAIResponse`
(forecast + recommendation + explanation + ai_insights + impact_metrics) -
FastAPI can return it directly with zero extra transformation.

For quick scripts/notebooks/tests that don't want to manage a class
instance, module-level convenience functions are provided at the bottom
(`forecast_tomorrow`, `run_ai_module`) which take already-fetched
history/weather DataFrames directly - handy for demo.py and unit tests,
and usable with dummy data while the real MQTT/InfluxDB pipeline is still
being built.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from .config import FORECAST
from .data_provider import HistoryProvider, WeatherForecastProvider
from .decision_engine import DecisionEngine
from .explainability import explain
from .forecasting import EnergyForecaster
from .impact import compute_impact
from .insights import generate_insights
from .schemas import AmpereXAIResponse, CurrentState, ForecastResult


# ---------------------------------------------------------------------------
# Stateful class - what a FastAPI backend should instantiate once at startup
# ---------------------------------------------------------------------------

class AmpereXAIModule:
    def __init__(self, history_provider: HistoryProvider, weather_provider: WeatherForecastProvider):
        self.history_provider = history_provider
        self.weather_provider = weather_provider
        self.decision_engine = DecisionEngine()
        self._forecasters: dict[str, EnergyForecaster] = {}

    def refresh_models(self, site_id: str, lookback_days: int = 30) -> None:
        """(Re)train the Prophet models for a site. Cheap to run on a
        schedule (hourly/daily) rather than per-request."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        history = self.history_provider.fetch_history(site_id, start, end)
        self._forecasters[site_id] = EnergyForecaster().train(history)

    def get_report(
        self,
        current_state: dict,
        latitude: float,
        longitude: float,
        horizon_hours: Optional[int] = None,
    ) -> dict:
        """
        current_state: dict matching schemas.CurrentState (from MQTT ->
        FastAPI -> normalized reading, or dummy data during development).

        Returns a dict matching schemas.AmpereXAIResponse.
        """
        state = CurrentState.model_validate(current_state)
        horizon = horizon_hours or FORECAST.default_horizon_hours

        if state.site_id not in self._forecasters:
            raise RuntimeError(
                f"No trained model for site_id='{state.site_id}'. "
                f"Call refresh_models('{state.site_id}') first."
            )

        future_weather = self.weather_provider.fetch_forecast(latitude, longitude, horizon)
        forecast = self._forecasters[state.site_id].predict(state.site_id, horizon, future_weather)

        response = _build_response(state, forecast)
        return response.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Stateless helpers - convenient for demo.py, notebooks, and unit tests where
# history/weather DataFrames are already on hand (e.g. dummy/synthetic data)
# ---------------------------------------------------------------------------

def forecast_tomorrow(site_id: str, history: pd.DataFrame, future_weather: pd.DataFrame,
                       horizon_hours: int = 24) -> ForecastResult:
    """Trains fresh Prophet models on `history` and forecasts `horizon_hours` ahead."""
    forecaster = EnergyForecaster().train(history)
    return forecaster.predict(site_id, horizon_hours, future_weather)


def _build_response(current: CurrentState, forecast: ForecastResult) -> AmpereXAIResponse:
    recommendation, schedule = DecisionEngine().decide(current, forecast)
    explanation = explain(current, recommendation, schedule)
    ai_insights = generate_insights(forecast, schedule)
    impact_metrics = compute_impact(schedule)

    return AmpereXAIResponse(
        site_id=current.site_id,
        generated_at=datetime.now(timezone.utc),
        forecast=forecast,
        recommendation=recommendation,
        explanation=explanation,
        ai_insights=ai_insights,
        impact_metrics=impact_metrics,
    )


def run_ai_module(current_state: dict, history: pd.DataFrame, future_weather: pd.DataFrame,
                   horizon_hours: int = 24) -> dict:
    """
    One-shot convenience function: train on `history`, forecast, decide,
    explain, generate insights, and estimate impact - all in one call.
    Handy for a quick FastAPI route, a notebook, or a test, when you already
    have history/weather data (real or dummy) in hand.

    Returns a dict matching schemas.AmpereXAIResponse.
    """
    state = CurrentState.model_validate(current_state)
    forecast = forecast_tomorrow(state.site_id, history, future_weather, horizon_hours)
    response = _build_response(state, forecast)
    return response.model_dump(mode="json")
