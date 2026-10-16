"""Shared Home Assistant device metadata for Movistar Askey routers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, ROUTER_MANUFACTURER, ROUTER_MODEL, ROUTER_NAME


def router_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the stable device-registry identifier for the configured router."""
    return (DOMAIN, entry.unique_id or entry.entry_id)


def router_device_info(
    entry: ConfigEntry,
    sw_version: str | None = None,
    hw_version: str | None = None,
) -> DeviceInfo:
    """Return canonical metadata for the configured router device."""
    info = DeviceInfo(
        identifiers={router_identifier(entry)},
        name=ROUTER_NAME,
        manufacturer=ROUTER_MANUFACTURER,
        model=ROUTER_MODEL,
        configuration_url=f"http://{entry.data['host']}",
    )
    if sw_version:
        info["sw_version"] = sw_version
    if hw_version:
        info["hw_version"] = hw_version
    return info
