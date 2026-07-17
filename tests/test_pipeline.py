"""
test_pipeline.py
------------------
Sanity tests for the AmpereX AI Module:
  1. Forecasting produces well-formed, physically valid output.
  2. The decision engine picks the expected single action under each
     canonical scenario (surplus/deficit/full-battery/low-battery/etc.).
  3. Insights fire under the conditions they're designed to catch.
  4. Impact metrics compute sane values.
  5. The full pipeline (run_ai_module) produces valid, JSON-serializable
     output matching the AmpereXAIResponse contract.

Hand-built ForecastResult/CurrentState fixtures are used for the decision
engine / insights / impact tests so they're fast and independent of
Prophet training.
"""

from datetime import datetime, timedelta, timezone

from ai_module.data_provider import SyntheticDataProvider
from ai_module.decision_engine import DecisionEngine
from ai_module.impact import compute_impact
from ai_module.insights import generate_insights
from ai_module.pipeline import run_ai_module
from ai_module.schemas import (
    ActionType, BatteryReading, CurrentState, ForecastPoint, ForecastResult,
    GridReading, LoadReading, MetricForecast, SolarReading, WindReading,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_forecast(site_id: str, solar_series, wind_series, load_series) -> ForecastResult:
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    def to_metric(name, series):
        points = [
            ForecastPoint(timestamp=start + timedelta(hours=i),
                          yhat=v, yhat_lower=max(0, v - 5), yhat_upper=v + 5)
            for i, v in enumerate(series)
        ]
        return MetricForecast(metric=name, points=points)

    return ForecastResult(
        site_id=site_id, generated_at=start, horizon_hours=len(solar_series),
        solar_kw=to_metric("solar_kw", solar_series),
        wind_kw=to_metric("wind_kw", wind_series),
        load_kw=to_metric("load_kw", load_series),
    )


def make_state(solar, wind, load, soc, grid_kw, grid_dir="import") -> CurrentState:
    return CurrentState(
        site_id="campus_01",
        timestamp=datetime.now(timezone.utc),
        solar=SolarReading(power_kw=solar),
        wind=WindReading(power_kw=wind),
        battery=BatteryReading(soc_percent=soc, capacity_kwh=500.0, power_kw=0.0),
        load=LoadReading(power_kw=load),
        grid=GridReading(power_kw=grid_kw, direction=grid_dir),
    )


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def test_forecaster_produces_valid_shapes():
    from ai_module.forecasting import EnergyForecaster

    provider = SyntheticDataProvider(seed=1)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    history = provider.fetch_history("campus_test", end - timedelta(days=14), end)
    forecaster = EnergyForecaster().train(history)
    weather = provider.fetch_forecast(0.0, 0.0, hours=12)
    forecast = forecaster.predict("campus_test", 12, weather)

    assert forecast.horizon_hours == 12
    for mf in (forecast.solar_kw, forecast.wind_kw, forecast.load_kw):
        assert len(mf.points) == 12
        for pt in mf.points:
            assert pt.yhat >= 0 and pt.yhat_lower >= 0 and pt.yhat_upper >= pt.yhat_lower


# ---------------------------------------------------------------------------
# Decision engine - one scenario per action
# ---------------------------------------------------------------------------

def test_charge_battery_wins_on_surplus_with_headroom():
    state = make_state(solar=90, wind=10, load=60, soc=50, grid_kw=0)
    forecast = make_forecast("campus_01", [80] * 24, [10] * 24, [60] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.charge_battery


def test_export_energy_wins_when_battery_full():
    state = make_state(solar=90, wind=10, load=60, soc=92, grid_kw=0)
    forecast = make_forecast("campus_01", [80] * 24, [10] * 24, [60] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.export_energy


def test_discharge_battery_wins_on_deficit_with_battery_available():
    state = make_state(solar=5, wind=2, load=60, soc=70, grid_kw=53)
    forecast = make_forecast("campus_01", [5] * 24, [2] * 24, [60] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.discharge_battery


def test_use_grid_wins_on_deficit_with_battery_low():
    # Deficit + low SOC, but grid import itself is still modest (below the
    # high_grid_import_kw threshold) so REDUCE_LOAD's stricter condition
    # doesn't also fire - isolates USE_GRID.
    state = make_state(solar=5, wind=2, load=25, soc=20, grid_kw=10)
    forecast = make_forecast("campus_01", [5] * 24, [2] * 24, [25] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.use_grid


def test_reduce_load_wins_on_severe_deficit_high_grid_import_low_battery():
    state = make_state(solar=2, wind=1, load=95, soc=12, grid_kw=92)
    forecast = make_forecast("campus_01", [2] * 24, [1] * 24, [95] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.reduce_load


def test_maintain_current_state_when_balanced():
    state = make_state(solar=30, wind=5, load=35, soc=60, grid_kw=0)
    forecast = make_forecast("campus_01", [30] * 24, [5] * 24, [35] * 24)
    rec, _ = DecisionEngine().decide(state, forecast)
    assert rec.action == ActionType.maintain_current_state


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def test_battery_depletion_insight_fires():
    state = make_state(solar=5, wind=2, load=90, soc=40, grid_kw=0)
    forecast = make_forecast("campus_01", [5] * 24, [2] * 24, [90] * 24)
    _, schedule = DecisionEngine().decide(state, forecast)
    insights = generate_insights(forecast, schedule)
    assert any(i.severity == "CRITICAL" for i in insights)


def test_surplus_opportunity_insight_fires():
    state = make_state(solar=20, wind=5, load=25, soc=90, grid_kw=0)
    forecast = make_forecast("campus_01", [120] * 24, [20] * 24, [30] * 24)
    _, schedule = DecisionEngine().decide(state, forecast)
    insights = generate_insights(forecast, schedule)
    assert any(i.severity == "OPPORTUNITY" for i in insights)


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------

def test_impact_metrics_are_sane():
    state = make_state(solar=90, wind=10, load=60, soc=50, grid_kw=0)
    forecast = make_forecast("campus_01", [80] * 24, [10] * 24, [60] * 24)
    _, schedule = DecisionEngine().decide(state, forecast)
    impact = compute_impact(schedule)
    assert 0 <= impact.renewable_utilization_percent <= 100
    assert 0 <= impact.grid_dependency_percent <= 100
    assert impact.estimated_carbon_saved_kg >= 0
    assert impact.trees_equivalent >= 0


# ---------------------------------------------------------------------------
# Full pipeline (dummy data end-to-end)
# ---------------------------------------------------------------------------

def test_run_ai_module_end_to_end_with_dummy_data():
    provider = SyntheticDataProvider(seed=3)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    history = provider.fetch_history("campus_e2e", end - timedelta(days=14), end)
    future_weather = provider.fetch_forecast(0.0, 0.0, hours=24)
    current_state = provider.current_snapshot("campus_e2e")

    report = run_ai_module(current_state, history, future_weather, horizon_hours=24)

    assert report["site_id"] == "campus_e2e"
    assert "forecast" in report and "recommendation" in report
    assert "explanation" in report and "ai_insights" in report and "impact_metrics" in report
    assert report["recommendation"]["action"] in {a.value for a in ActionType}
    assert len(report["forecast"]["solar_kw"]["points"]) == 24
