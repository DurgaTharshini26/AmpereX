"""
insights.py
------------
Proactive AI insights: scans the forecast + simulated schedule for
conditions worth flagging to a human *before* they happen, independent of
the single "do this now" recommendation from decision_engine.py.

Examples of what this looks for:
  - A solar generation drop coming later today (cloud front moving in)
  - A wind lull (sustained low wind speed / low wind output)
  - The battery projected to hit its minimum reserve SOC
  - A grid-import spike coming during evening peak
  - A strong upcoming surplus window worth planning discretionary loads around

Each insight is timestamped ("valid_from"/"valid_until") so the dashboard
can show it as a banner/timeline entry rather than a generic bullet list.
"""

from __future__ import annotations

from datetime import timedelta

from .config import BATTERY, THRESHOLDS
from .schedule_simulator import ScheduleHour
from .schemas import AIInsight, ForecastResult, InsightSeverity


def _solar_drop_insight(forecast: ForecastResult) -> AIInsight | None:
    points = forecast.solar_kw.points
    if len(points) < 12:
        return None
    near = points[:6]
    later = points[6:12]
    near_avg = sum(p.yhat for p in near) / len(near)
    later_avg = sum(p.yhat for p in later) / len(later)
    if near_avg <= 1e-6:
        return None
    drop_percent = 100.0 * (near_avg - later_avg) / near_avg
    if drop_percent >= 30:
        return AIInsight(
            severity=InsightSeverity.warning,
            message=(
                f"Solar generation is forecast to drop by ~{drop_percent:.0f}% "
                f"(from ~{near_avg:.0f} kW to ~{later_avg:.0f} kW average) between "
                f"{near[0].timestamp.strftime('%H:%M')} and {later[-1].timestamp.strftime('%H:%M UTC')} - "
                f"likely increasing cloud cover. Plan to lean on stored/battery energy in that window."
            ),
            valid_from=later[0].timestamp,
            valid_until=later[-1].timestamp,
        )
    return None


def _wind_lull_insight(forecast: ForecastResult, cut_in_kw: float = 3.0) -> AIInsight | None:
    points = forecast.wind_kw.points
    run_start = None
    for i, p in enumerate(points):
        if p.yhat < cut_in_kw:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= 3:
                return AIInsight(
                    severity=InsightSeverity.info,
                    message=(
                        f"Wind output is forecast to stay low (below ~{cut_in_kw:.0f} kW) for "
                        f"{i - run_start} consecutive hours, from "
                        f"{points[run_start].timestamp.strftime('%H:%M')} to "
                        f"{points[i - 1].timestamp.strftime('%H:%M UTC')}."
                    ),
                    valid_from=points[run_start].timestamp,
                    valid_until=points[i - 1].timestamp,
                )
            run_start = None
    if run_start is not None and len(points) - run_start >= 3:
        return AIInsight(
            severity=InsightSeverity.info,
            message=(
                f"Wind output is forecast to stay low (below ~{cut_in_kw:.0f} kW) for the rest of "
                f"the forecast window, starting {points[run_start].timestamp.strftime('%H:%M UTC')}."
            ),
            valid_from=points[run_start].timestamp,
            valid_until=points[-1].timestamp,
        )
    return None


def _battery_depletion_insight(schedule: list[ScheduleHour]) -> AIInsight | None:
    for hour in schedule:
        if hour.battery_soc_percent <= BATTERY.min_soc_percent + 5:
            return AIInsight(
                severity=InsightSeverity.critical,
                message=(
                    f"Battery is projected to approach its minimum reserve "
                    f"(~{hour.battery_soc_percent:.0f}% SOC) around "
                    f"{hour.timestamp.strftime('%H:%M UTC')} if current conditions hold - "
                    f"consider reducing discretionary load or scheduling a grid top-up before then."
                ),
                valid_from=hour.timestamp,
                valid_until=hour.timestamp + timedelta(hours=1),
            )
    return None


def _grid_spike_insight(schedule: list[ScheduleHour]) -> AIInsight | None:
    th = THRESHOLDS
    spikes = [h for h in schedule if h.grid_import_kw >= th.high_grid_import_kw]
    if not spikes:
        return None
    worst = max(spikes, key=lambda h: h.grid_import_kw)
    return AIInsight(
        severity=InsightSeverity.warning,
        message=(
            f"Grid import is forecast to spike to ~{worst.grid_import_kw:.0f} kW around "
            f"{worst.timestamp.strftime('%H:%M UTC')}, when demand outpaces both renewables and "
            f"available battery capacity - consider shifting flexible loads away from this window."
        ),
        valid_from=spikes[0].timestamp,
        valid_until=spikes[-1].timestamp,
    )


def _surplus_opportunity_insight(schedule: list[ScheduleHour]) -> AIInsight | None:
    surplus_hours = [h for h in schedule if h.export_kw >= THRESHOLDS.min_actionable_kw]
    if not surplus_hours:
        return None
    best = max(surplus_hours, key=lambda h: h.export_kw)
    return AIInsight(
        severity=InsightSeverity.opportunity,
        message=(
            f"A strong renewable surplus (~{best.export_kw:.0f} kW beyond what the battery can absorb) "
            f"is forecast around {best.timestamp.strftime('%H:%M UTC')} - a good window to schedule "
            f"EV charging, water pumping, or other flexible/heavy loads."
        ),
        valid_from=best.timestamp,
        valid_until=best.timestamp + timedelta(hours=1),
    )


def generate_insights(forecast: ForecastResult, schedule: list[ScheduleHour]) -> list[AIInsight]:
    """Returns the list of insights that actually fired (0 or more), in a
    fixed priority order: critical/warning conditions before opportunities."""
    candidates = [
        _battery_depletion_insight(schedule),
        _grid_spike_insight(schedule),
        _solar_drop_insight(forecast),
        _wind_lull_insight(forecast),
        _surplus_opportunity_insight(schedule),
    ]
    return [insight for insight in candidates if insight is not None]
