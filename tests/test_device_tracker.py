"""Tests for the device tracker platform."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.components.device_tracker import SourceType
from homeassistant.util import dt as dt_util

from custom_components.movistar_askey.device_tracker import (
    MovistarAskeyDeviceTracker,
    async_setup_entry,
)
from custom_components.movistar_askey.router import RouterDevice
from custom_components.movistar_askey.status import WifiClient


def _make_device(
    mac: str = "AA:BB:CC:DD:EE:01",
    ip: str = "192.168.1.50",
    name: str = "My Phone",
    interface: str = "WIFI",
    link: int = 1,
) -> RouterDevice:
    return RouterDevice(mac=mac, ip=ip, name=name, interface=interface, link=link)


def _make_coordinator(
    device: RouterDevice,
    is_present: bool = True,
    last_seen: datetime | None = None,
    wifi_client: WifiClient | None = None,
    consider_home: int = 600,
) -> MagicMock:
    coord = MagicMock()
    coord.data = {device.mac: device}
    coord.present = frozenset({device.mac}) if is_present else frozenset()
    coord.last_seen = {device.mac: last_seen or dt_util.utcnow()}
    coord.status.wifi_clients = {device.mac: wifi_client} if wifi_client else {}
    coord.display_name.return_value = device.name
    coord.person_names.return_value = []
    coord.consider_home = consider_home
    coord.config_entry = MagicMock(
        unique_id="192.168.1.1", entry_id="test_entry", options={}
    )
    return coord


def test_device_tracker_entity_defaults() -> None:
    """Device trackers enabled default respects tracked_devices configuration."""
    device = _make_device()
    coord = _make_coordinator(device)

    # By default, without tracked_devices configured, new trackers start disabled
    tracker = MovistarAskeyDeviceTracker(coord, device.mac)
    assert tracker.entity_registry_enabled_default is False
    assert tracker.has_entity_name is True
    assert tracker.unique_id == device.mac
    assert tracker.mac_address == device.mac
    assert tracker.hostname == device.name
    assert tracker.ip_address == device.ip
    assert tracker.source_type == SourceType.ROUTER

    # When device is in tracked_devices, it starts enabled
    coord.config_entry.options = {"tracked_devices": [device.mac]}
    tracker_enabled = MovistarAskeyDeviceTracker(coord, device.mac)
    assert tracker_enabled.entity_registry_enabled_default is True


def test_device_tracker_connection_states() -> None:
    """Tracker accurately reflects present, grace period, and absent states."""
    device = _make_device()
    now = dt_util.utcnow()

    # Case 1: Client is present in router map
    coord = _make_coordinator(device, is_present=True)
    tracker = MovistarAskeyDeviceTracker(coord, device.mac)
    assert tracker.is_connected is True

    # Case 2: Client absent but within grace period
    coord_grace = _make_coordinator(
        device,
        is_present=False,
        last_seen=now - timedelta(seconds=100),
        consider_home=300,
    )
    tracker_grace = MovistarAskeyDeviceTracker(coord_grace, device.mac)
    assert tracker_grace.is_connected is True

    # Case 3: Client absent and grace period expired
    coord_expired = _make_coordinator(
        device,
        is_present=False,
        last_seen=now - timedelta(seconds=500),
        consider_home=300,
    )
    tracker_expired = MovistarAskeyDeviceTracker(coord_expired, device.mac)
    assert tracker_expired.is_connected is False

    # Case 4: Grace period is zero (immediate away)
    coord_zero = _make_coordinator(
        device,
        is_present=False,
        last_seen=now,
        consider_home=0,
    )
    tracker_zero = MovistarAskeyDeviceTracker(coord_zero, device.mac)
    assert tracker_zero.is_connected is False


def test_device_tracker_attributes() -> None:
    """Attributes expose connection details, AP info, and person assignments."""
    device = _make_device()
    wifi_client = WifiClient(
        mac=device.mac,
        band="5 GHz",
        ap_id=1,
        rssi=-55,
        link_rate=866,
        standard="802.11ac",
        associated_seconds=3600,
    )
    coord = _make_coordinator(device, is_present=True, wifi_client=wifi_client)
    coord.person_names.return_value = ["Alice"]

    tracker = MovistarAskeyDeviceTracker(coord, device.mac)
    attrs = tracker.extra_state_attributes

    assert attrs["connection"] == "wifi"
    assert attrs["node"] == "router"
    assert attrs["person"] == "Alice"
    assert attrs["band"] == "5 GHz"
    assert attrs["rssi"] == -55
    assert attrs["link_rate"] == 866
    assert attrs["wifi_standard"] == "802.11ac"
    assert attrs["associated_seconds"] == 3600


@pytest.mark.anyio
async def test_device_tracker_setup_entry() -> None:
    """Async setup creates trackers for known devices and tracks dynamically."""
    device1 = _make_device("AA:BB:CC:DD:EE:01", name="Phone 1")
    device2 = _make_device("AA:BB:CC:DD:EE:02", name="Phone 2")
    coord = _make_coordinator(device1)

    entry = MagicMock()
    entry.runtime_data = coord

    created_trackers: list[MovistarAskeyDeviceTracker] = []

    def mock_add_entities(entities: list[MovistarAskeyDeviceTracker]) -> None:
        created_trackers.extend(entities)

    await async_setup_entry(MagicMock(), entry, mock_add_entities)

    # Initial setup found device1
    assert len(created_trackers) == 1
    assert created_trackers[0].unique_id == device1.mac

    # Dynamic update brings device2
    coord.data[device2.mac] = device2
    # The listener callback was registered via coordinator.async_add_listener
    listener_cb = coord.async_add_listener.call_args[0][0]
    listener_cb()

    assert len(created_trackers) == 2
    assert created_trackers[1].unique_id == device2.mac
