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


def test_async_sync_signal_sensors_syncs_trackers() -> None:
    """Trackers follow tracked_devices configuration."""
    hass = MagicMock()
    entry = MagicMock(
        entry_id="entry1",
        options={
            "signal_sensors": "all",
            "tracked_devices": ["AA:BB:CC:DD:EE:01"],
        },
    )

    tracker_selected_disabled = MagicMock(
        domain=Platform.DEVICE_TRACKER,
        unique_id="AA:BB:CC:DD:EE:01",
        entity_id="device_tracker.phone",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    tracker_unselected_enabled = MagicMock(
        domain=Platform.DEVICE_TRACKER,
        unique_id="AA:BB:CC:DD:EE:02",
        entity_id="device_tracker.plug",
        disabled_by=None,
    )

    registry = MagicMock()
    with (
        patch(
            "custom_components.movistar_askey.signal.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.movistar_askey.signal.er.async_entries_for_config_entry",
            return_value=[tracker_selected_disabled, tracker_unselected_enabled],
        ),
    ):
        enabled = async_sync_signal_sensors(hass, entry)

    assert enabled == 1
    registry.async_update_entity.assert_any_call(
        "device_tracker.phone", disabled_by=None
    )
    registry.async_update_entity.assert_any_call(
        "device_tracker.plug", disabled_by=er.RegistryEntryDisabler.INTEGRATION
    )
