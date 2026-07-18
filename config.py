"""
Configuration module for the Sensor Simulator.

All configurable parameters are centralized here. Modify these values
to match your deployment environment (location, broker, capacities).
"""

# =============================================================================
# Geographic Location (Default: Chennai, India)
# =============================================================================
LATITUDE: float = 13.0827
LONGITUDE: float = 80.2707

# =============================================================================
# Open-Meteo Forecast API
# =============================================================================
OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
WEATHER_FETCH_TIMEOUT: int = 10  # seconds
WEATHER_RETRY_ATTEMPTS: int = 3
WEATHER_RETRY_DELAY: float = 2.0  # seconds between retries

# =============================================================================
# MQTT Broker
# =============================================================================
MQTT_BROKER: str = "localhost"
MQTT_PORT: int = 1883
MQTT_KEEPALIVE: int = 60  # seconds
MQTT_CLIENT_ID: str = "amperex-sensor-simulator"

# MQTT Topic Prefix (allows namespacing for multi-campus deployments)
MQTT_TOPIC_PREFIX: str = "campus/energy"

# =============================================================================
# Publish Interval
# =============================================================================
PUBLISH_INTERVAL: int = 5  # seconds between each publish cycle

# =============================================================================
# Solar Panel Configuration
# =============================================================================
SOLAR_MAX_CAPACITY_KW: float = 100.0  # peak rated capacity in kW
SOLAR_SUNRISE_HOUR: int = 6           # hour when solar generation begins
SOLAR_SUNSET_HOUR: int = 18           # hour when solar generation ends
SOLAR_NOISE_FACTOR: float = 0.05      # ±5% random variation

# =============================================================================
# Wind Turbine Configuration
# =============================================================================
WIND_MAX_CAPACITY_KW: float = 50.0    # peak rated capacity in kW
WIND_CUT_IN_SPEED: float = 3.0        # minimum wind speed to generate (km/h)
WIND_RATED_SPEED: float = 40.0        # wind speed at rated power (km/h)
WIND_CUT_OUT_SPEED: float = 90.0      # safety shutdown speed (km/h)
WIND_NOISE_FACTOR: float = 0.05       # ±5% random variation

# =============================================================================
# Battery Storage Configuration
# =============================================================================
BATTERY_CAPACITY_KWH: float = 200.0   # total battery capacity in kWh
BATTERY_INITIAL_SOC: float = 50.0     # initial state of charge (%)
BATTERY_MIN_SOC: float = 10.0         # minimum allowed SoC (%)
BATTERY_MAX_SOC: float = 95.0         # maximum allowed SoC (%)
BATTERY_CHARGE_RATE_KW: float = 30.0  # max charge rate in kW
BATTERY_DISCHARGE_RATE_KW: float = 30.0  # max discharge rate in kW
BATTERY_EFFICIENCY: float = 0.92      # round-trip efficiency

# =============================================================================
# Campus Electrical Load Configuration
# =============================================================================
CAMPUS_BASE_LOAD_KW: float = 80.0     # base load in kW
LOAD_NOISE_FACTOR: float = 0.08       # ±8% random variation

# Hourly load multipliers (0–23 hours)
# Represents typical campus demand pattern across 24 hours
CAMPUS_LOAD_PROFILE: list[float] = [
    0.30,  # 00:00 - Midnight (very low)
    0.25,  # 01:00
    0.22,  # 02:00
    0.20,  # 03:00 - Lowest demand
    0.22,  # 04:00
    0.30,  # 05:00 - Early morning ramp-up
    0.45,  # 06:00
    0.60,  # 07:00 - Morning activity begins
    0.80,  # 08:00 - Classes start
    0.95,  # 09:00 - Peak morning
    1.00,  # 10:00 - Peak demand
    0.98,  # 11:00
    0.85,  # 12:00 - Lunch break dip
    0.90,  # 13:00 - Afternoon classes
    1.00,  # 14:00 - Peak afternoon
    0.95,  # 15:00
    0.85,  # 16:00 - Classes winding down
    0.75,  # 17:00 - Evening transition
    0.70,  # 18:00 - Evening activities
    0.65,  # 19:00
    0.55,  # 20:00
    0.45,  # 21:00 - Night
    0.38,  # 22:00
    0.32,  # 23:00
]

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s | %(name)-18s | %(levelname)-8s | %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
