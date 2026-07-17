"""
schedule_simulator.py
----------------------
A single shared "what will probably happen if we just let physics run"
simulation, used by three different consumers:

  - decision_engine.py  - scores candidate actions using the near-term
                           trajectory this produces
  - insights.py          - scans the trajectory for future warning-worthy
                           conditions (battery running low, curtailment, etc.)
  - impact.py            - sums the trajectory into cost/carbon/renewable
                           utilization estimates over the forecast horizon

Kept as its own module (rather than duplicated three times) so there is
exactly one definition of "how does the battery charge/discharge given a
forecast" in the whole codebase.

The policy is a simple greedy one: surplus charges the battery first, any
leftover is exported; deficit is covered by the battery first, any leftover
is imported from the grid. This is intentionally simple/explainable rather
than a full mixed-integer optimal control solve - appropriate for a rule
based decision-support system that has to justify itself to a human
operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import BATTERY
from .schemas import CurrentState, ForecastResult


@dataclass
class ScheduleHour:
    timestamp: datetime
    solar_kw: float
    wind_kw: float
    load_kw: float
    net_kw: float
    battery_soc_percent: float
    battery_action_kw: float   # positive = charging, negative = discharging
    grid_import_kw: float
    export_kw: float


def simulate_schedule(current: CurrentState, forecast: ForecastResult) -> list[ScheduleHour]:
    """Greedy hour-by-hour battery dispatch across the forecast horizon,
    starting from the current battery SOC."""
    cfg = BATTERY
    soc_kwh = (current.battery.soc_percent / 100.0) * current.battery.capacity_kwh
    capacity_kwh = current.battery.capacity_kwh
    max_charge_kw = current.battery.max_charge_kw or cfg.max_charge_kw
    max_discharge_kw = current.battery.max_discharge_kw or cfg.max_discharge_kw
    min_soc_kwh = (cfg.min_soc_percent / 100.0) * capacity_kwh
    max_soc_kwh = (cfg.max_soc_percent / 100.0) * capacity_kwh

    schedule: list[ScheduleHour] = []

    for solar_pt, wind_pt, load_pt in zip(
        forecast.solar_kw.points, forecast.wind_kw.points, forecast.load_kw.points
    ):
        solar_kw, wind_kw, load_kw = solar_pt.yhat, wind_pt.yhat, load_pt.yhat
        net_kw = (solar_kw + wind_kw) - load_kw

        battery_action_kw = 0.0
        grid_import_kw = 0.0
        export_kw = 0.0

        if net_kw >= 0:
            headroom_kwh = max(0.0, max_soc_kwh - soc_kwh)
            max_chargeable_kw = min(max_charge_kw, headroom_kwh / cfg.round_trip_efficiency)
            charge_kw = min(net_kw, max_chargeable_kw)
            soc_kwh += charge_kw * cfg.round_trip_efficiency
            battery_action_kw = charge_kw
            export_kw = net_kw - charge_kw
        else:
            deficit_kw = -net_kw
            available_kwh = max(0.0, soc_kwh - min_soc_kwh)
            max_dischargeable_kw = min(max_discharge_kw, available_kwh)
            discharge_kw = min(deficit_kw, max_dischargeable_kw)
            soc_kwh -= discharge_kw
            battery_action_kw = -discharge_kw
            grid_import_kw = deficit_kw - discharge_kw

        schedule.append(ScheduleHour(
            timestamp=solar_pt.timestamp,
            solar_kw=round(solar_kw, 2),
            wind_kw=round(wind_kw, 2),
            load_kw=round(load_kw, 2),
            net_kw=round(net_kw, 2),
            battery_soc_percent=round(100.0 * soc_kwh / capacity_kwh, 2),
            battery_action_kw=round(battery_action_kw, 2),
            grid_import_kw=round(grid_import_kw, 2),
            export_kw=round(export_kw, 2),
        ))

    return schedule
