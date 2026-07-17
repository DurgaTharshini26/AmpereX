"""
explainability.py
-------------------
Turns the DecisionEngine's chosen action into a human-readable explanation,
using the actual numbers behind the decision rather than a generic template.
This is what gets shown on the dashboard next to the recommendation so a
campus facilities operator (not a data scientist) can trust *why* the AI
suggested it.

Kept as its own module (rather than string-building inline in
decision_engine.py) so the "reasoning" logic and the "wording" logic can
evolve independently - e.g. swapping in multi-language templates later
without touching the scoring code at all.
"""

from __future__ import annotations

from .schedule_simulator import ScheduleHour
from .schemas import ActionType, CurrentState, Recommendation, Explanation


_ACTION_HEADLINES = {
    ActionType.charge_battery: "Charge the battery",
    ActionType.discharge_battery: "Discharge the battery to serve load",
    ActionType.use_grid: "Draw from the grid",
    ActionType.export_energy: "Export surplus energy to the grid",
    ActionType.run_heavy_loads: "Run heavy/flexible loads now",
    ActionType.reduce_load: "Reduce non-essential load",
    ActionType.maintain_current_state: "No action needed - system is balanced",
}


def explain(current: CurrentState, recommendation: Recommendation, schedule: list[ScheduleHour]) -> Explanation:
    net_kw = (current.solar.power_kw + current.wind.power_kw) - current.load.power_kw
    soc = current.battery.soc_percent
    action = recommendation.action

    details: list[str] = [
        f"Solar {current.solar.power_kw:.1f} kW + wind {current.wind.power_kw:.1f} kW "
        f"vs load {current.load.power_kw:.1f} kW -> net {'surplus' if net_kw >= 0 else 'deficit'} "
        f"of {abs(net_kw):.1f} kW right now.",
        f"Battery is at {soc:.0f}% state of charge.",
        f"Grid is currently {current.grid.direction.value}ing {current.grid.power_kw:.1f} kW.",
    ]

    if action == ActionType.charge_battery:
        summary = (
            f"Charge the battery at ~{recommendation.recommended_value_kw:.1f} kW - "
            f"renewables currently exceed campus load and the battery still has headroom."
        )
        details.append(
            f"Routing the {net_kw:.1f} kW surplus into storage avoids exporting it at a lower "
            f"tariff and builds a buffer for later in the day."
        )

    elif action == ActionType.export_energy:
        summary = (
            f"Export ~{recommendation.recommended_value_kw:.1f} kW to the grid - "
            f"the battery is already well charged, so there's no useful place left to store the surplus."
        )
        details.append("Exporting avoids curtailing (wasting) available renewable generation.")

    elif action == ActionType.run_heavy_loads:
        summary = (
            f"Good window to run flexible/heavy loads (~{recommendation.recommended_value_kw:.1f} kW) - "
            f"there's ample renewable surplus and the battery is already adequately charged."
        )
        details.append(
            "Running discretionary loads now (EV charging, pumping, pre-cooling) uses clean energy "
            "directly instead of exporting it at a lower rate than it would cost to buy back later."
        )

    elif action == ActionType.discharge_battery:
        summary = (
            f"Discharge the battery at ~{recommendation.recommended_value_kw:.1f} kW to cover the "
            f"current shortfall instead of pulling more from the grid."
        )
        details.append(f"Battery SOC ({soc:.0f}%) is comfortably above the minimum reserve threshold.")

    elif action == ActionType.use_grid:
        summary = (
            f"Draw ~{recommendation.recommended_value_kw:.1f} kW from the grid - "
            f"renewables can't cover the current load and the battery is too low to discharge further "
            f"without risking its reserve."
        )
        details.append(f"Battery SOC ({soc:.0f}%) is at or below the low-SOC protection threshold.")

    elif action == ActionType.reduce_load:
        summary = (
            f"Reduce non-essential/flexible load by ~{recommendation.recommended_value_kw:.1f} kW - "
            f"grid import is already high and the battery has little left to give."
        )
        details.append(
            f"Grid import is at {current.grid.power_kw:.1f} kW with battery SOC only {soc:.0f}% - "
            f"cutting discretionary load protects against further grid dependency."
        )

    else:  # maintain_current_state
        summary = "Generation, load, and battery SOC are currently balanced - maintain current operation."

    if schedule:
        min_soc_hour = min(schedule, key=lambda h: h.battery_soc_percent)
        if min_soc_hour.battery_soc_percent <= 20:
            details.append(
                f"Heads up: the forecast shows SOC dropping to ~{min_soc_hour.battery_soc_percent:.0f}% "
                f"around {min_soc_hour.timestamp.strftime('%H:%M UTC')} if this trajectory holds."
            )

    return Explanation(summary=summary, details=details)
