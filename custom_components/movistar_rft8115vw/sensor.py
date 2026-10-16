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
from homeassistant.const import (
    EVENT_STATE_CHANGED,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .clients import access_point_name
from .const import (
    IP_SENSOR_UNIQUE_ID_SUFFIX,
    PERSON_SENSOR_UNIQUE_ID_SUFFIX,
    SIGNAL_SENSOR_UNIQUE_ID_SUFFIX,
)
from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info
from .router import NODE_REPEATER
from .signal import signal_sensor_enabled_default
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
        key="connected_devices",
        translation_key="connected_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: len(c.data),
    ),
    RouterSensorDescription(
        key="last_successful_poll",
        translation_key="last_successful_poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_successful_poll,
        attributes_fn=lambda c: {"consecutive_failures": c.consecutive_failures},
    ),
    RouterSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.last_boot,
    ),
    RouterSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.cpu_usage if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.memory_usage if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="wifi_clients_24ghz",
        translation_key="wifi_clients_24ghz",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_clients(BAND_24GHZ),
    ),
    RouterSensorDescription(
        key="wifi_clients_5ghz",
        translation_key="wifi_clients_5ghz",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_wifi_clients(BAND_5GHZ),
    ),
    RouterSensorDescription(
        key="wifi_clients_repeater",
        translation_key="wifi_clients_repeater",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: sum(
            c.data[mac].node == NODE_REPEATER for mac in c.present if mac in c.data
        ),
    ),
    RouterSensorDescription(
        key="channel_24ghz",
        translation_key="channel_24ghz",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_channel(BAND_24GHZ),
        attributes_fn=_bandwidth(BAND_24GHZ),
    ),
    RouterSensorDescription(
        key="channel_5ghz",
        translation_key="channel_5ghz",
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
    """Set up router sensors and per-client signal sensors."""
    coordinator: MovistarAskeyCoordinator = entry.runtime_data
    async_add_entities(
        RouterStatusSensor(coordinator, description) for description in SENSORS
    )

    signal_tracked: set[str] = set()
    ip_tracked: set[str] = set()

    @callback
    def add_new_client_sensors() -> None:
        new_signal = [
            mac
            for mac in coordinator.status.wifi_clients
            if mac in coordinator.data and mac not in signal_tracked
        ]
        new_ip = [mac for mac in coordinator.data if mac not in ip_tracked]
        signal_tracked.update(new_signal)
        ip_tracked.update(new_ip)
        entities: list[SensorEntity] = [
            ClientSignalSensor(
                coordinator,
                mac,
                enabled_default=signal_sensor_enabled_default(hass, entry, mac),
            )
            for mac in new_signal
        ]
        entities.extend(
            sensor_class(
                coordinator,
                mac,
                enabled_default=signal_sensor_enabled_default(hass, entry, mac),
            )
            for mac in new_ip
            for sensor_class in (ClientIpSensor, ClientPersonSensor)
        )
        if entities:
            async_add_entities(entities)

    add_new_client_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_client_sensors))


class RouterStatusSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Expose one value from the router's status data."""

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
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Return optional attributes for this sensor."""
        if self.entity_description.key == "connected_devices":
            return {
                "devices": [
                    {"name": device.name, "ip": device.ip, "mac": device.mac}
                    for device in sorted(
                        self.coordinator.data.values(),
                        key=lambda item: item.name.casefold(),
                    )
                ]
            }
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)


class _ClientSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Base class for sensors attached to a network client device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unique_id_suffix: str

    def __init__(
        self,
        coordinator: MovistarAskeyCoordinator,
        mac: str,
        enabled_default: bool = False,
    ) -> None:
        """Initialize a client sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}{self._unique_id_suffix}"
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def device_info(self) -> DeviceInfo:
        """Attach the sensor to the client device."""
        return self.coordinator.client_device_info(self._mac)


class ClientSignalSensor(_ClientSensor):
    """Report the router-side signal strength of one Wi-Fi client."""

    _attr_translation_key = "signal_strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unique_id_suffix = SIGNAL_SENSOR_UNIQUE_ID_SUFFIX

    @property
    def native_value(self) -> int | None:
        """Return RSSI while the client is associated with the router."""
        if self._mac not in self.coordinator.present:
            return None
        client = self.coordinator.status.wifi_clients.get(self._mac)
        return client.rssi if client else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return the band and access point of the current association."""
        if self._mac not in self.coordinator.present:
            return {"band": None, "access_point": None}
        client = self.coordinator.status.wifi_clients.get(self._mac)
        device = self.coordinator.data[self._mac]
        return {
            "band": client.band if client else None,
            "access_point": access_point_name(device, client),
        }


class ClientPersonSensor(_ClientSensor):
    """Report which persons use this client's device tracker."""

    _attr_translation_key = "person"
    _unique_id_suffix = PERSON_SENSOR_UNIQUE_ID_SUFFIX

    async def async_added_to_hass(self) -> None:
        """Also update when a person's tracker assignment changes."""
        await super().async_added_to_hass()

        @callback
        def _person_changed(event: Event[EventStateChangedData]) -> None:
            if event.data["entity_id"].startswith("person."):
                self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, _person_changed)
        )

    @property
    def native_value(self) -> str | None:
        """Return the person names, or None when no person uses the tracker."""
        return ", ".join(self.coordinator.person_names(self._mac)) or None


class ClientIpSensor(_ClientSensor):
    """Report the IPv4 address of one network client."""

    _attr_translation_key = "ip_address"
    _unique_id_suffix = IP_SENSOR_UNIQUE_ID_SUFFIX

    @property
    def native_value(self) -> str | None:
        """Return the latest IPv4 address reported by the router."""
        device = self.coordinator.data.get(self._mac)
        if device is None or device.ip in ("", "0.0.0.0"):
            return None
        return device.ip
