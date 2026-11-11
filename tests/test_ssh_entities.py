"""Tests for SSH-exclusive sensors and binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.sensor import SensorEntity

from custom_components.movistar_askey import binary_sensor, sensor
from custom_components.movistar_askey.device import (
    repeater_identifier,
    router_identifier,
)
from custom_components.movistar_askey.router import RouterDevice, RouterStatus
from custom_components.movistar_askey.ssh import MovistarAskeySSHClient
from custom_components.movistar_askey.status import RepeaterInfo, RouterSummary


def _make_ssh_coordinator(
    is_ssh: bool = True,
    summary: RouterSummary | None = None,
    repeater: RepeaterInfo | None = None,
) -> MagicMock:
    coord = MagicMock()
    coord.is_ssh = is_ssh
    if is_ssh:
        coord.client = MagicMock(spec=MovistarAskeySSHClient)
    else:
        coord.client = MagicMock()
    coord.data = {
        "AA:BB:CC:DD:EE:01": RouterDevice(
            mac="AA:BB:CC:DD:EE:01",
            ip="192.168.1.10",
            name="Test Device",
            interface="WIFI",
            link=1,
        )
    }
    coord.present = frozenset({"AA:BB:CC:DD:EE:01"})
    coord.last_successful_poll = None
    coord.last_boot = None
    coord.last_update_success = True
    coord.consecutive_failures = 0
    coord.status = RouterStatus(
        summary=summary,
        repeater=repeater,
        wifi_clients={},
        radios={},
    )
    coord.config_entry = MagicMock(
        unique_id="192.168.1.1",
        entry_id="test_entry",
        options={},
    )
    coord.config_entry.data = {"host": "192.168.1.1"}
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


@pytest.mark.anyio
async def test_web_mode_does_not_create_ssh_binary_sensors() -> None:
    """When poll_method is Web (HTTP), SSH-exclusive binary sensors are not created."""
    hass = MagicMock()
    coord = _make_ssh_coordinator(is_ssh=False)
    entry = coord.config_entry
    entry.runtime_data = coord

    created: list[BinarySensorEntity] = []
    await binary_sensor.async_setup_entry(hass, entry, created.extend)

    # Only RouterReachableSensor is created in Web mode
    assert len(created) == 1
    assert created[0].translation_key == "router_reachable"


@pytest.mark.anyio
async def test_ssh_mode_creates_service_and_repeater_binary_sensors() -> None:
    """In SSH mode, service status and repeater link binary sensors are created."""
    hass = MagicMock()
    summary = RouterSummary(
        uptime_seconds=1000,
        cpu_usage=5,
        memory_usage=30,
        firmware="1.0",
        hardware="1.0",
        model="RTF8115VW",
        internet_status="up",
        pppoe_status="up",
        iptv_status="unconfigured",
        voip_status="up",
        sip_status="up",
        phone_number="961311913",
        temp_soc=61.3,
        temp_wifi_24=43.0,
        temp_wifi_5=40.0,
        optical_rx_power=-18.96,
        optical_tx_power=3.16,
        public_ip="88.20.211.172",
    )
    repeater = RepeaterInfo(
        connected=True,
        backhaul_band="5 GHz",
        upstream_bssid="88:33:74:4D:FF:5E",
        agent_mac="B0:14:DF:07:9F:10",
    )
    coord = _make_ssh_coordinator(is_ssh=True, summary=summary, repeater=repeater)
    entry = coord.config_entry
    entry.runtime_data = coord

    created: list[BinarySensorEntity] = []
    await binary_sensor.async_setup_entry(hass, entry, created.extend)

    keys = {e.translation_key: e for e in created}
    assert "router_reachable" in keys
    assert "internet_service" in keys
    assert "pppoe_status" in keys
    assert "voip_status" in keys
    assert "sip_status" in keys
    assert "repeater_link_status" in keys

    # Verify states and device attachments
    assert keys["internet_service"].is_on is True
    assert keys["pppoe_status"].is_on is True
    assert keys["voip_status"].is_on is True
    assert keys["sip_status"].is_on is True
    assert keys["repeater_link_status"].is_on is True
    assert keys["repeater_link_status"].extra_state_attributes == {
        "agent_mac": "B0:14:DF:07:9F:10"
    }

    # Repeater binary sensor must attach to repeater device info
    assert keys["repeater_link_status"].device_info["identifiers"] == {
        repeater_identifier(entry)
    }
    # Router binary sensors attach to router device info
    assert keys["internet_service"].device_info["identifiers"] == {
        router_identifier(entry)
    }


@pytest.mark.anyio
async def test_web_mode_does_not_create_ssh_sensors() -> None:
    """When poll_method is Web, SSH-exclusive sensors are not created."""
    hass = MagicMock()
    coord = _make_ssh_coordinator(is_ssh=False)
    entry = coord.config_entry
    entry.runtime_data = coord

    created: list[SensorEntity] = []
    await sensor.async_setup_entry(hass, entry, created.extend)

    keys = {getattr(e, "translation_key", None) for e in created}
    assert "temperature_soc" not in keys
    assert "temperature_wifi_24" not in keys
    assert "temperature_wifi_5" not in keys
    assert "optical_rx_power" not in keys
    assert "optical_tx_power" not in keys
    assert "public_ip" not in keys
    assert "registered_phone_number" not in keys
    assert "iptv_service_status" not in keys
    assert "repeater_backhaul_band" not in keys
    assert "repeater_upstream_bssid" not in keys


@pytest.mark.anyio
async def test_ssh_mode_creates_temperature_optical_and_repeater_sensors() -> None:
    """In SSH mode, telemetry and repeater sensors are created with values."""
    hass = MagicMock()
    summary = RouterSummary(
        uptime_seconds=1000,
        cpu_usage=5,
        memory_usage=30,
        firmware="1.0",
        hardware="1.0",
        model="RTF8115VW",
        temp_soc=61.3,
        temp_wifi_24=43.0,
        temp_wifi_5=40.0,
        optical_rx_power=-18.96,
        optical_tx_power=3.16,
        public_ip="88.20.211.172",
        phone_number="961311913",
        iptv_status="unconfigured",
    )
    repeater = RepeaterInfo(
        connected=True,
        backhaul_band="2.4 GHz",
        upstream_bssid="8A:33:74:3D:FF:5F",
        agent_mac="B0:14:DF:07:9F:10",
    )
    coord = _make_ssh_coordinator(is_ssh=True, summary=summary, repeater=repeater)
    entry = coord.config_entry
    entry.runtime_data = coord

    created: list[SensorEntity] = []
    await sensor.async_setup_entry(hass, entry, created.extend)

    keys = {getattr(e, "translation_key", None): e for e in created}
    assert keys["temperature_soc"].native_value == 61.3
    assert keys["temperature_wifi_24"].native_value == 43.0
    assert keys["temperature_wifi_5"].native_value == 40.0
    assert keys["optical_rx_power"].native_value == -18.96
    assert keys["optical_tx_power"].native_value == 3.16
    assert keys["public_ip"].native_value == "88.20.211.172"
    assert keys["registered_phone_number"].native_value == "961311913"
    assert keys["iptv_service_status"].native_value == "unconfigured"

    # Repeater sensors
    assert keys["repeater_backhaul_band"].native_value == "2.4 GHz"
    assert keys["repeater_backhaul_band"].device_info["identifiers"] == {
        repeater_identifier(entry)
    }
    assert keys["repeater_upstream_bssid"].native_value == "8A:33:74:3D:FF:5F"
    assert keys["repeater_upstream_bssid"].extra_state_attributes == {
        "agent_mac": "B0:14:DF:07:9F:10"
    }
