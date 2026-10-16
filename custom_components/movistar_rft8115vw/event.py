"""Event entities for the Movistar Askey Router integration."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_CLIENT_ROAMED, EVENT_ROUTER_REBOOTED
from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info

EVENT_TYPE_REBOOTED = "rebooted"
EVENT_TYPE_CLIENT_ROAMED = "client_roamed"


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
        self._attr_event_types = [EVENT_TYPE_REBOOTED, EVENT_TYPE_CLIENT_ROAMED]

    async def async_added_to_hass(self) -> None:
        """Listen for reboot and roam events fired by the coordinator."""
        for bus_event, event_type in (
            (EVENT_ROUTER_REBOOTED, EVENT_TYPE_REBOOTED),
            (EVENT_CLIENT_ROAMED, EVENT_TYPE_CLIENT_ROAMED),
        ):
            self.async_on_remove(
                self.hass.bus.async_listen(bus_event, self._handler(event_type))
            )

    def _handler(self, event_type: str) -> Callable[[Event], None]:
        @callback
        def handle(event: Event) -> None:
            self._trigger_event(event_type, dict(event.data))
            self.async_write_ha_state()

        return handle

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self._entry)
