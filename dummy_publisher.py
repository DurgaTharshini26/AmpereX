"""
dummy_publisher.py

Stands in for Member 3's real sensor simulator. Publishes fake-but-shaped-
correctly readings to the 4 topics every few seconds, so you can build and
test your MQTT -> InfluxDB pipeline without waiting on anyone else.

Once Member 3's real simulator is ready, you just stop running this file --
your subscriber.py doesn't change at all, since both publish the exact same
JSON shape defined in CONTRACT.md.
"""

import os
import json
import time
import random
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

# sensor_type -> (unit, (min, max) plausible range)
SENSORS = {
    "solar":   {"unit": "watts",   "range": (0, 5000)},
    "wind":    {"unit": "watts",   "range": (0, 2000)},
    "battery": {"unit": "percent", "range": (0, 100)},
    "load":    {"unit": "watts",   "range": (500, 4000)},
}


def make_reading(sensor_type: str) -> dict:
    lo, hi = SENSORS[sensor_type]["range"]
    return {
        "value": round(random.uniform(lo, hi), 2),
        "unit": SENSORS[sensor_type]["unit"],
        "device_id": f"{sensor_type}-sim-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    client = mqtt.Client()
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()

    print(f"Connected to {MQTT_HOST}:{MQTT_PORT}")
    print("Publishing dummy sensor data every 3s. Ctrl+C to stop.\n")

    try:
        while True:
            for sensor_type in SENSORS:
                topic = f"campus/{sensor_type}/data"
                reading = make_reading(sensor_type)
                client.publish(topic, json.dumps(reading))
                print(f"published -> {topic}: {reading}")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
