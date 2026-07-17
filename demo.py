"""
demo.py
--------
Standalone, runnable demonstration of the AmpereX AI Module using dummy
(synthetic) sensor/weather data - no MQTT, InfluxDB, or FastAPI required.

Run:
    python demo.py

This calls `ai_module.pipeline.run_ai_module(...)` exactly the way a
FastAPI route would once real history/weather data is available - only the
data source is swapped (SyntheticDataProvider instead of InfluxDB/Open-Meteo).
"""

import json
from datetime import datetime, timedelta, timezone

from ai_module.data_provider import SyntheticDataProvider
from ai_module.pipeline import run_ai_module

SITE_ID = "campus_01"
LATITUDE, LONGITUDE = 12.9716, 79.9700  # example campus coordinates
HORIZON_HOURS = 24
TRAINING_DAYS = 21


def main() -> None:
    provider = SyntheticDataProvider(seed=7)

    # --- Dummy historical sensor data (stand-in for InfluxDB) ------------------
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=TRAINING_DAYS)
    history = provider.fetch_history(SITE_ID, start, end)
    print(f"Generated {len(history)}h of dummy training history "
          f"({start.date()} -> {end.date()})")

    # --- Dummy weather forecast (stand-in for Open-Meteo) -----------------------
    future_weather = provider.fetch_forecast(LATITUDE, LONGITUDE, HORIZON_HOURS)

    # --- Dummy "current sensor snapshot" (stand-in for MQTT/FastAPI/InfluxDB) ---
    current_state = provider.current_snapshot(SITE_ID)
    # Nudge it into an interesting midday-surplus scenario for the demo:
    current_state["solar"]["power_kw"] = 95.0
    current_state["wind"]["power_kw"] = 18.0
    current_state["load"]["power_kw"] = 70.0
    current_state["battery"]["soc_percent"] = 55.0
    current_state["grid"]["power_kw"] = 3.0

    print("\nCurrent sensor snapshot fed into the AI module:")
    print(json.dumps(current_state, indent=2, default=str))

    # --- Run the whole AI module in one call ------------------------------------
    print("\nTraining Prophet models and running the decision engine...\n")
    report = run_ai_module(current_state, history, future_weather, horizon_hours=HORIZON_HOURS)

    print("=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print(json.dumps(report["recommendation"], indent=2))

    print("\n" + "=" * 70)
    print("EXPLANATION")
    print("=" * 70)
    print(json.dumps(report["explanation"], indent=2))

    print("\n" + "=" * 70)
    print("AI INSIGHTS")
    print("=" * 70)
    print(json.dumps(report["ai_insights"], indent=2))

    print("\n" + "=" * 70)
    print("IMPACT METRICS")
    print("=" * 70)
    print(json.dumps(report["impact_metrics"], indent=2))

    print("\n" + "=" * 70)
    print("FORECAST (first 3 hours only, full response has all 24h)")
    print("=" * 70)
    trimmed_forecast = {
        "site_id": report["forecast"]["site_id"],
        "horizon_hours": report["forecast"]["horizon_hours"],
        "solar_kw": {**report["forecast"]["solar_kw"], "points": report["forecast"]["solar_kw"]["points"][:3]},
        "wind_kw": {**report["forecast"]["wind_kw"], "points": report["forecast"]["wind_kw"]["points"][:3]},
        "load_kw": {**report["forecast"]["load_kw"], "points": report["forecast"]["load_kw"]["points"][:3]},
    }
    print(json.dumps(trimmed_forecast, indent=2))


if __name__ == "__main__":
    main()
