"""Binary sensors for the Movistar Askey Router integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router binary sensors."""
    async_add_entities([RouterReachableSensor(entry.runtime_data)])


class RouterReachableSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    BinarySensorEntity,
):
    """Report whether the latest router poll succeeded."""

    _attr_has_entity_name = True
    _attr_translation_key = "router_reachable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the router reachability sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_reachable"

    @property
    def available(self) -> bool:
        """Stay available so that an unreachable router reports off."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when the latest poll reached the router."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.consecutive_failures == 0
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)
