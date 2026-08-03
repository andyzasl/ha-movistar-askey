"""Polling coordinator for the Movistar Askey Router integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .router import (
    CannotConnectError,
    InvalidAuthError,
    MovistarAskeyClient,
    RouterDevice,
)

_LOGGER = logging.getLogger(__name__)


class MovistarAskeyCoordinator(DataUpdateCoordinator[dict[str, RouterDevice]]):
    """Coordinate a single poll and share the result with all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: MovistarAskeyClient,
        scan_interval: int,
        consider_home: int,
    ) -> None:
        """Initialize coordinated router polling."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.consider_home = max(consider_home, scan_interval)
        self.last_seen: dict[str, datetime] = {}

    async def _async_update_data(self) -> dict[str, RouterDevice]:
        try:
            devices = await self.client.async_get_devices()
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CannotConnectError as err:
            if self.data is None:
                raise ConfigEntryNotReady(str(err)) from err
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected router response: {err}") from err

        now = dt_util.utcnow()
        for mac in devices:
            self.last_seen[mac] = now
        return devices
