"""Tests for Movistar Askey Router logbook event descriptions."""

from unittest.mock import MagicMock

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event

from custom_components.movistar_rft8115vw.const import (
    EVENT_CLIENT_ROAMED,
    EVENT_ROUTER_REBOOTED,
)
from custom_components.movistar_rft8115vw.logbook import async_describe_events


def test_async_describe_events_registers_handlers() -> None:
    """The integration registers logbook handlers for roam and reboot events."""
    hass = MagicMock()
    async_describe_event = MagicMock()

    async_describe_events(hass, async_describe_event)

    registered = {
        call.args[1]: call.args[2] for call in async_describe_event.call_args_list
    }
    assert EVENT_CLIENT_ROAMED in registered
    assert EVENT_ROUTER_REBOOTED in registered


def test_describe_roam_with_access_points_and_entity_id() -> None:
    """Roam description links the client entity and formats access point transit."""
    hass = MagicMock()
    async_describe_event = MagicMock()
    async_describe_events(hass, async_describe_event)
    describe_roam = next(
        call.args[2]
        for call in async_describe_event.call_args_list
        if call.args[1] == EVENT_CLIENT_ROAMED
    )

    event = Event(
        EVENT_CLIENT_ROAMED,
        {
            "mac": "CE:FD:DE:2D:81:7E",
            "name": "iPhone",
            "client_name": "iPhone",
            "entity_id": "device_tracker.iphone",
            "from_access_point": "router 5 GHz",
            "to_access_point": "repeater",
            "message": "iPhone roamed: router 5 GHz → repeater",
        },
    )

    result = describe_roam(event)

    assert result[LOGBOOK_ENTRY_NAME] == "iPhone"
    assert result[LOGBOOK_ENTRY_MESSAGE] == "roamed from router 5 GHz to repeater"
    assert result[LOGBOOK_ENTRY_ENTITY_ID] == "device_tracker.iphone"


def test_describe_roam_fallback_formatting() -> None:
    """Fallback formats message without access points and uses MAC when name missing."""
    hass = MagicMock()
    async_describe_event = MagicMock()
    async_describe_events(hass, async_describe_event)
    describe_roam = next(
        call.args[2]
        for call in async_describe_event.call_args_list
        if call.args[1] == EVENT_CLIENT_ROAMED
    )

    # Legacy event without entity_id or from_access_point
    event = Event(
        EVENT_CLIENT_ROAMED,
        {
            "mac": "CE:FD:DE:2D:81:7E",
            "message": "Client roamed: router → repeater",
        },
    )

    result = describe_roam(event)

    assert result[LOGBOOK_ENTRY_NAME] == "CE:FD:DE:2D:81:7E"
    assert result[LOGBOOK_ENTRY_MESSAGE] == "roamed router → repeater"
    assert LOGBOOK_ENTRY_ENTITY_ID not in result

    # Event without message
    event_empty = Event(EVENT_CLIENT_ROAMED, {"mac": "CE:FD:DE:2D:81:7E"})
    result_empty = describe_roam(event_empty)
    assert result_empty[LOGBOOK_ENTRY_MESSAGE] == "roamed"


def test_describe_reboot() -> None:
    """Router reboot events describe the router rebooting."""
    hass = MagicMock()
    async_describe_event = MagicMock()
    async_describe_events(hass, async_describe_event)
    describe_reboot = next(
        call.args[2]
        for call in async_describe_event.call_args_list
        if call.args[1] == EVENT_ROUTER_REBOOTED
    )

    event = Event(EVENT_ROUTER_REBOOTED, {"uptime_seconds": 120})
    result = describe_reboot(event)

    assert result[LOGBOOK_ENTRY_NAME] == "Movistar Askey Router"
    assert result[LOGBOOK_ENTRY_MESSAGE] == "rebooted"
