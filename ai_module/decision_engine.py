"""
decision_engine.py
--------------------
Rule-based scoring engine that picks ONE operational action right now:

    CHARGE_BATTERY, DISCHARGE_BATTERY, USE_GRID, EXPORT_ENERGY,
    RUN_HEAVY_LOADS, REDUCE_LOAD, or MAINTAIN_CURRENT_STATE (fallback)

Unlike a multi-rule engine where several recommendations can fire at once,
a control-room operator (or an automated actuator) needs a single next
action. So every candidate action is scored 0-100 based on the current
sensor snapshot + the near-term forecasted trajectory (from
schedule_simulator.py), and the highest-scoring action wins. Runner-ups are
kept on the response for transparency/debugging - "why THIS action and not
that one" is fully inspectable.

Every scoring rule is a small, named, commented function - this is meant to
be auditable by a human, not a black box.
"""

from __future__ import annotations

from .config import BATTERY, THRESHOLDS
from .schedule_simulator import ScheduleHour, simulate_schedule
from .schemas import ActionCandidate, ActionType, CurrentState, ForecastResult, Priority, Recommendation


def _forecast_confidence(forecast: ForecastResult, hours: int) -> float:
    """Tighter Prophet uncertainty bands over the next `hours` -> higher confidence."""
    spreads = []
    for metric_forecast in (forecast.solar_kw, forecast.wind_kw, forecast.load_kw):
        for pt in metric_forecast.points[:hours]:
            spreads.append((pt.yhat_upper - pt.yhat_lower) / max(pt.yhat, 1.0))
    if not spreads:
        return 0.7
    avg_spread = sum(spreads) / len(spreads)
    return round(max(0.5, min(0.99, 1.0 - min(avg_spread, 1.0) * 0.5)), 2)


def _score_actions(current: CurrentState, schedule: list[ScheduleHour]) -> list[ActionCandidate]:
    th = THRESHOLDS
    net_kw = (current.solar.power_kw + current.wind.power_kw) - current.load.power_kw
    soc = current.battery.soc_percent
    grid_kw = current.grid.power_kw

    lookahead = schedule[: th.load_shift_lookahead_hours] if schedule else []
    near_term_best_net = max((h.net_kw for h in lookahead), default=net_kw)

    candidates: dict[ActionType, ActionCandidate] = {}

    def add(action: ActionType, score: float, value_kw: float | None = None) -> None:
        candidates[action] = ActionCandidate(
            action=action, score=round(max(0.0, score), 1),
            recommended_value_kw=None if value_kw is None else round(value_kw, 1),
        )

    # --- CHARGE_BATTERY: surplus now, battery has headroom -------------------
    if net_kw > 0 and soc < th.high_soc_percent:
        headroom_score = (th.high_soc_percent - soc)          # more headroom -> higher score
        surplus_score = min(net_kw, 100)                       # bigger surplus -> higher score
        score = 0.5 * headroom_score + 0.5 * surplus_score
        chargeable_kw = min(net_kw, current.battery.max_charge_kw or BATTERY.max_charge_kw)
        add(ActionType.charge_battery, score, chargeable_kw)

    # --- EXPORT_ENERGY: surplus now, battery already full ---------------------
    if net_kw > 0 and soc >= th.high_soc_percent:
        score = min(net_kw, 100) + 10  # battery full -> exporting is clearly the only good option
        add(ActionType.export_energy, score, net_kw)

    # --- RUN_HEAVY_LOADS: large surplus AND battery comfortably charged,
    #     AND the near-term forecast doesn't show an imminent generation drop
    #     -> good moment to run discretionary/flexible loads on clean energy
    #     rather than exporting it at a lower tariff.
    if net_kw > 0 and soc >= th.low_soc_percent and near_term_best_net > 0:
        surplus_after_battery_priority = max(0.0, net_kw - (th.high_soc_percent - soc))
        score = surplus_after_battery_priority * 0.8
        flexible_kw = current.load.power_kw * th.flexible_load_fraction
        add(ActionType.run_heavy_loads, score, flexible_kw)

    # --- DISCHARGE_BATTERY: deficit now, battery has usable energy above min SOC
    if net_kw < 0 and soc > th.low_soc_percent:
        deficit = -net_kw
        dischargeable_kwh = max(0.0, (soc - BATTERY.min_soc_percent) / 100.0 * current.battery.capacity_kwh)
        dischargeable_kw = min(deficit, current.battery.max_discharge_kw or BATTERY.max_discharge_kw,
                                dischargeable_kwh)
        if dischargeable_kw >= th.min_actionable_kw:
            score = min(dischargeable_kw, 100) + (soc - th.low_soc_percent) * 0.3
            add(ActionType.discharge_battery, score, dischargeable_kw)

    # --- USE_GRID: deficit now, battery too low to safely discharge more -------
    if net_kw < 0 and soc <= th.low_soc_percent:
        deficit = -net_kw
        score = min(deficit, 100) + (th.low_soc_percent - soc) * 0.5
        add(ActionType.use_grid, score, deficit)

    # --- REDUCE_LOAD: deficit is severe, grid import already high, battery
    #     nearly depleted -> curtail non-essential load rather than keep
    #     drawing more from an already-stressed grid connection.
    if net_kw < 0 and grid_kw >= th.high_grid_import_kw and soc <= th.low_soc_percent:
        score = min(grid_kw, 100) + (th.low_soc_percent - soc) * 0.5 + 15  # nudge above plain USE_GRID
        reducible_kw = current.load.power_kw * th.flexible_load_fraction
        add(ActionType.reduce_load, score, reducible_kw)

    # --- MAINTAIN_CURRENT_STATE: always available as the lowest-priority fallback
    add(ActionType.maintain_current_state, score=1.0, value_kw=0.0)

    return sorted(candidates.values(), key=lambda c: c.score, reverse=True)


def _priority_for_score(score: float) -> Priority:
    if score >= 60:
        return Priority.high
    if score >= 25:
        return Priority.medium
    return Priority.low


class DecisionEngine:
    """Public interface: pick the single best action for right now."""

    def decide(self, current: CurrentState, forecast: ForecastResult) -> tuple[Recommendation, list[ScheduleHour]]:
        schedule = simulate_schedule(current, forecast)
        ranked = _score_actions(current, schedule)

        winner = ranked[0]
        runner_ups = ranked[1:4]  # keep it short - top 3 alternatives is plenty for transparency
        confidence = _forecast_confidence(forecast, hours=min(6, len(schedule)))

        recommendation = Recommendation(
            action=winner.action,
            priority=_priority_for_score(winner.score),
            recommended_value_kw=winner.recommended_value_kw,
            confidence=confidence,
            runner_ups=runner_ups,
        )
        return recommendation, schedule
