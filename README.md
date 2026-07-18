# AmpereX Sensor Simulator

**Virtual IoT sensor simulator** for the AmpereX Hybrid Renewable Energy Generation Solution (Virtual Power Plant).

Replaces physical hardware by generating realistic renewable energy data and publishing it to an MQTT broker. Designed to integrate seamlessly with the FastAPI backend, AI forecast engine, InfluxDB, and React dashboard.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Sensor Simulator                    │
│                                                      │
│  ┌────────────┐    ┌──────────────┐    ┌──────────┐ │
│  │  Weather    │───▶│  Simulator   │───▶│   MQTT   │ │
│  │  Fetcher    │    │  (Solar,Wind │    │ Publisher │ │
│  │ (Open-Meteo)│    │  Battery,    │    │          │ │
│  └────────────┘    │  Load, Grid) │    └────┬─────┘ │
│                     └──────────────┘         │       │
└──────────────────────────────────────────────┼───────┘
                                               │
                                               ▼
                                     ┌──────────────────┐
                                     │ Mosquitto Broker  │
                                     │   (MQTT)          │
                                     └──────────────────┘
                                               │
                          ┌────────────────────┼────────────────────┐
                          ▼                    ▼                    ▼
                   ┌────────────┐    ┌──────────────┐    ┌──────────────┐
                   │  FastAPI   │    │   InfluxDB   │    │    React     │
                   │  Backend   │    │   Database   │    │  Dashboard   │
                   └────────────┘    └──────────────┘    └──────────────┘
```

---

## Project Structure

```
sensor_simulator/
├── config.py          # All Parameters
├── weather.py         # Open-Meteo API client with retry logic
├── simulator.py       # Energy simulation engine
├── mqtt_client.py     # MQTT publisher (paho-mqtt)
├── main.py            # Entry point and main loop
├── utils.py           # Shared utilities (logging, timestamps)
├── requirements.txt   # Python dependencies
└── README.md         
```

---

## Prerequisites

- **Python 3.11+**
- **Mosquitto MQTT Broker** running on `localhost:1883`

### Install Mosquitto

**Windows:**
```bash
# Download from https://mosquitto.org/download/
# Or via winget:
winget install EclipseFoundation.Mosquitto
```

**Ubuntu/Debian:**
```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd sensor_simulator
pip install -r requirements.txt
```

### 2. Start Mosquitto Broker

```bash
mosquitto -v
```

### 3. Run the Simulator

```bash
python main.py
```

### 4. Monitor MQTT Messages (optional)

```bash
# Subscribe to all sensor topics
mosquitto_sub -h localhost -t "campus/energy/#" -v
```

---

## MQTT Topics & Payloads

All messages are published as JSON with QoS 1.

| Topic                    | Payload                                                       |
|--------------------------|---------------------------------------------------------------|
| `campus/energy/solar`    | `{"timestamp": "...", "power": 74.5, "unit": "kW"}`          |
| `campus/energy/wind`     | `{"timestamp": "...", "power": 18.3, "unit": "kW"}`          |
| `campus/energy/battery`  | `{"timestamp": "...", "soc": 72.3, "unit": "%"}`             |
| `campus/energy/load`     | `{"timestamp": "...", "power": 61.2, "unit": "kW"}`          |
| `campus/energy/grid`     | `{"timestamp": "...", "power": -31.6, "unit": "kW"}`         |

**Grid Power Convention:**
- **Positive** → Importing from grid (deficit)
- **Negative** → Exporting to grid (surplus)

---

## Configuration

Edit `config.py` to customize:

| Parameter               | Default          | Description                          |
|-------------------------|------------------|--------------------------------------|
| `LATITUDE`              | `13.0827`        | Campus latitude                      |
| `LONGITUDE`             | `80.2707`        | Campus longitude                     |
| `MQTT_BROKER`           | `localhost`      | MQTT broker hostname                 |
| `MQTT_PORT`             | `1883`           | MQTT broker port                     |
| `PUBLISH_INTERVAL`      | `5`              | Seconds between publish cycles       |
| `SOLAR_MAX_CAPACITY_KW` | `100.0`          | Solar panel peak capacity            |
| `WIND_MAX_CAPACITY_KW`  | `50.0`           | Wind turbine rated capacity          |
| `BATTERY_CAPACITY_KWH`  | `200.0`          | Battery storage capacity             |
| `CAMPUS_BASE_LOAD_KW`   | `80.0`           | Base campus electrical load          |

---

## Simulation Models

### Solar
- Sinusoidal curve peaking at solar noon
- Attenuated by cloud cover (up to 85% reduction)
- Zero output outside 06:00–18:00
- ±5% random variation

### Wind
- Cubic power curve (realistic turbine model)
- Cut-in: 3 km/h | Rated: 40 km/h | Cut-out: 90 km/h
- ±5% random variation

### Battery
- Charges on renewable surplus, discharges on deficit
- SoC bounds: 10%–95%
- Charge/discharge rate limits: 30 kW
- Round-trip efficiency: 92%

### Campus Load
- 24-hour demand profile with hourly multipliers
- Smooth interpolation between hours
- ±8% random variation

### Grid
- `Grid = Load − Solar − Wind − Battery_Contribution`
- Balances the energy equation each cycle

---

## Integration

This simulator is designed to work with:

| Component       | Consumes Topics           | Protocol    |
|-----------------|---------------------------|-------------|
| FastAPI Backend | `campus/energy/#`         | MQTT → REST |
| InfluxDB        | `campus/energy/#`         | MQTT → DB   |
| React Dashboard | Via FastAPI WebSocket      | WebSocket   |
| AI Engine       | Historical data from DB    | REST/DB     |

No modifications needed — the simulator publishes standard JSON to MQTT topics that downstream services subscribe to.

---

## License

Internal project — AmpereX Virtual Power Plant.
