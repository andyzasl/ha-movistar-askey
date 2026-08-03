"""Modern Home Assistant integration for compatible Movistar Askey routers."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import MovistarAskeyCoordinator
from .router import MovistarAskeyClient

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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
