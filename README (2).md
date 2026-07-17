# AmpereX AI Module

The **AI module only** for AmpereX - AI-Powered Hybrid Renewable Energy
Management System. This does **not** include FastAPI routes, MQTT
ingestion, InfluxDB, the sensor simulator, or the React dashboard. It is a
standalone Python library meant to be imported by the FastAPI backend
(dummy/synthetic data is used here so it runs with zero external services).

## What it does

Given the current sensor snapshot (solar, wind, battery, load, grid) plus
historical sensor data and an Open-Meteo weather forecast, it returns one
structured JSON response containing:

1. **Forecast** - tomorrow's solar generation, wind generation, and campus
   demand (Prophet).
2. **Recommendation** - a single operational action (`CHARGE_BATTERY`,
   `DISCHARGE_BATTERY`, `USE_GRID`, `EXPORT_ENERGY`, `RUN_HEAVY_LOADS`,
   `REDUCE_LOAD`, or `MAINTAIN_CURRENT_STATE`), chosen by scoring every
   candidate action - not several independent rules firing at once.
3. **Explainability** - a human-readable explanation of *why* that action
   was chosen, with the actual numbers behind the decision.
4. **AI Insights** - proactive, forward-looking warnings/opportunities
   about conditions before they happen (battery depletion risk, an
   incoming solar drop, a wind lull, a grid-import spike, a good window
   for flexible loads).
5. **Impact Metrics** - estimated cost saved, carbon saved, renewable
   utilization %, grid dependency %, and a trees-equivalent figure.

## Project layout

```
ai_module/
  config.py               Battery limits, decision thresholds, forecast
                            settings, and impact-estimation assumptions
                            (tariffs, emission factor, tree absorption rate)
  schemas.py                Vendor-neutral common JSON contract (Pydantic)
  data_provider.py           History/weather source interfaces + dummy
                              (synthetic) data generator
  forecasting.py              Prophet models for solar_kw / wind_kw / load_kw
  schedule_simulator.py        Shared greedy battery-dispatch simulation used
                                by the decision engine, insights, and impact
  decision_engine.py            Scores every candidate action, picks ONE
  explainability.py              Human-readable explanation for the chosen action
  insights.py                    Proactive forward-looking warnings/opportunities
  impact.py                      Cost/carbon/renewable-utilization estimates
  pipeline.py                    Orchestration layer - what FastAPI imports
demo.py                    Standalone runnable demo (dummy data, no services needed)
tests/test_pipeline.py     Unit tests: forecasting shape, each decision-engine
                            action, insights, impact, and the full pipeline
requirements.txt
```

## Quick start

```bash
pip install -r requirements.txt
python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"   # first time only
python demo.py
pytest tests/ -v
```

`demo.py` generates dummy historical + weather data, trains the Prophet
models, and prints the full recommendation/explanation/insights/impact JSON.

## The vendor-neutral common JSON contract

Upstream (FastAPI backend / vendor adapters) normalizes every hardware
reading into this shape before it reaches the AI module -
`ai_module/schemas.py::CurrentState`:

```json
{
  "site_id": "campus_01",
  "timestamp": "2026-07-17T10:30:00Z",
  "solar": { "power_kw": 95.0 },
  "wind": { "power_kw": 18.0, "wind_speed_m_s": 6.2 },
  "battery": { "soc_percent": 55.0, "capacity_kwh": 500, "power_kw": 0.0, "state": "idle" },
  "load": { "power_kw": 70.0 },
  "grid": { "power_kw": 3.0, "direction": "import" }
}
```

## How the FastAPI backend should call this

```python
from ai_module.pipeline import AmpereXAIModule
from ai_module.data_provider import InfluxDBHistoryProvider, OpenMeteoForecastProvider

ai_module = AmpereXAIModule(
    history_provider=InfluxDBHistoryProvider(url=..., token=..., org=..., bucket="ampx"),
    weather_provider=OpenMeteoForecastProvider(),
)

# Run on a schedule (e.g. nightly cron), NOT per-request:
ai_module.refresh_models(site_id="campus_01", lookback_days=30)

# Called from a FastAPI route per request:
@app.post("/ai/report")
def get_report(current_state: dict, latitude: float, longitude: float):
    return ai_module.get_report(current_state, latitude, longitude)
```

`InfluxDBHistoryProvider` is a stub (raises `NotImplementedError`) - fill in
`fetch_history()` against your live InfluxDB bucket; the exact Flux query
shape and expected output columns are documented in `data_provider.py`.
`OpenMeteoForecastProvider` is fully implemented and hits the real
Open-Meteo API. `SyntheticDataProvider` (dummy data) implements both
interfaces and is what `demo.py`/tests use, so the module works standalone
before MQTT/InfluxDB exist.

If you'd rather not manage a class instance (e.g. a quick script, or a
route where you already have history/weather in hand), use the stateless
helper instead:

```python
from ai_module.pipeline import run_ai_module

report = run_ai_module(current_state, history_df, future_weather_df, horizon_hours=24)
```

## Example output shape

```json
{
  "site_id": "campus_01",
  "generated_at": "2026-07-17T10:30:00Z",
  "forecast": { "solar_kw": {...}, "wind_kw": {...}, "load_kw": {...} },
  "recommendation": {
    "action": "CHARGE_BATTERY",
    "priority": "MEDIUM",
    "recommended_value_kw": 43.0,
    "confidence": 0.87,
    "runner_ups": [ { "action": "MAINTAIN_CURRENT_STATE", "score": 1.0 } ]
  },
  "explanation": {
    "summary": "Charge the battery at ~43.0 kW - renewables currently exceed campus load and the battery still has headroom.",
    "details": [ "Solar 95.0 kW + wind 18.0 kW vs load 70.0 kW -> net surplus of 43.0 kW right now.", "..." ]
  },
  "ai_insights": [
    { "severity": "CRITICAL", "message": "Battery is projected to approach its minimum reserve (~18% SOC) around 02:00 UTC...", "valid_from": "...", "valid_until": "..." }
  ],
  "impact_metrics": {
    "renewable_utilization_percent": 100.0,
    "grid_dependency_percent": 49.4,
    "estimated_cost_saved_currency": 9411.28,
    "currency": "INR",
    "estimated_carbon_saved_kg": 964.66,
    "trees_equivalent": 16766.64
  }
}
```

## Notes on the decision engine

`decision_engine.py` scores every candidate action (0-100) using the
current sensor snapshot plus the near-term simulated schedule from
`schedule_simulator.py`, and returns the single highest-scoring action as
the `Recommendation`, with the next few runner-up candidates attached for
transparency (so "why THIS action and not that one" is always inspectable,
never a black box). All thresholds live in `config.py::DecisionThresholds`
so they can be tuned per campus without touching decision logic.

## Notes on impact metrics

Assumptions (grid tariff, export tariff, grid emission factor, tree CO2
absorption rate) live in `config.py::ImpactConfig` - replace them with your
actual campus tariff and your grid region's published emission factor for
a real deployment. `trees_equivalent` is expressed as an **annualized**
projection (if today's saving pattern repeated every day for a year) since
a single day's raw carbon saving would otherwise round to a fraction of a
tree and be hard to communicate on a dashboard - this is a simple,
clearly-labeled estimate for a hackathon demo, not a certified carbon
accounting methodology.

## Not included here (by design)

- FastAPI routes / HTTP layer
- MQTT ingestion, Mosquitto broker config
- InfluxDB schema/bucket setup
- Python Sensor Simulator
- React dashboard

These all consume this AI module as a library (`ai_module.pipeline`) - see
"How the FastAPI backend should call this" above.
