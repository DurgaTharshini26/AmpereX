"""
schemas.py
----------
Vendor-neutral common JSON contract for the AmpereX AI Module.

Same normalization philosophy as before: every hardware vendor's sensor
payload gets mapped upstream (MQTT -> FastAPI -> this module) into the
`CurrentState` shape below, so the AI module never has to know or care
whether a reading came from a Growatt inverter, a synthetic simulator, or
anything else.

New in this version (per the hackathon spec):
  - `Recommendation` is now a SINGLE best action (not a list of independently
    firing rules) - `DecisionEngine` scores every candidate action and
    returns the winner, plus runner-ups for transparency.
  - `Explanation`: a human-readable justification for the chosen action.
  - `AIInsight`: proactive, forward-looking warnings/opportunities
    ("wind will drop below cut-in speed for 3h tonight", etc.) generated
    from the forecast, independent of the single recommended action.
  - `ImpactMetrics`: estimated financial + environmental impact (cost
    saved, carbon saved, renewable utilization, trees-equivalent).
  - `AmpereXAIResponse`: the single top-level object the FastAPI backend
    gets back from this module - forecast + recommendation + explanation
    + insights + impact, all in one JSON-serializable payload.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# INPUT: current sensor snapshot
# ---------------------------------------------------------------------------

class SolarReading(BaseModel):
    power_kw: float = Field(..., ge=0)
    irradiance_w_m2: Optional[float] = Field(None, ge=0)


class WindReading(BaseModel):
    power_kw: float = Field(..., ge=0)
    wind_speed_m_s: Optional[float] = Field(None, ge=0)


class BatteryState(str, Enum):
    idle = "idle"
    charging = "charging"
    discharging = "discharging"


class BatteryReading(BaseModel):
    soc_percent: float = Field(..., ge=0, le=100)
    capacity_kwh: float = Field(..., gt=0)
    power_kw: float = 0.0
    state: BatteryState = BatteryState.idle
    max_charge_kw: Optional[float] = None
    max_discharge_kw: Optional[float] = None


class LoadReading(BaseModel):
    power_kw: float = Field(..., ge=0)


class GridDirection(str, Enum):
    importing = "import"
    exporting = "export"
    neutral = "neutral"


class GridReading(BaseModel):
    power_kw: float = Field(..., ge=0)
    direction: GridDirection = GridDirection.importing


class WeatherContext(BaseModel):
    temperature_c: Optional[float] = None
    cloud_cover_percent: Optional[float] = Field(None, ge=0, le=100)
    wind_speed_m_s: Optional[float] = Field(None, ge=0)
    shortwave_radiation_w_m2: Optional[float] = Field(None, ge=0)


class CurrentState(BaseModel):
    site_id: str
    timestamp: datetime
    solar: SolarReading
    wind: WindReading
    battery: BatteryReading
    load: LoadReading
    grid: GridReading
    weather: Optional[WeatherContext] = None


# ---------------------------------------------------------------------------
# OUTPUT: forecast (Prophet) - solar / wind / demand for tomorrow
# ---------------------------------------------------------------------------

class ForecastPoint(BaseModel):
    timestamp: datetime
    yhat: float
    yhat_lower: float
    yhat_upper: float


class MetricForecast(BaseModel):
    metric: str  # "solar_kw" | "wind_kw" | "load_kw"
    unit: str = "kW"
    points: list[ForecastPoint]


class ForecastResult(BaseModel):
    site_id: str
    generated_at: datetime
    horizon_hours: int
    solar_kw: MetricForecast
    wind_kw: MetricForecast
    load_kw: MetricForecast


# ---------------------------------------------------------------------------
# OUTPUT: decision engine - ONE recommended action
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    charge_battery = "CHARGE_BATTERY"
    discharge_battery = "DISCHARGE_BATTERY"
    use_grid = "USE_GRID"
    export_energy = "EXPORT_ENERGY"
    run_heavy_loads = "RUN_HEAVY_LOADS"
    reduce_load = "REDUCE_LOAD"
    maintain_current_state = "MAINTAIN_CURRENT_STATE"


class Priority(str, Enum):
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"


class ActionCandidate(BaseModel):
    """One scored candidate the decision engine considered."""
    action: ActionType
    score: float
    recommended_value_kw: Optional[float] = None


class Recommendation(BaseModel):
    action: ActionType
    priority: Priority
    recommended_value_kw: Optional[float] = None
    confidence: float = Field(..., ge=0, le=1)
    runner_ups: list[ActionCandidate] = Field(
        default_factory=list,
        description="Other candidate actions considered, for transparency/debugging",
    )


class Explanation(BaseModel):
    summary: str = Field(..., description="One-line, dashboard-friendly explanation")
    details: list[str] = Field(
        default_factory=list,
        description="Supporting bullet points with the numbers behind the decision",
    )


# ---------------------------------------------------------------------------
# OUTPUT: proactive AI insights (forward-looking warnings/opportunities)
# ---------------------------------------------------------------------------

class InsightSeverity(str, Enum):
    info = "INFO"
    warning = "WARNING"
    critical = "CRITICAL"
    opportunity = "OPPORTUNITY"


class AIInsight(BaseModel):
    severity: InsightSeverity
    message: str
    valid_from: datetime
    valid_until: Optional[datetime] = None


# ---------------------------------------------------------------------------
# OUTPUT: environmental + financial impact estimates
# ---------------------------------------------------------------------------

class ImpactMetrics(BaseModel):
    renewable_utilization_percent: float
    grid_dependency_percent: float
    estimated_cost_saved_currency: float = Field(
        ..., description="Estimated cost saved over the forecast horizon vs. a 100%-grid baseline"
    )
    currency: str = "INR"
    estimated_carbon_saved_kg: float
    trees_equivalent: float = Field(
        ..., description="Carbon saved expressed as an equivalent number of mature trees per year"
    )


# ---------------------------------------------------------------------------
# Top-level response returned by the AI module
# ---------------------------------------------------------------------------

class AmpereXAIResponse(BaseModel):
    site_id: str
    generated_at: datetime
    forecast: ForecastResult
    recommendation: Recommendation
    explanation: Explanation
    ai_insights: list[AIInsight]
    impact_metrics: ImpactMetrics
