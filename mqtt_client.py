"""
MQTT client module for publishing sensor data.

Wraps paho-mqtt to provide a clean interface for connecting to a
Mosquitto broker and publishing JSON-formatted sensor readings
to structured topics.
"""

import json

import paho.mqtt.client as mqtt

from config import (
    MQTT_BROKER,
    MQTT_CLIENT_ID,
    MQTT_KEEPALIVE,
    MQTT_PORT,
    MQTT_TOPIC_PREFIX,
)
from utils import get_iso_timestamp, setup_logger

logger = setup_logger(__name__)


class MQTTPublisher:
    """Manages MQTT connection and publishes sensor data as JSON.

    Handles connection lifecycle, automatic reconnection, and
    structured topic publishing with error handling.
    """

    def __init__(
        self,
        broker: str = MQTT_BROKER,
        port: int = MQTT_PORT,
        client_id: str = MQTT_CLIENT_ID,
    ) -> None:
        """Initialize the MQTT publisher.

        Args:
            broker: Hostname or IP of the MQTT broker.
            port: Port number of the MQTT broker.
            client_id: Unique client identifier.
        """
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._is_connected: bool = False

        # Register callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        logger.info("MQTTPublisher initialized for %s:%d", self.broker, self.port)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Callback fired when the broker connection is established."""
        if reason_code == 0:
            self._is_connected = True
            logger.info("Connected to MQTT broker at %s:%d", self.broker, self.port)
        else:
            self._is_connected = False
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        """Callback fired when the broker connection is lost."""
        self._is_connected = False
        logger.warning("Disconnected from MQTT broker (reason: %s)", reason_code)

    def connect(self) -> bool:
        """Connect to the MQTT broker.

        Returns:
            True if connection succeeds, False otherwise.
        """
        try:
            self.client.connect(self.broker, self.port, MQTT_KEEPALIVE)
            self.client.loop_start()
            logger.info("MQTT connection initiated...")
            return True
        except ConnectionRefusedError:
            logger.error("MQTT broker refused connection at %s:%d", self.broker, self.port)
            return False
        except OSError as exc:
            logger.error("MQTT connection error: %s", exc)
            return False

    def disconnect(self) -> None:
        """Gracefully disconnect from the MQTT broker."""
        self.client.loop_stop()
        self.client.disconnect()
        self._is_connected = False
        logger.info("MQTT client disconnected.")

    def _build_topic(self, sensor: str) -> str:
        """Build a fully qualified MQTT topic.

        Args:
            sensor: Sensor name (e.g., 'solar', 'wind').

        Returns:
            Full topic string like 'campus/energy/solar'.
        """
        return f"{MQTT_TOPIC_PREFIX}/{sensor}"

    def publish_solar(self, power_kw: float) -> None:
        """Publish solar panel reading."""
        self._publish(
            "solar",
            {"timestamp": get_iso_timestamp(), "power": power_kw, "unit": "kW"},
        )

    def publish_wind(self, power_kw: float) -> None:
        """Publish wind turbine reading."""
        self._publish(
            "wind",
            {"timestamp": get_iso_timestamp(), "power": power_kw, "unit": "kW"},
        )

    def publish_battery(self, soc: float) -> None:
        """Publish battery state of charge."""
        self._publish(
            "battery",
            {"timestamp": get_iso_timestamp(), "soc": soc, "unit": "%"},
        )

    def publish_load(self, power_kw: float) -> None:
        """Publish campus electrical load."""
        self._publish(
            "load",
            {"timestamp": get_iso_timestamp(), "power": power_kw, "unit": "kW"},
        )

    def publish_grid(self, power_kw: float) -> None:
        """Publish grid power (positive=import, negative=export)."""
        self._publish(
            "grid",
            {"timestamp": get_iso_timestamp(), "power": power_kw, "unit": "kW"},
        )

    def _publish(self, sensor: str, payload: dict) -> None:
        """Serialize and publish a payload to the sensor's topic.

        Args:
            sensor: Sensor name for topic construction.
            payload: Dictionary to serialize as JSON.
        """
        topic = self._build_topic(sensor)
        message = json.dumps(payload)

        try:
            result = self.client.publish(topic, message, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug("Published to %s: %s", topic, message)
            else:
                logger.warning("Publish to %s failed (rc=%d)", topic, result.rc)
        except Exception as exc:
            logger.error("Error publishing to %s: %s", topic, exc)

    def publish_all(self, readings: dict[str, float]) -> None:
        """Publish a complete set of sensor readings.

        Args:
            readings: Dictionary from EnergySimulator.run_cycle() with
                      keys: solar, wind, load, battery_soc, grid.
        """
        self.publish_solar(readings["solar"])
        self.publish_wind(readings["wind"])
        self.publish_battery(readings["battery_soc"])
        self.publish_load(readings["load"])
        self.publish_grid(readings["grid"])

        logger.info("All sensor data published to MQTT.")
