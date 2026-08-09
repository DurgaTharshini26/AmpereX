"""
Utility functions for the Sensor Simulator.

Provides common helpers used across modules: timestamp generation,
value clamping, and structured logging setup.
"""

import logging
from datetime import datetime, timezone

from config import LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT


def get_iso_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 format.

    Returns:
        ISO 8601 formatted timestamp string with timezone info.

    Example:
        >>> get_iso_timestamp()
        '2026-07-17T10:30:00.123456+00:00'
    """
    return datetime.now(timezone.utc).isoformat()


def get_local_hour() -> int:
    """Return the current local hour (0–23).

    Uses the system's local timezone to determine the hour, which is
    critical for time-of-day-dependent calculations like solar output
    and campus load profiles.

    Returns:
        Integer hour in range [0, 23].
    """
    return datetime.now().hour


def get_local_minute() -> int:
    """Return the current local minute (0–59).

    Used for sub-hour interpolation in solar curve calculations.

    Returns:
        Integer minute in range [0, 59].
    """
    return datetime.now().minute


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value within the specified bounds.

    Args:
        value: The value to clamp.
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        The clamped value, guaranteed to be within [min_val, max_val].
    """
    return max(min_val, min(value, max_val))


def setup_logger(name: str) -> logging.Logger:
    """Create and configure a named logger.

    Sets up a logger with console output using the format and level
    defined in config.py. Safe to call multiple times for the same
    name — returns the existing logger if already configured.

    Args:
        name: Logger name (typically the module name).

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

        formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

    return logger
