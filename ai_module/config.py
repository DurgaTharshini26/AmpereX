"""
config.py
---------
Central place for every tunable constant used by the AmpereX AI Module.

Nothing here is hardcoded logic - it is all "site configuration". In a real
deployment these values would come from a per-campus config record (stored
alongside the vendor adapter config) so the same module can run for many
different campuses with different battery sizes, tariffs, thresholds, etc.

Keeping this separate from decision_engine.py / forecasting.py / impact.py
means the decision logic never has magic numbers buried in it.
"""

from dataclasses import dataclass


@dataclass
class BatteryConfig:
    capacity_kwh: float = 500.0          # usable battery capacity
    max_charge_kw: float = 100.0         # max charge rate (C-rate limited)
    max_discharge_kw: float = 100.0      # max discharge rate
    min_soc_percent: float = 15.0        # never discharge below this (protects battery health)
    max_soc_percent: float = 95.0        # never charge above this (protects battery health)
    round_trip_efficiency: float = 0.92  # energy lost charging + discharging


@dataclass
class DecisionThresholds:
    """Tunables used by the single-action DecisionEngine's scoring rules."""

    # Minimum surplus/deficit (kW) before it's worth acting on - avoids
    # flip-flopping on tiny/noisy readings.
    min_actionable_kw: float = 2.0

    # Battery SOC bands
    low_soc_percent: float = 30.0
    high_soc_percent: float = 85.0

    # If current grid import exceeds this, USE_GRID/REDUCE_LOAD become relevant
    high_grid_import_kw: float = 15.0

    # Look-ahead window (hours) used to decide whether to defer heavy loads
    # to a forecasted better window
    load_shift_lookahead_hours: int = 6

    # Fraction of current load assumed to be flexible/heavy (EV charging,
    # pumping, HVAC pre-cooling, etc.) - sizes the RUN_HEAVY_LOADS kW value
    flexible_load_fraction: float = 0.25


@dataclass
class ForecastConfig:
    default_horizon_hours: int = 24
    frequency: str = "h"          # pandas offset alias: hourly
    daily_seasonality: bool = True
    weekly_seasonality: bool = True
    yearly_seasonality: bool = False   # needs >1yr of history to be reliable
    interval_width: float = 0.80       # Prophet uncertainty interval


@dataclass
class ImpactConfig:
    """Assumptions used to translate kWh into money/CO2/trees.

    These are deliberately simple, clearly-labeled estimates suitable for a
    hackathon demo / dashboard callout - not a certified carbon accounting
    methodology. Swap in your campus's actual tariff and your grid region's
    published emission factor for a real deployment.
    """
    currency: str = "INR"
    grid_tariff_per_kwh: float = 8.0          # cost of 1 kWh bought from the grid
    export_tariff_per_kwh: float = 3.5        # revenue for 1 kWh exported to the grid
    grid_emission_factor_kg_co2_per_kwh: float = 0.82  # India grid average (approx.)
    tree_co2_absorption_kg_per_year: float = 21.0      # 1 mature tree absorbs ~21 kg CO2/year


BATTERY = BatteryConfig()
THRESHOLDS = DecisionThresholds()
FORECAST = ForecastConfig()
IMPACT = ImpactConfig()
