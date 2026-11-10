"""Tests for the Wi-Fi signal sensor enablement policy."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er

from custom_components.movistar_askey.signal import (
    NO_CHANGE,
    async_sync_signal_sensors,
    desired_disabled_by,
)

INTEGRATION = "integration"
USER = "user"


@pytest.mark.parametrize(
    ("mode", "tracker_enabled", "current", "expected"),
    [
        # Manual never touches the registry.
        ("manual", True, INTEGRATION, NO_CHANGE),
        ("manual", False, None, NO_CHANGE),
        # All enables integration-disabled sensors.
        ("all", False, INTEGRATION, None),
        ("all", False, None, NO_CHANGE),
        # Follow tracker mirrors the tracker state.
        ("follow_tracker", True, INTEGRATION, None),
        ("follow_tracker", True, None, NO_CHANGE),
        ("follow_tracker", False, None, INTEGRATION),
        ("follow_tracker", False, INTEGRATION, NO_CHANGE),
        # A sensor disabled by the user is never changed.
        ("all", True, USER, NO_CHANGE),
        ("follow_tracker", True, USER, NO_CHANGE),
    ],
)
def test_desired_disabled_by(
    mode: str, tracker_enabled: bool, current: str | None, expected: str | None
) -> None:
    """The policy enables, disables or leaves sensors as specified."""
    assert desired_disabled_by(mode, tracker_enabled, current) == expected


def test_async_sync_signal_sensors_reenables_trackers() -> None:
    """Trackers disabled by integration are restored to enabled status."""
    hass = MagicMock()
    entry = MagicMock(entry_id="entry1", options={"signal_sensors": "all"})

    tracker_integration_disabled = MagicMock(
        domain=Platform.DEVICE_TRACKER,
        entity_id="device_tracker.phone",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    tracker_user_disabled = MagicMock(
        domain=Platform.DEVICE_TRACKER,
        entity_id="device_tracker.plug",
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    registry = MagicMock()
    with (
        patch(
            "custom_components.movistar_askey.signal.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.movistar_askey.signal.er.async_entries_for_config_entry",
            return_value=[tracker_integration_disabled, tracker_user_disabled],
        ),
    ):
        enabled = async_sync_signal_sensors(hass, entry)

    assert enabled == 1
    registry.async_update_entity.assert_called_once_with(
        "device_tracker.phone", disabled_by=None
    )
