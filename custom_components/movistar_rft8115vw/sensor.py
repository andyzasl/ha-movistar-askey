"""Sensors for the Movistar Askey Router integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info
from .status import BAND_5GHZ, BAND_24GHZ


@dataclass(frozen=True, kw_only=True)
class RouterSensorDescription(SensorEntityDescription):
    """Describe a sensor derived from the router's status data."""

    value_fn: Callable[[MovistarAskeyCoordinator], datetime | int | None]
    attributes_fn: (
        Callable[[MovistarAskeyCoordinator], dict[str, int | None]] | None
    ) = None


def _wifi_clients(band: str) -> Callable[[MovistarAskeyCoordinator], int]:
    def value(coordinator: MovistarAskeyCoordinator) -> int:
        # Only count stations that are also in the device map; this excludes
        # mesh backhaul links, which associate without a LAN address.
        return sum(
            client.band == band and mac in coordinator.present
            for mac, client in coordinator.status.wifi_clients.items()
        )

    return value


def _channel(band: str) -> Callable[[MovistarAskeyCoordinator], int | None]:
    def value(coordinator: MovistarAskeyCoordinator) -> int | None:
        radio = coordinator.status.radios.get(band)
        return radio.channel if radio else None

    return value


def _bandwidth(
    band: str,
) -> Callable[[MovistarAskeyCoordinator], dict[str, int | None]]:
    def attributes(coordinator: MovistarAskeyCoordinator) -> dict[str, int | None]:
        radio = coordinator.status.radios.get(band)
        return {"bandwidth_mhz": radio.bandwidth_mhz if radio else None}

    return attributes


SENSORS: tuple[RouterSensorDescription, ...] = (
    RouterSensorDescription(
        key="last_boot",
        name="Last boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_boot,
    ),
    RouterSensorDescription(
        key="cpu_usage",
        name="CPU usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.cpu_usage if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="memory_usage",
        name="Memory usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.memory_usage if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="wifi_clients_24ghz",
        name="Wi-Fi clients 2.4 GHz",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_clients(BAND_24GHZ),
    ),
    RouterSensorDescription(
        key="wifi_clients_5ghz",
        name="Wi-Fi clients 5 GHz",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_clients(BAND_5GHZ),
    ),
    RouterSensorDescription(
        key="channel_24ghz",
        name="Channel 2.4 GHz",
        icon="mdi:access-point",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_channel(BAND_24GHZ),
        attributes_fn=_bandwidth(BAND_24GHZ),
    ),
    RouterSensorDescription(
        key="channel_5ghz",
        name="Channel 5 GHz",
        icon="mdi:access-point",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_channel(BAND_5GHZ),
        attributes_fn=_bandwidth(BAND_5GHZ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router sensors."""
    coordinator: MovistarAskeyCoordinator = entry.runtime_data
    async_add_entities(
        [
            ConnectedDevicesSensor(coordinator),
            LastSuccessfulPollSensor(coordinator),
            *(RouterStatusSensor(coordinator, description) for description in SENSORS),
        ]
    )


class RouterStatusSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Expose one value from the router's optional status data."""

    _attr_has_entity_name = True
    entity_description: RouterSensorDescription

    def __init__(
        self,
        coordinator: MovistarAskeyCoordinator,
        description: RouterSensorDescription,
    ) -> None:
        """Initialize a router status sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{description.key}"

    @property
    def native_value(self) -> datetime | int | None:
        """Return the value from the latest router status."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, int | None] | None:
        """Return optional attributes for this sensor."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)


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
