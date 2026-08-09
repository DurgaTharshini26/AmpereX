"""
Main entry point for the AmpereX Sensor Simulator.

Orchestrates the continuous simulation loop:
  Fetch Weather → Simulate Sensors → Publish MQTT → Wait → Repeat

Usage:
    python main.py
"""

import signal
import sys
import time

from config import PUBLISH_INTERVAL
from mqtt_client import MQTTPublisher
from simulator import EnergySimulator
from utils import setup_logger
from weather import WeatherFetcher

logger = setup_logger("amperex.main")

# Global flag for graceful shutdown
_running: bool = True


def _signal_handler(signum: int, frame: object) -> None:
    """Handle SIGINT/SIGTERM for graceful shutdown."""
    global _running
    logger.info("Shutdown signal received (signal=%d). Stopping...", signum)
    _running = False


def main() -> None:
    """Run the sensor simulator main loop.

    Initializes all components, then continuously:
    1. Fetches live weather data
    2. Runs one simulation cycle
    3. Publishes all sensor readings via MQTT
    4. Waits for the configured interval

    Handles graceful shutdown on Ctrl+C / SIGTERM.
    """
    global _running

    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("=" * 60)
    logger.info("  AmpereX Sensor Simulator Starting")
    logger.info("  Publish interval: %d seconds", PUBLISH_INTERVAL)
    logger.info("=" * 60)

    # Initialize components
    weather_fetcher = WeatherFetcher()
    simulator = EnergySimulator()
    mqtt_publisher = MQTTPublisher()

    # Connect to MQTT broker
    if not mqtt_publisher.connect():
        logger.error("Failed to connect to MQTT broker. Exiting.")
        sys.exit(1)

    # Allow MQTT connection to establish
    time.sleep(1)

    cycle_count: int = 0

    try:
        while _running:
            cycle_count += 1
            logger.info("--- Cycle %d ---", cycle_count)

            # Step 1: Fetch weather
            weather = weather_fetcher.fetch()

            # Step 2: Run simulation
            readings = simulator.run_cycle(weather)

            # Step 3: Publish to MQTT
            mqtt_publisher.publish_all(readings)

            # Step 4: Wait
            logger.info(
                "Next cycle in %d seconds...\n", PUBLISH_INTERVAL
            )

            # Use short sleep intervals for responsive shutdown
            for _ in range(PUBLISH_INTERVAL * 10):
                if not _running:
                    break
                time.sleep(0.1)

    except Exception as exc:
        logger.critical("Unexpected error in main loop: %s", exc, exc_info=True)
    finally:
        mqtt_publisher.disconnect()
        logger.info("AmpereX Sensor Simulator stopped after %d cycles.", cycle_count)


if __name__ == "__main__":
    main()
