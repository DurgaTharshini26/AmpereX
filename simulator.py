"""
Renewable energy sensor simulator.

Generates realistic sensor readings for solar panels, wind turbines,
battery storage, campus electrical load, and grid power based on
live weather data and time-of-day patterns.
"""

import math
import random

from config import (
    BATTERY_CAPACITY_KWH,
    BATTERY_CHARGE_RATE_KW,
    BATTERY_DISCHARGE_RATE_KW,
    BATTERY_EFFICIENCY,
    BATTERY_INITIAL_SOC,
    BATTERY_MAX_SOC,
    BATTERY_MIN_SOC,
    CAMPUS_BASE_LOAD_KW,
    CAMPUS_LOAD_PROFILE,
    LOAD_NOISE_FACTOR,
    PUBLISH_INTERVAL,
    SOLAR_MAX_CAPACITY_KW,
    SOLAR_NOISE_FACTOR,
    SOLAR_SUNRISE_HOUR,
    SOLAR_SUNSET_HOUR,
    WIND_CUT_IN_SPEED,
    WIND_CUT_OUT_SPEED,
    WIND_MAX_CAPACITY_KW,
    WIND_NOISE_FACTOR,
    WIND_RATED_SPEED,
)
from utils import clamp, get_local_hour, get_local_minute, setup_logger
from weather import WeatherData

logger = setup_logger(__name__)


class EnergySimulator:
    """Simulates realistic renewable energy sensor readings.

    Maintains internal state (battery SoC) across cycles and uses
    weather data plus time-of-day to compute physically plausible
    power values for each energy source.
    """

    def __init__(self) -> None:
        self.battery_soc: float = BATTERY_INITIAL_SOC
        logger.info("EnergySimulator initialized | Battery SoC: %.1f%%", self.battery_soc)

    def simulate_solar(self, weather: WeatherData) -> float:
        """Calculate solar output based on time of day and cloud cover."""
        hour = get_local_hour()
        minute = get_local_minute()
        fh = hour + minute / 60.0

        if fh < SOLAR_SUNRISE_HOUR or fh >= SOLAR_SUNSET_HOUR:
            return 0.0

        duration = SOLAR_SUNSET_HOUR - SOLAR_SUNRISE_HOUR
        progress = (fh - SOLAR_SUNRISE_HOUR) / duration
        angle = math.sin(math.pi * progress)

        cloud = 1.0 - (weather.cloud_cover_pct / 100.0) * 0.85
        noise = 1.0 + random.uniform(-SOLAR_NOISE_FACTOR, SOLAR_NOISE_FACTOR)

        power = SOLAR_MAX_CAPACITY_KW * angle * cloud * noise
        return clamp(round(power, 2), 0.0, SOLAR_MAX_CAPACITY_KW)

    def simulate_wind(self, weather: WeatherData) -> float:
        """Calculate wind turbine output using a cubic power curve."""
        ws = weather.wind_speed_kmh

        if ws < WIND_CUT_IN_SPEED or ws > WIND_CUT_OUT_SPEED:
            return 0.0

        if ws <= WIND_RATED_SPEED:
            fraction = ((ws - WIND_CUT_IN_SPEED) / (WIND_RATED_SPEED - WIND_CUT_IN_SPEED)) ** 3
            power = WIND_MAX_CAPACITY_KW * fraction
        else:
            power = WIND_MAX_CAPACITY_KW

        noise = 1.0 + random.uniform(-WIND_NOISE_FACTOR, WIND_NOISE_FACTOR)
        power *= noise
        return clamp(round(power, 2), 0.0, WIND_MAX_CAPACITY_KW)

    def simulate_load(self) -> float:
        """Simulate campus electrical demand with hourly interpolation."""
        hour = get_local_hour()
        minute = get_local_minute()

        cur = CAMPUS_LOAD_PROFILE[hour]
        nxt = CAMPUS_LOAD_PROFILE[(hour + 1) % 24]
        interp = cur + (nxt - cur) * (minute / 60.0)

        noise = 1.0 + random.uniform(-LOAD_NOISE_FACTOR, LOAD_NOISE_FACTOR)
        load = CAMPUS_BASE_LOAD_KW * interp * noise
        return round(max(load, 0.0), 2)

    def update_battery(self, solar_kw: float, wind_kw: float, load_kw: float) -> float:
        """Update battery SoC. Returns flow (positive=charging, negative=discharging)."""
        surplus = (solar_kw + wind_kw) - load_kw
        dt = PUBLISH_INTERVAL / 3600.0

        if surplus > 0:
            charge = min(surplus, BATTERY_CHARGE_RATE_KW)
            energy = charge * BATTERY_EFFICIENCY * dt
            headroom = (BATTERY_MAX_SOC - self.battery_soc) / 100.0 * BATTERY_CAPACITY_KWH
            energy = min(energy, max(headroom, 0.0))
            self.battery_soc += (energy / BATTERY_CAPACITY_KWH) * 100.0
            self.battery_soc = clamp(self.battery_soc, BATTERY_MIN_SOC, BATTERY_MAX_SOC)
            flow = round(energy / (BATTERY_EFFICIENCY * dt) if dt > 0 else 0.0, 2)
        elif surplus < 0:
            discharge = min(abs(surplus), BATTERY_DISCHARGE_RATE_KW)
            energy = discharge * dt
            available = (self.battery_soc - BATTERY_MIN_SOC) / 100.0 * BATTERY_CAPACITY_KWH
            energy = min(energy, max(available, 0.0))
            self.battery_soc -= (energy / BATTERY_CAPACITY_KWH) * 100.0
            self.battery_soc = clamp(self.battery_soc, BATTERY_MIN_SOC, BATTERY_MAX_SOC)
            flow = round(-(energy / dt) if dt > 0 else 0.0, 2)
        else:
            flow = 0.0

        self.battery_soc = round(self.battery_soc, 2)
        return flow

    def calculate_grid(self, load: float, solar: float, wind: float, battery_flow: float) -> float:
        """Grid = Load - Solar - Wind + battery_discharge. Positive=import."""
        grid = load - solar - wind + battery_flow
        return round(grid, 2)

    def run_cycle(self, weather: WeatherData) -> dict[str, float]:
        """Execute one full simulation cycle and return all readings."""
        solar = self.simulate_solar(weather)
        wind = self.simulate_wind(weather)
        load = self.simulate_load()
        battery_flow = self.update_battery(solar, wind, load)
        grid = self.calculate_grid(load, solar, wind, battery_flow)

        logger.info(
            "Cycle: Solar=%.1f | Wind=%.1f | Load=%.1f | "
            "Battery=%.1f%% (%.1f kW) | Grid=%.1f kW",
            solar, wind, load, self.battery_soc, battery_flow, grid,
        )

        return {
            "solar": solar,
            "wind": wind,
            "load": load,
            "battery_soc": self.battery_soc,
            "battery_flow": battery_flow,
            "grid": grid,
        }
