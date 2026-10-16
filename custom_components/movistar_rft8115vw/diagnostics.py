"""Privacy-preserving diagnostics for the Movistar Askey Router integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics without device names, addresses, or credentials."""
    coordinator = entry.runtime_data
    return {
        "config_entry": async_redact_data(entry.as_dict(), {CONF_PASSWORD}),
        "router_available": coordinator.last_update_success,
        "connected_device_count": len(coordinator.data or {}),
        "polling_interval_seconds": int(coordinator.update_interval.total_seconds()),
        "presence_grace_seconds": coordinator.consider_home,
        "consecutive_failures": coordinator.consecutive_failures,
        "last_successful_poll": (
            coordinator.last_successful_poll.isoformat()
            if coordinator.last_successful_poll
            else None
        ),
    }
