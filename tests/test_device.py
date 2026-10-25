"""Tests for shared Home Assistant device metadata."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.helpers import device_registry as dr

from custom_components.movistar_rft8115vw.const import DOMAIN
from custom_components.movistar_rft8115vw.coordinator import MovistarAskeyCoordinator
from custom_components.movistar_rft8115vw.device import (
    client_device_info,
    repeater_identifier,
    router_device_info,
    router_identifier,
)
from custom_components.movistar_rft8115vw.router import (
    NODE_REPEATER,
    RouterDevice,
    RouterStatus,
)


def test_router_identifier_prefers_config_entry_unique_id() -> None:
    """Parent and child devices share the host-based config-entry identity."""
    entry = SimpleNamespace(
        unique_id="192.168.1.1",
        entry_id="fallback-entry-id",
        data={"host": "192.168.1.1"},
    )

    assert router_identifier(entry) == (DOMAIN, "192.168.1.1")
    assert router_device_info(entry)["identifiers"] == {(DOMAIN, "192.168.1.1")}


def test_client_device_info_uses_default_name_and_model() -> None:
    """Client device metadata uses default fields so shared devices keep theirs."""
    entry = SimpleNamespace(unique_id="192.168.1.1", entry_id="entry-1")

    info = client_device_info(
        entry, "aa:bb:cc:dd:ee:ff", "Speaker", model="Wi-Fi client (5 GHz)"
    )

    assert info["connections"] == {(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")}
    assert info["default_name"] == "Speaker"
    assert info["default_model"] == "Wi-Fi client (5 GHz)"
    assert info["via_device"] == router_identifier(entry)
    assert "name" not in info
    assert "model" not in info

    repeater_client = client_device_info(
        entry,
        "aa:bb:cc:dd:ee:ff",
        "Speaker",
        model="Repeater · Wi-Fi",
        node=NODE_REPEATER,
    )
    assert repeater_client["via_device"] == repeater_identifier(entry)


def test_sync_client_devices_only_updates_exclusively_owned_devices() -> None:
    """Devices owned or shared with other integrations are not overwritten."""
    own_mac = "00:bb:cc:dd:ee:01"
    shared_mac = "00:bb:cc:dd:ee:02"
    foreign_mac = "00:bb:cc:dd:ee:03"

    devices = {
        own_mac: RouterDevice(
            mac=own_mac,
            name="phone",
            ip="192.168.1.10",
            interface="ETH",
            link=1,
        ),
        shared_mac: RouterDevice(
            mac=shared_mac,
            name="sonos-zp",
            ip="192.168.1.11",
            interface="ETH",
            link=1,
        ),
        foreign_mac: RouterDevice(
            mac=foreign_mac,
            name="hue-bridge",
            ip="192.168.1.12",
            interface="ETH",
            link=1,
        ),
    }

    router_entry = SimpleNamespace(id="router-device-id")
    by_mac = {
        own_mac: SimpleNamespace(
            id="own-device-id",
            config_entries={"movistar-entry"},
            via_device_id=None,
            model=None,
            name="old",
        ),
        shared_mac: SimpleNamespace(
            id="shared-device-id",
            config_entries={"movistar-entry", "sonos-entry"},
            via_device_id=None,
            model="Sonos One",
            name="Living Room",
        ),
        foreign_mac: SimpleNamespace(
            id="foreign-device-id",
            config_entries={"hue-entry"},
            via_device_id=None,
            model="BSB002",
            name="Philips Hue",
        ),
    }

    registry = MagicMock()

    def get_device(
        identifiers: set[tuple[str, str]] | None = None,
        connections: set[tuple[str, str]] | None = None,
    ) -> SimpleNamespace | None:
        if identifiers:
            return router_entry
        if connections:
            ((_, mac),) = connections
            return by_mac.get(mac)
        return None

    registry.async_get_device.side_effect = get_device

    coordinator = object.__new__(MovistarAskeyCoordinator)
    coordinator.hass = MagicMock()
    coordinator.config_entry = SimpleNamespace(
        unique_id="192.168.1.1",
        entry_id="movistar-entry",
    )
    coordinator.present = frozenset(devices)
    coordinator.status = RouterStatus()
    coordinator.suffixed = set()

    with patch.object(dr, "async_get", return_value=registry):
        coordinator._sync_client_devices(devices)

    registry.async_update_device.assert_called_once_with(
        "own-device-id",
        via_device_id="router-device-id",
        model="Ethernet",
        name="phone",
    )
