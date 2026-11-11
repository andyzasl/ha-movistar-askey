"""Binary sensors for the Movistar Askey Router integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MovistarAskeyCoordinator
from .device import repeater_device_info, router_device_info
from .router import NODE_REPEATER


@dataclass(frozen=True, kw_only=True)
class RouterBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a binary sensor derived from router summary or WAN diagnosis."""

    is_on_fn: Callable[[MovistarAskeyCoordinator], bool | None]


SSH_ROUTER_SERVICE_BINARY_SENSORS: tuple[RouterBinarySensorDescription, ...] = (
    RouterBinarySensorDescription(
        key="internet_service",
        translation_key="internet_service",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda c: (
            c.status.summary.internet_status.lower() == "up"
            if c.status.summary and c.status.summary.internet_status
            else None
        ),
    ),
    RouterBinarySensorDescription(
        key="pppoe_status",
        translation_key="pppoe_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda c: (
            c.status.summary.pppoe_status.lower() == "up"
            if c.status.summary and c.status.summary.pppoe_status
            else None
        ),
    ),
    RouterBinarySensorDescription(
        key="voip_status",
        translation_key="voip_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda c: (
            c.status.summary.voip_status.lower() == "up"
            if c.status.summary and c.status.summary.voip_status
            else None
        ),
    ),
    RouterBinarySensorDescription(
        key="sip_status",
        translation_key="sip_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda c: (
            c.status.summary.sip_status.lower() == "up"
            if c.status.summary and c.status.summary.sip_status
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up router binary sensors."""
    coordinator: MovistarAskeyCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [RouterReachableSensor(coordinator)]

    if coordinator.is_ssh:
        entities.extend(
            RouterServiceBinarySensor(coordinator, desc)
            for desc in SSH_ROUTER_SERVICE_BINARY_SENSORS
        )

    async_add_entities(entities)

    if coordinator.is_ssh:
        repeater_added = False

        @callback
        def check_repeater_binary_sensors() -> None:
            nonlocal repeater_added
            if repeater_added:
                return
            if coordinator.status.repeater is not None or any(
                d.node == NODE_REPEATER for d in coordinator.data.values()
            ):
                repeater_added = True
                async_add_entities([RepeaterLinkBinarySensor(coordinator)])

        check_repeater_binary_sensors()
        entry.async_on_unload(
            coordinator.async_add_listener(check_repeater_binary_sensors)
        )


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


class RouterServiceBinarySensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    BinarySensorEntity,
):
    """Report WAN and VoIP service connectivity status from SSH diagnosis."""

    _attr_has_entity_name = True
    entity_description: RouterBinarySensorDescription

    def __init__(
        self,
        coordinator: MovistarAskeyCoordinator,
        description: RouterBinarySensorDescription,
    ) -> None:
        """Initialize a router service binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return connectivity state from router summary."""
        return self.entity_description.is_on_fn(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return metadata for the parent router device."""
        return router_device_info(self.coordinator.config_entry)


class RepeaterLinkBinarySensor(
    CoordinatorEntity[MovistarAskeyCoordinator],
    BinarySensorEntity,
):
    """Report whether the mesh repeater is connected to the router."""

    _attr_has_entity_name = True
    _attr_translation_key = "repeater_link_status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MovistarAskeyCoordinator) -> None:
        """Initialize the repeater link binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.unique_id}_repeater_link_status"
        )

    @property
    def available(self) -> bool:
        """Keep sensor available even when repeater is disconnected."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True when repeater is connected."""
        return bool(
            self.coordinator.status.repeater
            and self.coordinator.status.repeater.connected
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return repeater agent MAC if known."""
        if (
            self.coordinator.status.repeater
            and self.coordinator.status.repeater.agent_mac
        ):
            return {"agent_mac": self.coordinator.status.repeater.agent_mac}
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Attach binary sensor to the mesh repeater device."""
        return repeater_device_info(self.coordinator.config_entry)
