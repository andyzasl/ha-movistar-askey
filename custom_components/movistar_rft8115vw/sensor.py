"""Sensors for the Movistar Askey Router integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    """Set up router sensors."""
    async_add_entities(
        [
            ConnectedDevicesSensor(entry.runtime_data),
            LastSuccessfulPollSensor(entry.runtime_data),
        ]
    )


class ConnectedDevicesSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Report the connected-device count and a current inventory attribute."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:devices"
    _attr_name = "Connected devices"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the router's connected-device count."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_connected_devices"

    @property
    def native_value(self) -> int:
        """Return the number of clients in the latest successful poll."""
        return len(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str]]]:
        """Return the current inventory for dashboard and automation use."""
        return {
            "devices": [
                {"name": device.name, "ip": device.ip, "mac": device.mac}
                for device in sorted(
                    self.coordinator.data.values(),
                    key=lambda item: item.name.casefold(),
                )
            ]
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)


class LastSuccessfulPollSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Report when the router last answered a poll successfully."""

    _attr_has_entity_name = True
    _attr_name = "Last successful poll"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the router's last-successful-poll timestamp."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.unique_id}_last_successful_poll"
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the time of the latest successful router poll."""
        return self.coordinator.last_successful_poll

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Return the current run of failed polls."""
        return {"consecutive_failures": self.coordinator.consecutive_failures}

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)
