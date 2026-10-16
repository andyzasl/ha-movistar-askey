"""Privacy-preserving diagnostics for the Movistar Askey Router integration."""

from __future__ import annotations

from collections import Counter
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .diag import link_crosstab, summarize_capture


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics without device names, addresses, or credentials."""
    coordinator = entry.runtime_data
    client = coordinator.client
    integration = await async_get_integration(hass, DOMAIN)
    last_error = coordinator.last_exception
    return {
        "integration_version": str(integration.version),
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
        "last_error": type(last_error).__name__ if last_error else None,
        "session": dict(client.stats),
        "status": _status_diagnostics(coordinator),
        "link_vs_association": link_crosstab(
            coordinator.data or {},
            coordinator.present,
            coordinator.status.wifi_clients,
        ),
        "endpoints": {
            name: summarize_capture(name, capture)
            for name, capture in sorted(client.captures.items())
        },
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
        "clients_by_node": dict(
            Counter(
                coordinator.data[mac].node or coordinator.data[mac].interface or "?"
                for mac in coordinator.present
                if mac in coordinator.data
            )
        ),
        "device_map_link_values": dict(
            Counter(
                str(coordinator.data[mac].link)
                for mac in coordinator.present
                if mac in coordinator.data
            )
        ),
        "access_point_ids": sorted(
            {client.ap_id for client in clients if client.ap_id is not None}
        ),
        "stations_per_access_point": {
            f"{band} AP {ap_id}": count
            for (band, ap_id), count in sorted(
                Counter((client.band, client.ap_id) for client in clients).items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1] if item[0][1] is not None else -1,
                ),
            )
        },
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
