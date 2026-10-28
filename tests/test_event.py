"""Tests for the router event entity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.event import EventExtraStoredData
from homeassistant.core import Context, Event

from custom_components.movistar_rft8115vw.const import (
    EVENT_CLIENT_ROAMED,
    EVENT_ROUTER_REBOOTED,
)
from custom_components.movistar_rft8115vw.event import (
    EVENT_TYPE_CLIENT_ROAMED,
    EVENT_TYPE_REBOOTED,
    RouterEventEntity,
)


@pytest.fixture
def mock_coordinator() -> SimpleNamespace:
    """Return a minimal mock coordinator."""
    return SimpleNamespace(
        config_entry=SimpleNamespace(
            unique_id="192.168.1.1",
            entry_id="entry-1",
        )
    )


@pytest.mark.anyio
async def test_router_event_entity_preserves_context_and_attributes(
    mock_coordinator: SimpleNamespace,
) -> None:
    """The event entity preserves the trigger event context and sets roam attributes."""
    entity = RouterEventEntity(mock_coordinator)
    entity.hass = MagicMock()
    entity.entity_id = "event.movistar_askey_router_router_event"
    entity.async_write_ha_state = MagicMock()

    context = Context()
    roam_data = {
        "mac": "CE:FD:DE:2D:81:7E",
        "name": "iPhone",
        "client_name": "iPhone",
        "entity_id": "device_tracker.iphone",
        "from_node": "router",
        "to_node": "repeater",
        "from_band": "5 GHz",
        "to_band": None,
        "from_access_point": "router 5 GHz",
        "to_access_point": "repeater",
        "message": "iPhone roamed: router 5 GHz → repeater",
        "roam_count": 2,
    }
    event = Event(EVENT_CLIENT_ROAMED, roam_data, context=context)

    handler = entity._handler(EVENT_TYPE_CLIENT_ROAMED)
    handler(event)

    # Context must match the triggering event
    assert entity._context == context
    # Icon reflects roaming
    assert entity.icon == "mdi:wifi-sync"
    # Attributes must include all roam details and entity linkage
    attrs = entity.state_attributes
    assert attrs["event_type"] == EVENT_TYPE_CLIENT_ROAMED
    assert attrs["client_name"] == "iPhone"
    assert attrs["entity_id"] == "device_tracker.iphone"
    assert attrs["from_access_point"] == "router 5 GHz"
    assert attrs["to_access_point"] == "repeater"
    assert attrs["message"] == "iPhone roamed: router 5 GHz → repeater"
    assert attrs["roam_count"] == 2


@pytest.mark.anyio
async def test_router_event_entity_icon_transitions(
    mock_coordinator: SimpleNamespace,
) -> None:
    """Icon dynamically reflects rebooted vs client_roamed states."""
    entity = RouterEventEntity(mock_coordinator)
    entity.hass = MagicMock()
    entity.entity_id = "event.movistar_askey_router_router_event"
    entity.async_write_ha_state = MagicMock()

    # Initial state
    assert entity.icon == "mdi:restart"

    # Roam event
    roam_event = Event(EVENT_CLIENT_ROAMED, {"mac": "AA:BB:CC:DD:EE:FF"})
    entity._handler(EVENT_TYPE_CLIENT_ROAMED)(roam_event)
    assert entity.icon == "mdi:wifi-sync"

    # Reboot event
    reboot_event = Event(EVENT_ROUTER_REBOOTED, {"uptime_seconds": 60})
    entity._handler(EVENT_TYPE_REBOOTED)(reboot_event)
    assert entity.icon == "mdi:restart"


@pytest.mark.anyio
async def test_router_event_entity_restores_last_event_type(
    mock_coordinator: SimpleNamespace,
) -> None:
    """On HA startup, the last event type is restored to determine icon."""
    entity = RouterEventEntity(mock_coordinator)
    entity.hass = MagicMock()
    entity.entity_id = "event.movistar_askey_router_router_event"

    stored_data = EventExtraStoredData(EVENT_TYPE_CLIENT_ROAMED, {})
    with patch.object(
        entity, "async_get_last_event_data", new_callable=AsyncMock
    ) as mock_last_event_data:
        mock_last_event_data.return_value = stored_data
        await entity.async_added_to_hass()

    assert entity._last_event_type == EVENT_TYPE_CLIENT_ROAMED
    assert entity.icon == "mdi:wifi-sync"
