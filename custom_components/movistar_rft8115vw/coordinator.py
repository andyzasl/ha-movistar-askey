"""Polling coordinator for the Movistar Askey Router integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .clients import (
    Attachment,
    attachment,
    client_model,
    detect_roams,
    display_name,
    roam_message,
    update_suffixed,
)
from .const import (
    DOMAIN,
    EVENT_CLIENT_ROAMED,
    EVENT_ROUTER_REBOOTED,
    FAILURE_TOLERANCE,
    ISSUE_ROUTER_UNREACHABLE,
)
from .device import client_device_info, repeater_device_info, router_identifier
from .router import (
    NODE_REPEATER,
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
        self.suffixed: set[str] = set()
        self._attachments: dict[str, Attachment] = {}
        # Roam counters; restored by their sensors after a restart.
        self.roam_counts: dict[str, int] = {}
        self.total_roams = 0

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
        if self.consecutive_failures >= FAILURE_TOLERANCE:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ROUTER_UNREACHABLE)
        self.consecutive_failures = 0
        await self._async_update_status(now)
        self.suffixed = update_suffixed(devices, self.suffixed)
        self._detect_roams(devices)
        self._sync_client_devices(devices)
        return devices

    def client_device_info(self, mac: str) -> DeviceInfo:
        """Return device metadata for a network client."""
        device = (self.data or {}).get(mac)
        if device is None:
            return client_device_info(self.config_entry, mac, mac)
        client = self.status.wifi_clients.get(mac)
        return client_device_info(
            self.config_entry,
            mac,
            display_name(device, self.suffixed),
            model=client_model(device, client.band if client else None),
        )

    def _sync_client_devices(self, devices: dict[str, RouterDevice]) -> None:
        """
        Keep each client device's parent node, model and name current.

        Entity device_info is only applied when an entity is added, so roams
        between router and repeater are written to the device registry here.
        """
        registry = dr.async_get(self.hass)
        router = registry.async_get_device(
            identifiers={router_identifier(self.config_entry)}
        )
        if router is None:
            return
        repeater_id: str | None = None
        if any(devices[mac].node == NODE_REPEATER for mac in self.present):
            repeater_id = registry.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                **repeater_device_info(self.config_entry),
            ).id

        for mac in self.present:
            entry = registry.async_get_device(
                connections={(dr.CONNECTION_NETWORK_MAC, mac)}
            )
            if entry is None:
                continue
            device = devices[mac]
            client = self.status.wifi_clients.get(mac)
            via = (
                repeater_id
                if device.node == NODE_REPEATER and repeater_id
                else router.id
            )
            model = client_model(device, client.band if client else None)
            name = display_name(device, self.suffixed)
            if (entry.via_device_id, entry.model, entry.name) != (via, model, name):
                registry.async_update_device(
                    entry.id, via_device_id=via, model=model, name=name
                )

    def display_name(self, mac: str, fallback: str) -> str:
        """Return a unique display name for a client."""
        if (device := (self.data or {}).get(mac)) is None:
            return fallback
        return display_name(device, self.suffixed)

    def person_names(self, mac: str) -> list[str]:
        """Return the names of persons that use this client's device tracker."""
        tracker_id = er.async_get(self.hass).async_get_entity_id(
            Platform.DEVICE_TRACKER, DOMAIN, mac
        )
        if tracker_id is None:
            return []
        return sorted(
            state.name
            for state in self.hass.states.async_all("person")
            if tracker_id in (state.attributes.get("device_trackers") or ())
        )

    def _detect_roams(self, devices: dict[str, RouterDevice]) -> None:
        """Fire an event for clients whose node or band changed since last poll."""
        current = {
            mac: attachment(device, self.status.wifi_clients.get(mac))
            for mac, device in devices.items()
        }
        for mac, before, now in detect_roams(self._attachments, current):
            name = display_name(devices[mac], self.suffixed)
            self.roam_counts[mac] = self.roam_counts.get(mac, 0) + 1
            self.total_roams += 1
            device_entry = dr.async_get(self.hass).async_get_device(
                connections={(dr.CONNECTION_NETWORK_MAC, mac)}
            )
            self.hass.bus.async_fire(
                EVENT_CLIENT_ROAMED,
                {
                    "mac": mac,
                    "name": name,
                    "device_id": device_entry.id if device_entry else None,
                    "from_node": before.node,
                    "to_node": now.node,
                    "from_band": before.band,
                    "to_band": now.band,
                    "message": roam_message(name, before, now),
                    "roam_count": self.roam_counts[mac],
                },
            )
        self._attachments = current

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
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_ROUTER_UNREACHABLE,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_ROUTER_UNREACHABLE,
                translation_placeholders={
                    "failures": str(self.consecutive_failures),
                    "error": str(err),
                },
            )
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
