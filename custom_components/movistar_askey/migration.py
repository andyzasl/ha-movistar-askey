"""Config-entry migration helpers for the Movistar Askey Router integration."""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

# Option key used by the version 1 integration (luis-garza/movistar_rft8115vw).
LEGACY_CONF_INTERVAL_SECONDS = "interval_seconds"


def migrate_options_v1(options: dict[str, Any]) -> dict[str, int]:
    """Convert version 1 options to version 2, within version 2 limits."""
    scan_interval = int(
        options.get(
            LEGACY_CONF_INTERVAL_SECONDS,
            options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
    )
    scan_interval = min(max(scan_interval, MIN_SCAN_INTERVAL), MAX_SCAN_INTERVAL)
    consider_home = int(options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME))
    consider_home = min(max(consider_home, scan_interval), MAX_SCAN_INTERVAL)
    return {CONF_SCAN_INTERVAL: scan_interval, CONF_CONSIDER_HOME: consider_home}


def migrate_tracker_unique_id_v1(unique_id: str) -> str | None:
    """Return the version 2 tracker unique ID, or None when unchanged."""
    upper = unique_id.upper()
    return upper if upper != unique_id else None
