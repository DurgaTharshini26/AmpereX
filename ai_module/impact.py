"""
impact.py
----------
Translates the simulated schedule (schedule_simulator.py) into estimated
financial + environmental impact metrics for the dashboard:

  - renewable_utilization_percent: how much of the generated renewable
    energy was actually self-consumed (vs exported/curtailed)
  - grid_dependency_percent: what fraction of total campus demand still had
    to come from the grid
  - estimated_cost_saved: vs. a 100%-grid baseline, over the forecast horizon
  - estimated_carbon_saved_kg: grid-equivalent CO2 avoided
  - trees_equivalent: that carbon saving expressed as an annualized
    equivalent number of mature trees (see note below)

These are intentionally simple, clearly-documented estimates suitable for a
hackathon dashboard callout - not a certified carbon-accounting methodology.
Swap the constants in config.py::ImpactConfig for your actual campus tariff
and your grid region's published emission factor for a real deployment.
"""

from __future__ import annotations

from .config import IMPACT
from .schedule_simulator import ScheduleHour
from .schemas import ImpactMetrics


def compute_impact(schedule: list[ScheduleHour]) -> ImpactMetrics:
    if not schedule:
        return ImpactMetrics(
            renewable_utilization_percent=0.0,
            grid_dependency_percent=0.0,
            estimated_cost_saved_currency=0.0,
            currency=IMPACT.currency,
            estimated_carbon_saved_kg=0.0,
            trees_equivalent=0.0,
        )

    total_renewable_kwh = sum(h.solar_kw + h.wind_kw for h in schedule)      # hourly steps -> kWh
    total_load_kwh = sum(h.load_kw for h in schedule)
    total_grid_import_kwh = sum(h.grid_import_kw for h in schedule)
    total_export_kwh = sum(h.export_kw for h in schedule)

    # How much of the campus's own renewable generation actually served its
    # own load / storage, rather than being exported / curtailed.
    renewable_utilization_percent = (
        100.0 * (total_renewable_kwh - total_export_kwh) / total_renewable_kwh
        if total_renewable_kwh > 0 else 0.0
    )
    grid_dependency_percent = (
        100.0 * total_grid_import_kwh / total_load_kwh if total_load_kwh > 0 else 0.0
    )

    # Energy that served campus load WITHOUT being bought from the grid
    # (renewables + battery discharge covering load directly).
    avoided_grid_kwh = max(0.0, total_load_kwh - total_grid_import_kwh)

    # Cost saved vs. a 100%-grid baseline: what the campus didn't have to
    # pay for avoided grid energy, plus revenue earned from exporting surplus.
    baseline_cost = total_load_kwh * IMPACT.grid_tariff_per_kwh
    actual_grid_cost = total_grid_import_kwh * IMPACT.grid_tariff_per_kwh
    export_revenue = total_export_kwh * IMPACT.export_tariff_per_kwh
    estimated_cost_saved = (baseline_cost - actual_grid_cost) + export_revenue

    carbon_saved_kg = avoided_grid_kwh * IMPACT.grid_emission_factor_kg_co2_per_kwh

    # "Trees equivalent" is expressed as an ANNUALIZED projection: if this
    # forecast horizon's saving pattern repeated every day for a year, how
    # many mature trees' worth of yearly CO2 absorption would that equal?
    # (A single day's raw saving would otherwise round to a fraction of a
    # tree and be hard to communicate on a dashboard.)
    horizon_hours = len(schedule)
    days_per_year_equivalent = 365.0 * (24.0 / horizon_hours) if horizon_hours > 0 else 0.0
    annualized_carbon_saved_kg = carbon_saved_kg * days_per_year_equivalent
    trees_equivalent = (
        annualized_carbon_saved_kg / IMPACT.tree_co2_absorption_kg_per_year
        if IMPACT.tree_co2_absorption_kg_per_year > 0 else 0.0
    )

    return ImpactMetrics(
        renewable_utilization_percent=round(max(0.0, min(100.0, renewable_utilization_percent)), 1),
        grid_dependency_percent=round(max(0.0, min(100.0, grid_dependency_percent)), 1),
        estimated_cost_saved_currency=round(estimated_cost_saved, 2),
        currency=IMPACT.currency,
        estimated_carbon_saved_kg=round(carbon_saved_kg, 2),
        trees_equivalent=round(trees_equivalent, 2),
    )
