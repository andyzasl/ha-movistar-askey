"""Event entities for the Movistar Askey Router integration."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_ROUTER_REBOOTED
from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info

EVENT_TYPE_REBOOTED = "rebooted"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router event entities."""
    async_add_entities([RouterEventEntity(entry.runtime_data)])


class RouterEventEntity(EventEntity):
    """Expose router lifecycle events, such as reboots, as an event entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "router_event"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the router event entity."""
        self._entry = coordinator.config_entry
        self._attr_unique_id = f"{self._entry.unique_id}_router_event"
        self._attr_event_types = [EVENT_TYPE_REBOOTED]

    async def async_added_to_hass(self) -> None:
        """Listen for reboot events fired by the coordinator."""
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_ROUTER_REBOOTED, self._handle_reboot)
        )

    @callback
    def _handle_reboot(self, event: Event) -> None:
        self._trigger_event(EVENT_TYPE_REBOOTED, dict(event.data))
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self._entry)
