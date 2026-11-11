"""Tests for the Movistar Askey config flow and options flow."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from custom_components.movistar_askey.config_flow import (
    MovistarAskeyConfigFlow,
    MovistarAskeyOptionsFlow,
    _device_label,
)
from custom_components.movistar_askey.const import (
    CONF_CONSIDER_HOME,
    CONF_POLL_METHOD,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_SENSORS,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_TRACKED_DEVICES,
    DEFAULT_SIGNAL_SENSORS,
    POLL_METHOD_SSH,
)
from custom_components.movistar_askey.router import (
    CannotConnectError,
    RouterDevice,
)


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


@pytest.mark.anyio
async def test_user_flow_ssh_transition_and_submit() -> None:
    """Choosing SSH poll method prompts for SSH settings and creates entry."""
    flow = MovistarAskeyConfigFlow()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()

    # Step 1: User enters host and chooses SSH
    res1 = await flow.async_step_user(
        {
            "host": "192.168.1.1",
            "password": "web_password",
            CONF_POLL_METHOD: POLL_METHOD_SSH,
        }
    )
    assert res1["type"] == "form"
    assert res1["step_id"] == "ssh"

    # Step 2: User configures SSH
    with patch(
        "custom_components.movistar_askey.config_flow._async_validate_ssh",
        new=AsyncMock(),
    ) as mock_val:
        res2 = await flow.async_step_ssh(
            {
                CONF_SSH_USERNAME: "1234",
                CONF_SSH_PORT: 22,
            }
        )

    mock_val.assert_called_once_with("192.168.1.1", "web_password", "1234", 22, None)
    assert res2["type"] == "create_entry"
    assert res2["options"][CONF_POLL_METHOD] == POLL_METHOD_SSH
    assert res2["options"][CONF_SSH_USERNAME] == "1234"
    assert res2["options"][CONF_SSH_PORT] == 22


@pytest.mark.anyio
async def test_options_flow_switch_to_ssh_success() -> None:
    """Switching to SSH in options validates SSH and updates options."""
    flow = MovistarAskeyOptionsFlow()
    config_entry = MagicMock(
        data={"host": "192.168.1.1", "password": "web_password"},
        options={},
    )

    with (
        patch.object(
            MovistarAskeyOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=config_entry,
        ),
        patch(
            "custom_components.movistar_askey.config_flow._async_validate_ssh",
            new=AsyncMock(),
        ) as mock_val,
    ):
        res = await flow.async_step_init(
            {
                CONF_SCAN_INTERVAL: 60,
                CONF_CONSIDER_HOME: 120,
                CONF_POLL_METHOD: POLL_METHOD_SSH,
                CONF_SSH_PORT: 2222,
                CONF_SSH_USERNAME: "support",
            }
        )

    mock_val.assert_called_once_with(
        "192.168.1.1", "web_password", "support", 2222, None
    )
    assert res["type"] == "create_entry"
    assert res["data"][CONF_POLL_METHOD] == POLL_METHOD_SSH
    assert res["data"][CONF_SSH_PORT] == 2222
    assert res["data"][CONF_SSH_USERNAME] == "support"


@pytest.mark.anyio
async def test_options_flow_switch_to_ssh_failure() -> None:
    """Failing SSH validation redisplays options form with error."""
    flow = MovistarAskeyOptionsFlow()
    config_entry = MagicMock(
        data={"host": "192.168.1.1", "password": "web_password"},
        options={},
    )

    with (
        patch.object(
            MovistarAskeyOptionsFlow,
            "config_entry",
            new_callable=PropertyMock,
            return_value=config_entry,
        ),
        patch(
            "custom_components.movistar_askey.config_flow._async_validate_ssh",
            side_effect=CannotConnectError("Connection refused"),
        ),
        patch(
            "custom_components.movistar_askey.config_flow.er.async_get",
            return_value=MagicMock(async_entries_for_config_entry=lambda *_: []),
        ),
        patch.object(
            flow,
            "add_suggested_values_to_schema",
            side_effect=lambda schema, vals: schema,
        ),
    ):
        res = await flow.async_step_init(
            {
                CONF_SCAN_INTERVAL: 60,
                CONF_CONSIDER_HOME: 120,
                CONF_POLL_METHOD: POLL_METHOD_SSH,
            }
        )

    assert res["type"] == "form"
    assert res["step_id"] == "init"
    assert res["errors"] == {"base": "cannot_connect"}
