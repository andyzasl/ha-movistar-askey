"""Keep per-client Wi-Fi signal and IP sensors enabled according to options."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    CLIENT_SENSOR_UNIQUE_ID_SUFFIXES,
    CONF_SIGNAL_SENSORS,
    DEFAULT_SIGNAL_SENSORS,
    DOMAIN,
    SIGNAL_SENSORS_ALL,
    SIGNAL_SENSORS_FOLLOW_TRACKER,
    SIGNAL_SENSORS_MANUAL,
)

_INTEGRATION = er.RegistryEntryDisabler.INTEGRATION.value

# Sentinel meaning "leave the registry entry unchanged".
NO_CHANGE = "no_change"


def desired_disabled_by(
    mode: str,
    tracker_enabled: bool,
    current: str | None,
) -> str | None:
    """
    Return the disabled_by value a signal sensor should have, or NO_CHANGE.

    Only entries that are enabled or were disabled by the integration are
    managed; a sensor disabled by the user (or anything else) is left alone.
    """
    if mode == SIGNAL_SENSORS_MANUAL or current not in (None, _INTEGRATION):
        return NO_CHANGE
    should_enable = mode == SIGNAL_SENSORS_ALL or (
        mode == SIGNAL_SENSORS_FOLLOW_TRACKER and tracker_enabled
    )
    wanted = None if should_enable else _INTEGRATION
    return NO_CHANGE if wanted == current else wanted


def signal_sensor_mode(entry: ConfigEntry) -> str:
    """Return the configured signal sensor mode."""
    return entry.options.get(CONF_SIGNAL_SENSORS, DEFAULT_SIGNAL_SENSORS)


def _tracker_enabled(registry: er.EntityRegistry, mac: str) -> bool:
    entity_id = registry.async_get_entity_id(Platform.DEVICE_TRACKER, DOMAIN, mac)
    if entity_id is None or (entity := registry.async_get(entity_id)) is None:
        return False
    return entity.disabled_by is None


@callback
def signal_sensor_enabled_default(
    hass: HomeAssistant, entry: ConfigEntry, mac: str
) -> bool:
    """Return whether a newly created signal sensor should start enabled."""
    mode = signal_sensor_mode(entry)
    if mode == SIGNAL_SENSORS_ALL:
        return True
    if mode == SIGNAL_SENSORS_FOLLOW_TRACKER:
        return _tracker_enabled(er.async_get(hass), mac)
    return False


@callback
def async_sync_signal_sensors(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Enable or disable existing signal sensors to match the configured mode."""
    mode = signal_sensor_mode(entry)
    if mode == SIGNAL_SENSORS_MANUAL:
        return
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain != Platform.SENSOR:
            continue
        suffix = next(
            (
                s
                for s in CLIENT_SENSOR_UNIQUE_ID_SUFFIXES
                if entity.unique_id.endswith(s)
            ),
            None,
        )
        if suffix is None:
            continue
        mac = entity.unique_id.removesuffix(suffix)
        current = entity.disabled_by.value if entity.disabled_by else None
        wanted = desired_disabled_by(mode, _tracker_enabled(registry, mac), current)
        if wanted == NO_CHANGE:
            continue
        registry.async_update_entity(
            entity.entity_id,
            disabled_by=er.RegistryEntryDisabler(wanted) if wanted else None,
        )


@callback
def async_track_tracker_changes(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-sync signal sensors when one of this entry's trackers is toggled."""
    if signal_sensor_mode(entry) != SIGNAL_SENSORS_FOLLOW_TRACKER:
        return

    @callback
    def _handle(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        data = event.data
        if data["action"] != "update" or "disabled_by" not in data.get("changes", {}):
            return
        if not data["entity_id"].startswith(f"{Platform.DEVICE_TRACKER}."):
            return
        entity = er.async_get(hass).async_get(data["entity_id"])
        if entity is None or entity.config_entry_id != entry.entry_id:
            return
        async_sync_signal_sensors(hass, entry)

    entry.async_on_unload(
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _handle)
    )
