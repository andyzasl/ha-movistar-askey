"""Modern config-entry device trackers for Movistar Askey routers."""

from __future__ import annotations

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .clients import access_point_name
from .coordinator import MovistarAskeyCoordinator

_CONNECTION_TYPES = {"WIFI": "wifi", "ETH": "ethernet"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create trackers dynamically as clients are first observed."""
    coordinator: MovistarAskeyCoordinator = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def add_new_devices() -> None:
        new_macs = [mac for mac in coordinator.data if mac not in tracked]
        if not new_macs:
            return
        tracked.update(new_macs)
        async_add_entities(
            MovistarAskeyDeviceTracker(coordinator, mac) for mac in new_macs
        )

    add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_new_devices))


class MovistarAskeyDeviceTracker(
    CoordinatorEntity[MovistarAskeyCoordinator],
    ScannerEntity,
):
    """Represent a network client detected by the router."""

    _attr_entity_registry_enabled_default = False
    _attr_source_type = SourceType.ROUTER

    def __init__(self, coordinator: MovistarAskeyCoordinator, mac: str) -> None:
        """Initialize one disabled-by-default client tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = mac
        self._cached_device = coordinator.data[mac]

    @callback
    def _handle_coordinator_update(self) -> None:
        if device := self.coordinator.data.get(self._mac):
            self._cached_device = device
        super()._handle_coordinator_update()

    @property
    def name(self) -> str:
        """Return the client name, made unique with a MAC suffix if needed."""
        return self.coordinator.display_name(self._mac, self._cached_device.name)

    @property
    def is_connected(self) -> bool:
        """Return whether the client is present within the grace period."""
        if self._mac in self.coordinator.present:
            return True
        last_seen = self.coordinator.last_seen.get(self._mac)
        if last_seen is None or self.coordinator.consider_home == 0:
            return False
        return (
            dt_util.utcnow() - last_seen
        ).total_seconds() < self.coordinator.consider_home

    @property
    def mac_address(self) -> str:
        """Return the stable network identifier used by the router."""
        return self._mac

    @property
    def hostname(self) -> str:
        """Return the latest reported hostname."""
        return self._cached_device.name

    @property
    def ip_address(self) -> str:
        """Return the latest reported IPv4 address."""
        return self._cached_device.ip

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None]:
        """Return connection, mesh node and, for router Wi-Fi, link details."""
        device = self._cached_device
        is_present = self._mac in self.coordinator.present
        client = (
            self.coordinator.status.wifi_clients.get(self._mac) if is_present else None
        )
        attributes: dict[str, str | int | bool | None] = {
            "connection": _CONNECTION_TYPES.get(device.interface),
            "node": device.node if is_present else None,
            "access_point": access_point_name(device, client) if is_present else None,
            "private_mac": device.is_private_mac,
        }
        if client:
            attributes.update(
                band=client.band,
                ap_id=client.ap_id,
                rssi=client.rssi,
                link_rate=client.link_rate,
                wifi_standard=client.standard,
                associated_seconds=client.associated_seconds,
            )
        return attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Link this client device to the router device."""
        return self.coordinator.client_device_info(self._mac)
