"""Tests for the Movistar Askey config flow and options flow."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from custom_components.movistar_askey.config_flow import (
    MovistarAskeyOptionsFlow,
    _device_label,
)
from custom_components.movistar_askey.const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_SENSORS,
    CONF_TRACKED_DEVICES,
    DEFAULT_SIGNAL_SENSORS,
)
from custom_components.movistar_askey.router import RouterDevice


def test_device_label_formatting() -> None:
    """Labels format correctly with and without IP or interface."""
    assert (
        _device_label("iPhone", "192.168.1.50", "WIFI") == "iPhone (192.168.1.50, WIFI)"
    )
    assert _device_label("192.168.1.60", "192.168.1.60", "ETH") == "192.168.1.60 (ETH)"
    assert _device_label("MyDevice", None, None) == "MyDevice"


@pytest.mark.anyio
async def test_options_flow_lists_all_devices() -> None:
    """Options flow populates device choices from coordinator and registry."""
    hass = MagicMock()
    dev1 = RouterDevice(
        mac="AA:BB:CC:DD:EE:01",
        ip="192.168.1.50",
        name="iPhone",
        interface="WIFI",
    )
    dev2 = RouterDevice(
        mac="AA:BB:CC:DD:EE:02",
        ip="192.168.1.60",
        name="Living Room TV",
        interface="ETH",
    )

    coordinator = MagicMock()
    coordinator.data = {dev1.mac: dev1, dev2.mac: dev2}
    coordinator.display_name.side_effect = lambda mac, name: name

    config_entry = MagicMock(
        entry_id="test_entry",
        options={
            CONF_SCAN_INTERVAL: 300,
            CONF_CONSIDER_HOME: 600,
            CONF_SIGNAL_SENSORS: DEFAULT_SIGNAL_SENSORS,
            CONF_TRACKED_DEVICES: [dev1.mac],
        },
        runtime_data=coordinator,
    )

    registry = MagicMock()
    registry.async_entries_for_config_entry.return_value = []

    flow = MovistarAskeyOptionsFlow()
    flow.hass = hass

    with (
        patch.object(
            MovistarAskeyOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=config_entry,
        ),
        patch(
            "custom_components.movistar_askey.config_flow.er.async_get",
            return_value=registry,
        ),
        patch.object(
            flow,
            "add_suggested_values_to_schema",
            side_effect=lambda schema, vals: schema,
        ),
    ):
        result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    schema = result["data_schema"]

    # Verify tracked_devices selector exists and includes both devices
    tracked_selector = schema.schema[CONF_TRACKED_DEVICES]
    options = tracked_selector.config["options"]
    option_values = [opt["value"] for opt in options]
    assert dev1.mac in option_values
    assert dev2.mac in option_values


@pytest.mark.anyio
async def test_options_flow_submit_saves_selection() -> None:
    """Submitting the options flow persists chosen tracked devices."""
    flow = MovistarAskeyOptionsFlow()

    user_input = {
        CONF_SCAN_INTERVAL: 120,
        CONF_CONSIDER_HOME: 300,
        CONF_TRACKED_DEVICES: ["AA:BB:CC:DD:EE:01"],
        CONF_SIGNAL_SENSORS: "follow_tracker",
    }

    with patch.object(
        MovistarAskeyOptionsFlow,
        "config_entry",
        new_callable=PropertyMock,
        return_value=MagicMock(options={}),
    ):
        result = await flow.async_step_init(user_input)

    assert result["type"] == "create_entry"
    assert result["data"][CONF_SCAN_INTERVAL] == 120
    assert result["data"][CONF_CONSIDER_HOME] == 300
    assert result["data"][CONF_TRACKED_DEVICES] == ["AA:BB:CC:DD:EE:01"]
    assert result["data"][CONF_SIGNAL_SENSORS] == "follow_tracker"
