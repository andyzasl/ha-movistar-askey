"""Polling coordinator for the Movistar Askey Router integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FAILURE_TOLERANCE
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
        self.present: frozenset[str] = frozenset()
        self.last_successful_poll: datetime | None = None
        self.consecutive_failures = 0

    async def _async_update_data(self) -> dict[str, RouterDevice]:
        try:
            devices = await self.client.async_get_devices()
        except InvalidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            if self.data is None:
                if isinstance(err, CannotConnectError):
                    raise ConfigEntryNotReady(str(err)) from err
                raise UpdateFailed(f"Unexpected router response: {err}") from err
            return self._handle_poll_failure(err)

        now = dt_util.utcnow()
        for mac in devices:
            self.last_seen[mac] = now
        self.present = frozenset(devices)
        self.last_successful_poll = now
        self.consecutive_failures = 0
        return devices

    def _handle_poll_failure(self, err: Exception) -> dict[str, RouterDevice]:
        """
        Keep entities available through short router or network interruptions.

        A failed poll is a collection gap, not evidence that clients left.
        Trackers fall back to their presence grace period, based on the last
        successful observation, until the failure tolerance is exhausted.
        """
        self.consecutive_failures += 1
        self.present = frozenset()
        if self.consecutive_failures >= FAILURE_TOLERANCE:
            raise UpdateFailed(
                f"Router poll failed {self.consecutive_failures} times in a row: {err}"
            ) from err
        _LOGGER.warning(
            "Router poll failed (%s of %s tolerated): %s",
            self.consecutive_failures,
            FAILURE_TOLERANCE - 1,
            err,
        )
        return self.data
