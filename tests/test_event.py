"""Tests for the router event entity."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.core import Context, Event

from custom_components.movistar_rft8115vw.const import EVENT_ROUTER_REBOOTED
from custom_components.movistar_rft8115vw.event import (
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
            data={"host": "192.168.1.1"},
        )
    )


def test_router_event_entity_types(mock_coordinator: SimpleNamespace) -> None:
    """The router event entity exposes only the rebooted event type."""
    entity = RouterEventEntity(mock_coordinator)
    assert entity.event_types == [EVENT_TYPE_REBOOTED]
    assert entity.unique_id == "192.168.1.1_router_event"


@pytest.mark.anyio
async def test_router_event_entity_preserves_context_and_attributes(
    mock_coordinator: SimpleNamespace,
) -> None:
    """The event entity preserves trigger context and sets reboot attributes."""
    entity = RouterEventEntity(mock_coordinator)
    entity.hass = MagicMock()
    entity.entity_id = "event.movistar_askey_router_router_event"
    entity.async_write_ha_state = MagicMock()

    context = Context()
    reboot_data = {
        "uptime_seconds": 60,
        "previous_uptime_seconds": 3600,
    }
    event = Event(EVENT_ROUTER_REBOOTED, reboot_data, context=context)

    entity._handle_reboot(event)

    # Context must match the triggering event
    assert entity._context == context
    # Attributes must include reboot details
    attrs = entity.state_attributes
    assert attrs["event_type"] == EVENT_TYPE_REBOOTED
    assert attrs["uptime_seconds"] == 60
    assert attrs["previous_uptime_seconds"] == 3600


@pytest.mark.anyio
async def test_router_event_entity_listens_to_reboot(
    mock_coordinator: SimpleNamespace,
) -> None:
    """The entity listens only for router reboot bus events."""
    entity = RouterEventEntity(mock_coordinator)
    entity.hass = MagicMock()
    entity.async_on_remove = MagicMock()

    await entity.async_added_to_hass()

    entity.hass.bus.async_listen.assert_called_once()
    assert entity.hass.bus.async_listen.call_args[0][0] == EVENT_ROUTER_REBOOTED
