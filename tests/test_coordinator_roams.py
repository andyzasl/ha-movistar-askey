"""Tests for coordinator client entity lookup and roam event firing."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.movistar_rft8115vw.clients import Attachment
from custom_components.movistar_rft8115vw.const import (
    DOMAIN,
    EVENT_CLIENT_ROAMED,
    ROAM_SENSOR_UNIQUE_ID_SUFFIX,
)
from custom_components.movistar_rft8115vw.coordinator import MovistarAskeyCoordinator
from custom_components.movistar_rft8115vw.router import RouterDevice, RouterStatus
from custom_components.movistar_rft8115vw.status import WifiClient


def test_client_entity_id_only_uses_own_entities() -> None:
    """Only entities created by this integration are returned."""
    mac = "CE:FD:DE:2D:81:7E"
    entity_reg = MagicMock()

    tracker_enabled = SimpleNamespace(
        entity_id="device_tracker.iphone",
        disabled=False,
    )
    tracker_disabled = SimpleNamespace(
        entity_id="device_tracker.iphone",
        disabled=True,
    )
    roam_sensor_enabled = SimpleNamespace(
        entity_id="sensor.iphone_roams",
        disabled=False,
    )

    coordinator = object.__new__(MovistarAskeyCoordinator)
    coordinator.hass = MagicMock()

    with patch.object(er, "async_get", return_value=entity_reg):
        # Case 1: device tracker created by this integration is enabled
        entity_reg.async_get_entity_id.side_effect = lambda domain, platform, uid: (
            "device_tracker.iphone"
            if (domain, platform, uid) == (Platform.DEVICE_TRACKER, DOMAIN, mac)
            else None
        )
        entity_reg.async_get.return_value = tracker_enabled
        assert coordinator.client_entity_id(mac) == "device_tracker.iphone"

        # Case 2: device tracker is disabled, but client roam sensor is enabled
        def lookup_entity_id(domain: str, platform: str, uid: str) -> str | None:
            if platform != DOMAIN:
                return None
            if (domain, uid) == (Platform.DEVICE_TRACKER, mac):
                return "device_tracker.iphone"
            if (domain, uid) == (
                Platform.SENSOR,
                f"{mac}{ROAM_SENSOR_UNIQUE_ID_SUFFIX}",
            ):
                return "sensor.iphone_roams"
            return None

        def lookup_entry(entity_id: str) -> SimpleNamespace | None:
            if entity_id == "device_tracker.iphone":
                return tracker_disabled
            if entity_id == "sensor.iphone_roams":
                return roam_sensor_enabled
            return None

        entity_reg.async_get_entity_id.side_effect = lookup_entity_id
        entity_reg.async_get.side_effect = lookup_entry
        assert coordinator.client_entity_id(mac) == "sensor.iphone_roams"

        # Case 3: all integration entities disabled -> fallback to own device_tracker
        entity_reg.async_get.side_effect = lambda entity_id: tracker_disabled
        assert coordinator.client_entity_id(mac) == "device_tracker.iphone"

        # Case 4: no entity created by this integration exists
        entity_reg.async_get_entity_id.side_effect = lambda domain, platform, uid: None
        assert coordinator.client_entity_id(mac) is None


def test_detect_roams_fires_detailed_event() -> None:
    """Roam detection fires EVENT_CLIENT_ROAMED with entity ID and access points."""
    mac = "CE:FD:DE:2D:81:7E"
    coordinator = object.__new__(MovistarAskeyCoordinator)
    coordinator.hass = MagicMock()
    coordinator.suffixed = set()
    coordinator.roam_counts = {}
    coordinator.total_roams = 0
    coordinator.status = RouterStatus(
        wifi_clients={
            mac: WifiClient(
                mac=mac,
                band="5 GHz",
                ap_id=1,
                rssi=-50,
                link_rate="400 Mbps",
                standard="11ac",
                associated_seconds=60,
            )
        }
    )

    # Previous poll: client was on repeater
    coordinator._attachments = {mac: Attachment(node="repeater", band=None)}

    # Current poll: client is on router 5 GHz
    devices = {
        mac: RouterDevice(
            mac=mac,
            name="iPhone",
            ip="192.168.1.50",
            interface="WIFI",
            link=0,
        )
    }

    device_entry = SimpleNamespace(id="device-entry-id")
    device_reg = MagicMock()
    device_reg.async_get_device.return_value = device_entry

    with (
        patch.object(dr, "async_get", return_value=device_reg),
        patch.object(
            coordinator,
            "client_entity_id",
            return_value="device_tracker.iphone",
        ),
    ):
        coordinator._detect_roams(devices)

    assert coordinator.total_roams == 1
    assert coordinator.roam_counts[mac] == 1

    coordinator.hass.bus.async_fire.assert_called_once()
    event_type, payload = coordinator.hass.bus.async_fire.call_args[0]
    assert event_type == EVENT_CLIENT_ROAMED
    assert payload["mac"] == mac
    assert payload["name"] == "iPhone"
    assert payload["client_name"] == "iPhone"
    assert payload["entity_id"] == "device_tracker.iphone"
    assert payload["device_id"] == "device-entry-id"
    assert payload["from_node"] == "repeater"
    assert payload["to_node"] == "router"
    assert payload["from_band"] is None
    assert payload["to_band"] == "5 GHz"
    assert payload["from_access_point"] == "repeater"
    assert payload["to_access_point"] == "router 5 GHz"
    assert payload["message"] == "iPhone roamed: repeater → router 5 GHz"
    assert payload["roam_count"] == 1
