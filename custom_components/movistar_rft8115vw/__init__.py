"""Modern Home Assistant integration for compatible Movistar Askey routers."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import MovistarAskeyCoordinator
from .device import router_device_info
from .migration import migrate_options_v1, migrate_tracker_unique_id_v1
from .router import MovistarAskeyClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = (Platform.DEVICE_TRACKER, Platform.SENSOR)

type MovistarAskeyConfigEntry = ConfigEntry[MovistarAskeyCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MovistarAskeyConfigEntry,
) -> bool:
    """Set up a Movistar Askey router from a config entry."""
    connector = aiohttp.TCPConnector(force_close=True)
    session = aiohttp.ClientSession(connector=connector)
    client = MovistarAskeyClient(
        session=session,
        host=entry.data[CONF_HOST],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = MovistarAskeyCoordinator(
        hass=hass,
        config_entry=entry,
        client=client,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        consider_home=entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await session.close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register the parent before platform forwarding. Device trackers are added
    # immediately and Home Assistant requires their via_device to already exist.
    summary = coordinator.status.summary
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **router_device_info(
            entry,
            sw_version=summary.firmware if summary else None,
            hw_version=summary.hardware if summary else None,
        ),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: MovistarAskeyConfigEntry,
) -> bool:
    """Migrate entries created by the version 1 integration."""
    if entry.version > 2:
        return False
    if entry.version == 1:

        @callback
        def _migrate_tracker(
            entity: er.RegistryEntry,
        ) -> dict[str, str] | None:
            if entity.domain != Platform.DEVICE_TRACKER:
                return None
            new_id = migrate_tracker_unique_id_v1(entity.unique_id)
            return {"new_unique_id": new_id} if new_id else None

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_tracker)
        hass.config_entries.async_update_entry(
            entry,
            options=migrate_options_v1(dict(entry.options)),
            version=2,
            minor_version=1,
        )
        _LOGGER.info("Migrated config entry %s to version 2", entry.title)
    return True


async def _async_options_updated(
    hass: HomeAssistant,
    entry: MovistarAskeyConfigEntry,
) -> None:
    """Reload the integration after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: MovistarAskeyConfigEntry,
) -> bool:
    """Unload the integration and close its private HTTP session."""
    coordinator = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await coordinator.client.async_close()
    return unloaded
