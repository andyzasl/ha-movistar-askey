"""Asynchronous client and parser for compatible Movistar Askey routers."""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .status import (
    RADIO_BANDS,
    RadioInfo,
    RouterSummary,
    WifiClient,
    parse_associations,
    parse_radio,
    parse_summary,
)

_DEVICE_DATA_PATTERN = re.compile(r"var\s+deviceData\s*=\s*([\w\W]+?);")
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_LOGIN_MARKERS = ("loginPassword", "te_acceso_router")

_LOGGER = logging.getLogger(__name__)


class MovistarAskeyError(Exception):
    """Base exception for router communication errors."""


class CannotConnectError(MovistarAskeyError):
    """Raised when the router cannot be reached or returns an invalid response."""


class InvalidAuthError(MovistarAskeyError):
    """Raised when the router rejects the supplied credentials."""


class RouterParseError(MovistarAskeyError):
    """Raised when the local-network map cannot be parsed."""


@dataclass(frozen=True, slots=True)
class RouterDevice:
    """A device reported as connected by the router."""

    mac: str
    ip: str
    name: str
    interface: str = ""


@dataclass(frozen=True, slots=True)
class RouterStatus:
    """Optional status data read alongside the device map."""

    wifi_clients: dict[str, WifiClient] = field(default_factory=dict)
    radios: dict[str, RadioInfo] = field(default_factory=dict)
    summary: RouterSummary | None = None


def encode_router_value(value: str) -> str:
    """Apply the reversible encoding used by the Askey login form."""
    return "".join(chr(ord(character) ^ 0x1F) for character in value)


def parse_device_data(page: str) -> dict[str, RouterDevice]:
    """Parse the router's JavaScript deviceData array."""
    match = _DEVICE_DATA_PATTERN.search(page)
    if match is None:
        raise RouterParseError("The router page did not contain deviceData")

    try:
        raw_devices: list[list[Any]] = ast.literal_eval(
            match.group(1).replace("\\", "")
        )
    except (SyntaxError, ValueError) as err:
        raise RouterParseError(
            "The router returned an unreadable deviceData array"
        ) from err

    devices: dict[str, RouterDevice] = {}
    for record in raw_devices:
        if len(record) < 7 or str(record[0]) != "1":
            continue
        mac = str(record[6]).strip().upper().replace("-", ":")
        if not _MAC_PATTERN.fullmatch(mac):
            continue
        ip = str(record[3]).strip()
        name = str(record[1]).strip() or mac
        interface = str(record[4]).strip().upper() if len(record) > 4 else ""
        devices[mac] = RouterDevice(mac=mac, ip=ip, name=name, interface=interface)
    return devices


class MovistarAskeyClient:
    """Fetch the local-network map using the router's web interface."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        password: str,
    ) -> None:
        """Initialize a local router client."""
        self._session = session
        self._base_url = f"http://{host.strip().rstrip('/')}"
        self._password = password
        self._cookies: dict[str, str] = {}

    async def async_get_devices(self) -> dict[str, RouterDevice]:
        """
        Return all currently connected devices.

        The router session is reused between polls. A new login happens only
        when no session exists or the router no longer accepts it, so polling
        does not repeatedly displace other web-interface sessions.
        """
        if self._cookies:
            page = await self._async_get_map_page(self._cookies)
            if "deviceData" in page:
                return parse_device_data(page)
            self._cookies = {}

        cookies, login_page = await self._async_login()
        page = await self._async_get_map_page(cookies)
        if _authentication_failed(page, login_page):
            raise InvalidAuthError("The router rejected the supplied password")
        devices = parse_device_data(page)
        self._cookies = cookies
        return devices

    async def async_get_status(self) -> RouterStatus:
        """
        Return optional Wi-Fi and system status using the current session.

        Call after async_get_devices. Each endpoint is best effort: a failed or
        unsupported endpoint yields no data instead of failing the poll.
        """
        wifi_clients: dict[str, WifiClient] = {}
        radios: dict[str, RadioInfo] = {}
        for radio_id, band in RADIO_BANDS.items():
            if text := await self._async_post_xml(
                "cbListWifiAccPtAssociation.xml", {"dpm_cfg_wifi_id": str(radio_id)}
            ):
                wifi_clients.update(parse_associations(text, band))
            if (
                text := await self._async_post_xml(
                    "cbGetWifi.xml", {"dpm_cfg_wifi_0i": str(radio_id)}
                )
            ) and (radio := parse_radio(text, band)):
                radios[band] = radio

        summary = None
        if text := await self._async_post_xml("cbGetSummary.xml", {}):
            summary = parse_summary(text)
        return RouterStatus(wifi_clients=wifi_clients, radios=radios, summary=summary)

    async def _async_post_xml(self, endpoint: str, data: dict[str, str]) -> str | None:
        """POST to an XML status endpoint and return its body, or None."""
        if not self._cookies:
            return None
        headers = {
            **self._cookie_headers(self._cookies),
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            async with self._session.post(
                f"{self._base_url}/cgi-bin/{endpoint}",
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status >= 400:
                    _LOGGER.debug("%s returned HTTP %s", endpoint, response.status)
                    return None
                return await response.text()
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            _LOGGER.debug("Could not read %s: %s", endpoint, err)
            return None

    async def _async_login(self) -> tuple[dict[str, str], str]:
        """Start a new router session and return its cookies and login page."""
        cookies = await self._async_initial_cookies()
        headers = self._cookie_headers(cookies)

        try:
            async with self._session.post(
                f"{self._base_url}/cgi-bin/te_acceso_router.cgi",
                headers=headers,
                data={
                    "loginUsername": encode_router_value("1234"),
                    "loginPassword": encode_router_value(self._password),
                },
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as response:
                login_page = await response.text()
                if response.status >= 400:
                    raise CannotConnectError(
                        f"Router login returned HTTP {response.status}"
                    )
                cookies.update(self._response_cookies(response))
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CannotConnectError(
                "Could not submit credentials to the router"
            ) from err
        return cookies, login_page

    async def _async_get_map_page(self, cookies: dict[str, str]) -> str:
        """Return the local-network map page for the given session cookies."""
        headers = self._cookie_headers(cookies)
        try:
            async with self._session.get(
                f"{self._base_url}/te_mapa_red_local.asp",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as response:
                page = await response.text()
                if response.status >= 400:
                    raise CannotConnectError(
                        f"Network map returned HTTP {response.status}"
                    )
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CannotConnectError(
                "Could not retrieve the router network map"
            ) from err
        return page

    async def async_test_credentials(self) -> None:
        """Raise a typed exception unless credentials and parser both work."""
        await self.async_get_devices()

    async def async_close(self) -> None:
        """Close the private HTTP session."""
        await self._session.close()

    async def _async_initial_cookies(self) -> dict[str, str]:
        try:
            async with self._session.get(
                self._base_url,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as response:
                await response.read()
                if response.status >= 400:
                    raise CannotConnectError(
                        f"Router landing page returned HTTP {response.status}"
                    )
                return self._response_cookies(response)
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise CannotConnectError("Could not connect to the router") from err

    @staticmethod
    def _response_cookies(response: aiohttp.ClientResponse) -> dict[str, str]:
        return {name: morsel.value for name, morsel in response.cookies.items()}

    @staticmethod
    def _cookie_headers(cookies: dict[str, str]) -> dict[str, str]:
        if not cookies:
            return {}
        return {"Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items())}


def _looks_like_login_page(page: str) -> bool:
    lowered = page.lower()
    return any(marker.lower() in lowered for marker in _LOGIN_MARKERS)


def _authentication_failed(map_page: str, login_page: str) -> bool:
    """
    Return whether the router redirected an unauthenticated client to login.

    Authenticated map pages on the RTF8316VW still contain references to the
    login endpoint, so login markers are only meaningful when deviceData is
    absent from the map response.
    """
    return "deviceData" not in map_page and (
        _looks_like_login_page(map_page) or _looks_like_login_page(login_page)
    )
