"""Sensors for the Movistar Askey Router integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
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
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .clients import access_point_name
from .const import (
    IP_SENSOR_UNIQUE_ID_SUFFIX,
    PERSON_SENSOR_UNIQUE_ID_SUFFIX,
    ROAM_SENSOR_UNIQUE_ID_SUFFIX,
    SIGNAL_SENSOR_UNIQUE_ID_SUFFIX,
)
from .coordinator import MovistarAskeyCoordinator
from .device import repeater_device_info, router_device_info
from .router import NODE_REPEATER
from .signal import signal_sensor_enabled_default
from .status import BAND_5GHZ, BAND_24GHZ


@dataclass(frozen=True, kw_only=True)
class RouterSensorDescription(SensorEntityDescription):
    """Describe a sensor derived from the router's status data."""

    value_fn: Callable[[MovistarAskeyCoordinator], datetime | int | float | str | None]
    attributes_fn: (
        Callable[[MovistarAskeyCoordinator], dict[str, Any] | None] | None
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

SSH_ROUTER_SENSORS: tuple[RouterSensorDescription, ...] = (
    RouterSensorDescription(
        key="temperature_soc",
        translation_key="temperature_soc",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.temp_soc if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="temperature_wifi_24",
        translation_key="temperature_wifi_24",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.temp_wifi_24 if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="temperature_wifi_5",
        translation_key="temperature_wifi_5",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.temp_wifi_5 if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="optical_rx_power",
        translation_key="optical_rx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: (
            c.status.summary.optical_rx_power if c.status.summary else None
        ),
    ),
    RouterSensorDescription(
        key="optical_tx_power",
        translation_key="optical_tx_power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: (
            c.status.summary.optical_tx_power if c.status.summary else None
        ),
    ),
    RouterSensorDescription(
        key="public_ip",
        translation_key="public_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.public_ip if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="registered_phone_number",
        translation_key="registered_phone_number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.phone_number if c.status.summary else None,
    ),
    RouterSensorDescription(
        key="iptv_service_status",
        translation_key="iptv_service_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.status.summary.iptv_status if c.status.summary else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router sensors and per-client signal sensors."""
    coordinator: MovistarAskeyCoordinator = entry.runtime_data
    router_sensors: list[SensorEntity] = [
        *(RouterStatusSensor(coordinator, d) for d in SENSORS),
        RouterRoamSensor(coordinator),
    ]
    if coordinator.is_ssh:
        router_sensors.extend(
            RouterStatusSensor(coordinator, d) for d in SSH_ROUTER_SENSORS
        )
    async_add_entities(router_sensors)

    if coordinator.is_ssh:
        repeater_sensors_added = False

        @callback
        def check_repeater_sensors() -> None:
            nonlocal repeater_sensors_added
            if repeater_sensors_added:
                return
            if coordinator.status.repeater is not None or any(
                d.node == NODE_REPEATER for d in coordinator.data.values()
            ):
                repeater_sensors_added = True
                async_add_entities(
                    [
                        RepeaterStatusSensor(
                            coordinator,
                            key="backhaul_band",
                            translation_key="repeater_backhaul_band",
                            value_fn=lambda c: (
                                c.status.repeater.backhaul_band
                                if c.status.repeater
                                else None
                            ),
                        ),
                        RepeaterStatusSensor(
                            coordinator,
                            key="upstream_bssid",
                            translation_key="repeater_upstream_bssid",
                            value_fn=lambda c: (
                                c.status.repeater.upstream_bssid
                                if c.status.repeater
                                else None
                            ),
                            attributes_fn=lambda c: (
                                {"agent_mac": c.status.repeater.agent_mac}
                                if c.status.repeater and c.status.repeater.agent_mac
                                else None
                            ),
                        ),
                    ]
                )

        check_repeater_sensors()
        entry.async_on_unload(coordinator.async_add_listener(check_repeater_sensors))

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
            for sensor_class in (ClientIpSensor, ClientPersonSensor, ClientRoamSensor)
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
    def native_value(self) -> datetime | int | float | str | None:
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


class ClientRoamSensor(_ClientSensor, RestoreSensor):
    """Count roams of one client between router and repeater or bands."""

    _attr_translation_key = "roams"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _unique_id_suffix = ROAM_SENSOR_UNIQUE_ID_SUFFIX

    async def async_added_to_hass(self) -> None:
        """Restore the count after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            restored = int(last.native_value or 0)
            counts = self.coordinator.roam_counts
            counts[self._mac] = max(counts.get(self._mac, 0), restored)

    @property
    def native_value(self) -> int:
        """Return the number of roams detected for this client."""
        return self.coordinator.roam_counts.get(self._mac, 0)


class RouterRoamSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    RestoreSensor,
):
    """Count roams of all clients."""

    _attr_has_entity_name = True
    _attr_translation_key = "client_roams"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the total roam counter."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_client_roams"

    async def async_added_to_hass(self) -> None:
        """Restore the count after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            restored = int(last.native_value or 0)
            self.coordinator.total_roams = max(self.coordinator.total_roams, restored)

    @property
    def native_value(self) -> int:
        """Return the number of roams detected for all clients."""
        return self.coordinator.total_roams

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)


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


class RepeaterStatusSensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    SensorEntity,
):
    """Expose a sensor on the mesh repeater device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MovistarAskeyCoordinator,
        key: str,
        translation_key: str,
        value_fn: Callable[[MovistarAskeyCoordinator], str | None],
        attributes_fn: (
            Callable[[MovistarAskeyCoordinator], dict[str, Any] | None] | None
        ) = None,
    ) -> None:
        """Initialize a repeater status sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_repeater_{key}"
        self._value_fn = value_fn
        self._attributes_fn = attributes_fn

    @property
    def native_value(self) -> str | None:
        """Return current sensor value."""
        return self._value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return attributes if configured."""
        if self._attributes_fn:
            return self._attributes_fn(self.coordinator)
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Attach sensor to the repeater device."""
        return repeater_device_info(self.coordinator.config_entry)
