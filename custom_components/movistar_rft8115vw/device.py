"""Shared Home Assistant device metadata for Movistar Askey routers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DOMAIN, ROUTER_MANUFACTURER, ROUTER_MODEL, ROUTER_NAME
from .router import NODE_REPEATER


def router_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the stable device-registry identifier for the configured router."""
    return (DOMAIN, entry.unique_id or entry.entry_id)


def client_device_info(
    entry: ConfigEntry,
    mac: str,
    name: str,
    model: str | None = None,
    node: str | None = None,
) -> DeviceInfo:
    """Return metadata for a network client, linked to its upstream node."""
    via = (
        repeater_identifier(entry)
        if node == NODE_REPEATER
        else router_identifier(entry)
    )
    info = DeviceInfo(
        connections={(CONNECTION_NETWORK_MAC, mac)},
        default_name=name,
        via_device=via,
    )
    if model:
        info["default_model"] = model
    return info


def repeater_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the device-registry identifier for the mesh repeater."""
    return (DOMAIN, f"{entry.unique_id or entry.entry_id}_repeater")


def repeater_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return metadata for the mesh repeater, linked to the router."""
    return DeviceInfo(
        identifiers={repeater_identifier(entry)},
        name="Mesh repeater",
        model="EasyMesh agent",
        via_device=router_identifier(entry),
    )


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
