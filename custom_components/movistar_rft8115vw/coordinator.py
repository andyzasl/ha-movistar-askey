"""Polling coordinator for the Movistar Askey Router integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_ROUTER_REBOOTED, FAILURE_TOLERANCE
from .router import (
    CannotConnectError,
    InvalidAuthError,
    MovistarAskeyClient,
    RouterDevice,
    RouterStatus,
)

_LOGGER = logging.getLogger(__name__)

_BOOT_DRIFT = timedelta(seconds=120)


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
        self.status = RouterStatus()
        self.last_boot: datetime | None = None
        self._last_uptime: int | None = None

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
        await self._async_update_status(now)
        return devices

    async def _async_update_status(self, now: datetime) -> None:
        """Refresh optional Wi-Fi and system status; never fail the poll."""
        try:
            self.status = await self.client.async_get_status()
        except Exception:
            _LOGGER.debug("Router status could not be read", exc_info=True)
            return

        summary = self.status.summary
        if summary is None or summary.uptime_seconds is None:
            return
        uptime = summary.uptime_seconds
        if self._last_uptime is not None and uptime < self._last_uptime:
            self.hass.bus.async_fire(
                EVENT_ROUTER_REBOOTED,
                {
                    "uptime_seconds": uptime,
                    "previous_uptime_seconds": self._last_uptime,
                },
            )
        self._last_uptime = uptime

        boot = now - timedelta(seconds=uptime)
        # Uptime and poll time are read separately; ignore small drift so the
        # boot timestamp does not change on every poll.
        if self.last_boot is None or abs(boot - self.last_boot) > _BOOT_DRIFT:
            self.last_boot = boot

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
