# Role 5 — MQTT + InfluxDB Integration (AmpereX)

## What's in here

```
role5/
  CONTRACT.md              <- READ THIS FIRST. Push to team's main branch.
  docker-compose.yml        <- spins up Mosquitto + InfluxDB together
  mosquitto/config/
    mosquitto.conf
  subscriber/
    requirements.txt
    .env.example
    dummy_publisher.py      <- fake sensor data, stands in for Member 3
    mqtt_to_influx.py        <- YOUR deliverable: subscribes + stores
```

## How to run it (first time)

1. Start Mosquitto and InfluxDB together:
   ```
   docker compose up -d
   ```

2. Open InfluxDB's UI at http://localhost:8086 and log in with the
   username/password from `docker-compose.yml` (admin / ampereX123).
   The bucket `sensor_data` and org `ampereX` are already created for you
   by the init environment variables.

3. Generate an API token: in the InfluxDB UI, go to
   **Load Data -> API Tokens -> Generate API Token -> All Access Token**.
   Copy it.

4. In `subscriber/`, copy `.env.example` to `.env` and paste your token in:
   ```
   cp .env.example .env
   ```
   (on Windows PowerShell: `copy .env.example .env`)
   Then edit `.env` and set `INFLUX_TOKEN=<the token you copied>`.

5. Install Python dependencies:
   ```
   cd subscriber
   pip install -r requirements.txt
   ```

6. In one terminal, start your subscriber:
   ```
   python mqtt_to_influx.py
   ```

7. In a second terminal, start the dummy publisher to generate test data:
   ```
   python dummy_publisher.py
   ```

8. You should see `published ->` lines in the publisher terminal and
   matching `stored ->` lines in the subscriber terminal. Go back to the
   InfluxDB UI, use **Data Explorer**, pick bucket `sensor_data`,
   measurement `sensor_reading`, and you should see your data plotted.

## When Member 3's real simulator is ready

Nothing in `mqtt_to_influx.py` changes. Just stop running `dummy_publisher.py`
and let Member 3's simulator publish to the same 4 topics instead — as long
as their messages match the JSON shape in `CONTRACT.md`, your subscriber
keeps working exactly as-is. That's the whole point of agreeing on the
contract up front.

## Merging into the team repo

- Put this entire `role5/` content at the repo root (merge `mosquitto/`,
  `subscriber/`, `docker-compose.yml`, and `CONTRACT.md` into `main`,
  ideally in its own branch first, e.g. `member5-mqtt-influx`, then PR it).
- If `docker-compose.yml` already exists in the repo (someone else may add
  services for FastAPI/frontend later), merge your `mosquitto` and
  `influxdb` service blocks into the existing file rather than overwriting it.
- Push `CONTRACT.md` early and tell the team — this is what keeps everyone's
  independently-AI-generated code compatible with yours.
