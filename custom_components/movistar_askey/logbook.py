"""Describe Movistar Askey Router events in the Home Assistant logbook."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_CLIENT_ROAMED, EVENT_ROUTER_REBOOTED


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Describe roam and reboot events; roams link to the client device."""

    @callback
    def describe_roam(event: Event) -> dict[str, Any]:
        data = event.data
        entry: dict[str, Any] = {
            LOGBOOK_ENTRY_NAME: data.get("name")
            or data.get("client_name")
            or data.get("mac", "Client"),
        }
        if entity_id := data.get("entity_id"):
            entry[LOGBOOK_ENTRY_ENTITY_ID] = entity_id

        from_ap = data.get("from_access_point")
        to_ap = data.get("to_access_point")
        if from_ap and to_ap:
            entry[LOGBOOK_ENTRY_MESSAGE] = f"roamed from {from_ap} to {to_ap}"
        elif msg := data.get("message"):
            entry[LOGBOOK_ENTRY_MESSAGE] = "roamed " + msg.split(": ", 1)[-1]
        else:
            entry[LOGBOOK_ENTRY_MESSAGE] = "roamed"

        return entry

    @callback
    def describe_reboot(event: Event) -> dict[str, Any]:
        return {
            LOGBOOK_ENTRY_NAME: "Movistar Askey Router",
            LOGBOOK_ENTRY_MESSAGE: "rebooted",
        }

    async_describe_event(DOMAIN, EVENT_CLIENT_ROAMED, describe_roam)
    async_describe_event(DOMAIN, EVENT_ROUTER_REBOOTED, describe_reboot)
