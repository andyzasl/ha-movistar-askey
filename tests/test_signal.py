"""Tests for the Wi-Fi signal sensor enablement policy."""

import pytest

from custom_components.movistar_rft8115vw.signal import (
    NO_CHANGE,
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
