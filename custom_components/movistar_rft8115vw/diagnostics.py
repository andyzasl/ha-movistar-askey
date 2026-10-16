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
        "status": _status_diagnostics(coordinator),
    }


def _status_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Summarize optional status data without client identifiers."""
    status = coordinator.status
    summary = status.summary
    clients = status.wifi_clients.values()
    return {
        "wifi_clients_by_band": {
            band: sum(client.band == band for client in clients)
            for band in sorted({client.band for client in clients})
        },
        "wifi_clients_in_device_map": sum(
            mac in coordinator.present for mac in status.wifi_clients
        ),
        "access_point_ids": sorted(
            {client.ap_id for client in clients if client.ap_id is not None}
        ),
        "radios": {
            band: {
                "enabled": radio.enabled,
                "channel": radio.channel,
                "bandwidth_mhz": radio.bandwidth_mhz,
            }
            for band, radio in status.radios.items()
        },
        "summary": (
            {
                "model": summary.model,
                "hardware": summary.hardware,
                "firmware": summary.firmware,
                "uptime_seconds": summary.uptime_seconds,
                "cpu_usage": summary.cpu_usage,
                "memory_usage": summary.memory_usage,
            }
            if summary
            else None
        ),
    }
