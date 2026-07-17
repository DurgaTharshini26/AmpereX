"""
mqtt_to_influx.py

Role 5 deliverable: subscribes to all 4 sensor topics over MQTT and writes
every incoming reading into InfluxDB, following the schema in CONTRACT.md.

Run this alongside dummy_publisher.py (or Member 3's real simulator, once
it's ready -- no code change needed here either way, since both speak the
same JSON contract) to see end-to-end storage happening.
"""

import os
import json

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv

load_dotenv()

# --- config, all from .env so nothing is hardcoded per CONTRACT.md section 5 ---
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "campus/+/data"  # wildcard catches solar, wind, battery, load

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "ampereX")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "sensor_data")

influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        print(f"subscribed to {MQTT_TOPIC}")
    else:
        print(f"failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    try:
        # topic looks like: campus/solar/data  -> sensor_type = "solar"
        topic_parts = msg.topic.split("/")
        sensor_type = topic_parts[1] if len(topic_parts) > 1 else "unknown"

        payload = json.loads(msg.payload.decode())

        value = payload.get("value")
        unit = payload.get("unit", "")
        device_id = payload.get("device_id", "unknown")
        timestamp = payload.get("timestamp")

        if value is None:
            print(f"skipped message on {msg.topic}: missing 'value' field")
            return

        point = (
            Point("sensor_reading")          # measurement, per CONTRACT.md
            .tag("sensor_type", sensor_type)
            .tag("device_id", device_id)
            .tag("unit", unit)
            .field("value", float(value))
        )

        if timestamp:
            point = point.time(timestamp)

        write_api.write(bucket=INFLUX_BUCKET, record=point)
        print(f"stored -> {sensor_type}: {value} {unit} (device={device_id})")

    except json.JSONDecodeError:
        print(f"skipped message on {msg.topic}: not valid JSON -> {msg.payload}")
    except Exception as e:
        print(f"error processing message on {msg.topic}: {e}")


def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_HOST, MQTT_PORT, 60)
    print("starting MQTT loop -- Ctrl+C to stop")
    client.loop_forever()


if __name__ == "__main__":
    main()
