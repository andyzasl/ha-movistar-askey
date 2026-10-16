"""Tests for router session reuse and re-login behaviour."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.movistar_rft8115vw.router import (
    InvalidAuthError,
    MovistarAskeyClient,
)

MAP_PAGE = (
    "var deviceData=[['1','Laptop','','192.168.1.42','','','AA:BB:CC:DD:EE:01']];"
)
LOGIN_PAGE = "<html><form action='te_acceso_router.cgi'>loginPassword</form></html>"
LOGIN_PATH = "/cgi-bin/te_acceso_router.cgi"
MAP_PATH = "/te_mapa_red_local.asp"


class _Morsel:
    def __init__(self, value: str) -> None:
        self.value = value


class _Response:
    def __init__(self, text: str, cookies: dict[str, str] | None = None) -> None:
        self.status = 200
        self._text = text
        self.cookies = {name: _Morsel(value) for name, value in (cookies or {}).items()}

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def text(self) -> str:
        return self._text

    async def read(self) -> bytes:
        return self._text.encode()


class _FakeRouter:
    """Serve a router whose session expires on demand."""

    def __init__(self, *, password_ok: bool = True) -> None:
        self.password_ok = password_ok
        self.valid_session: str | None = None
        self.logins = 0
        self.sessions_issued = 0
        self.requests: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        path = url.removeprefix("http://192.168.1.1") or "/"
        self.requests.append(f"GET {path}")
        if path == "/":
            self.sessions_issued += 1
            return _Response(LOGIN_PAGE, {"SessionID": str(self.sessions_issued)})
        cookie = kwargs.get("headers", {}).get("Cookie", "")
        if self.valid_session and f"SessionID={self.valid_session}" in cookie:
            return _Response(MAP_PAGE)
        return _Response(LOGIN_PAGE)

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.requests.append(f"POST {url.removeprefix('http://192.168.1.1')}")
        self.logins += 1
        if self.password_ok:
            cookie = kwargs["headers"]["Cookie"]
            self.valid_session = cookie.split("SessionID=")[1].split(";")[0]
        return _Response(LOGIN_PAGE)


def _client(router: _FakeRouter) -> MovistarAskeyClient:
    return MovistarAskeyClient(session=router, host="192.168.1.1", password="secret")  # type: ignore[arg-type]


def test_session_is_reused_between_polls() -> None:
    """A valid session is polled without logging in again."""
    router = _FakeRouter()
    client = _client(router)

    assert "AA:BB:CC:DD:EE:01" in asyncio.run(client.async_get_devices())
    assert "AA:BB:CC:DD:EE:01" in asyncio.run(client.async_get_devices())

    assert router.logins == 1
    assert router.requests[-1] == f"GET {MAP_PATH}"


def test_expired_session_triggers_single_relogin() -> None:
    """An expired session is replaced instead of being reported as bad auth."""
    router = _FakeRouter()
    client = _client(router)
    asyncio.run(client.async_get_devices())

    router.valid_session = None
    devices = asyncio.run(client.async_get_devices())

    assert "AA:BB:CC:DD:EE:01" in devices
    assert router.logins == 2


def test_wrong_password_after_fresh_login_is_auth_failure() -> None:
    """Only a fresh login that still lacks the map is invalid auth."""
    router = _FakeRouter(password_ok=False)

    with pytest.raises(InvalidAuthError):
        asyncio.run(_client(router).async_get_devices())

    assert router.logins == 1
    assert f"POST {LOGIN_PATH}" in router.requests
