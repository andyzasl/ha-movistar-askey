"""Asynchronous client and parser for compatible Movistar Askey routers."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

_DEVICE_DATA_PATTERN = re.compile(r"var\s+deviceData\s*=\s*([\w\W]+?);")
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_LOGIN_MARKERS = ("loginPassword", "te_acceso_router")


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
        devices[mac] = RouterDevice(mac=mac, ip=ip, name=name)
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

    async def async_get_devices(self) -> dict[str, RouterDevice]:
        """Authenticate and return all currently connected devices."""
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

        if _authentication_failed(page, login_page):
            raise InvalidAuthError("The router rejected the supplied password")
        return parse_device_data(page)

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
