"""Tests for shared Home Assistant device metadata."""

from types import SimpleNamespace

from custom_components.movistar_rft8115vw.const import DOMAIN
from custom_components.movistar_rft8115vw.device import (
    router_device_info,
    router_identifier,
)


def test_router_identifier_prefers_config_entry_unique_id() -> None:
    """Parent and child devices share the host-based config-entry identity."""
    entry = SimpleNamespace(
        unique_id="192.168.1.1",
        entry_id="fallback-entry-id",
        data={"host": "192.168.1.1"},
    )

    assert router_identifier(entry) == (DOMAIN, "192.168.1.1")
    assert router_device_info(entry)["identifiers"] == {(DOMAIN, "192.168.1.1")}
