"""Tests for the SSH client, console commands, and topology parsers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import asyncssh
import pytest

from custom_components.movistar_askey.router import (
    LINK_REPEATER,
    LINK_ROUTER_5GHZ,
    LINK_ROUTER_24GHZ,
    NODE_REPEATER,
    NODE_ROUTER,
    CannotConnectError,
    InvalidAuthError,
    RouterParseError,
)
from custom_components.movistar_askey.ssh import (
    MovistarAskeySSHClient,
    parse_ssh_map_info,
    parse_ssh_sys_info,
)

TOPOLOGY_SAMPLE = """dhcp_table
192.168.1.51 2E:47:93:F1:D8:0C dynamic 987654 false
192.168.1.41 DE:48:DB:E8:5F:C4 dynamic 123456 false
Mesh Level N0
wifi station_info
192.168.1.33 24:9E:7D:86:56:95 Movistar_24G HomePod -35
wifi_plus station_info
192.168.1.51 2E:47:93:F1:D8:0C Movistar_5G MacBook Pro -49
eth0_device information
192.168.1.41 DE:48:DB:E8:5F:C4 DesktopPC -20
Mesh Level N1(5GHz)
Agent (B0:14:DF:07:9F:10)
Connected to (88:33:74:4D:FF:5E)
wifi station_info
wifi_plus station_info
192.168.1.43 AA:F5:54:F4:42:9E Movistar_5G iPhone -58
"""


def test_parse_ssh_map_info_extracts_all_devices() -> None:
    """Topology parsing correctly maps router, repeater, and wired clients."""
    devices, wifi_clients, radios = parse_ssh_map_info(TOPOLOGY_SAMPLE)

    assert len(devices) == 4

    # Router 2.4 GHz client
    c24 = devices["24:9E:7D:86:56:95"]
    assert c24.ip == "192.168.1.33"
    assert c24.name == "HomePod"
    assert c24.interface == "WIFI"
    assert c24.link == LINK_ROUTER_24GHZ
    assert c24.node == NODE_ROUTER
    assert wifi_clients["24:9E:7D:86:56:95"].band == "2.4 GHz"
    assert wifi_clients["24:9E:7D:86:56:95"].rssi == -35

    # Router 5 GHz client with multi-word Wi-Fi hostname
    c5 = devices["2E:47:93:F1:D8:0C"]
    assert c5.ip == "192.168.1.51"
    assert c5.name == "MacBook Pro"
    assert c5.interface == "WIFI"
    assert c5.link == LINK_ROUTER_5GHZ
    assert c5.node == NODE_ROUTER
    assert wifi_clients["2E:47:93:F1:D8:0C"].band == "5 GHz"
    assert wifi_clients["2E:47:93:F1:D8:0C"].rssi == -49

    # Repeater client (e.g. iPhone)
    rep = devices["AA:F5:54:F4:42:9E"]
    assert rep.ip == "192.168.1.43"
    assert rep.name == "iPhone"
    assert rep.interface == "WIFI"
    assert rep.link == LINK_REPEATER
    assert rep.node == NODE_REPEATER
    assert wifi_clients["AA:F5:54:F4:42:9E"].band == "5 GHz"
    assert wifi_clients["AA:F5:54:F4:42:9E"].rssi == -58

    # Wired ethernet client
    eth = devices["DE:48:DB:E8:5F:C4"]
    assert eth.ip == "192.168.1.41"
    assert eth.name == "DesktopPC"
    assert eth.interface == "ETH"
    assert eth.link is None
    assert eth.node is None

    # Radios
    assert "2.4 GHz" in radios
    assert "5 GHz" in radios
    assert radios["2.4 GHz"].enabled is True
    assert radios["5 GHz"].enabled is True


def test_parse_ssh_map_info_filters_lease_keywords_and_handles_missing_names() -> None:
    """DHCP lease keywords ('dynamic', 'static') are never used as device names."""
    raw = """dhcp_table
192.168.1.10 11:22:33:44:55:66 dynamic 86400 false
192.168.1.20 AA:BB:CC:DD:EE:FF static 86400 false
Mesh Level N0
wifi station_info
192.168.1.10 11:22:33:44:55:66 MOVISTAR_XXXX iPhone de Andy -45
wifi_plus station_info
192.168.1.20 AA:BB:CC:DD:EE:FF MOVISTAR_PLUS_XXXX -60
"""
    devices, _, _ = parse_ssh_map_info(raw)

    # Device with Wi-Fi hostname receives the parsed hostname
    assert devices["11:22:33:44:55:66"].name == "iPhone de Andy"
    assert devices["11:22:33:44:55:66"].name != "dynamic"

    # Device with only SSID (no hostname) defaults to MAC, never 'static' or 'dynamic'
    assert devices["AA:BB:CC:DD:EE:FF"].name == "AA:BB:CC:DD:EE:FF"
    assert devices["AA:BB:CC:DD:EE:FF"].name != "static"


def test_parse_ssh_map_info_empty_station_tables() -> None:
    """Empty station tables with a valid Mesh Level N0 header return empty devices."""
    empty_topology = """Mesh Level N0
wifi station_info
wifi_plus station_info
"""
    devices, wifi_clients, radios = parse_ssh_map_info(empty_topology)
    assert devices == {}
    assert wifi_clients == {}
    assert "2.4 GHz" in radios
    assert "5 GHz" in radios


def test_parse_ssh_map_info_rejects_unrecognized_output() -> None:
    """Arbitrary text or error messages without mesh nodes raise RouterParseError."""
    with pytest.raises(RouterParseError, match="Unrecognized or empty"):
        parse_ssh_map_info("Invalid privilege: 2\n")


def test_parse_ssh_sys_info() -> None:
    """Sys info outputs extract uptime in seconds and system metrics."""
    text = """uptime 8784
load15Min: 7.48
memory: 45
"""
    summary = parse_ssh_sys_info(text)
    assert summary.uptime_seconds == 8784
    assert summary.cpu_usage == 7
    assert summary.memory_usage == 45

    # Test alternative uptime formatting
    alt_text = "SysUptime: 1234 seconds\n"
    alt_summary = parse_ssh_sys_info(alt_text)
    assert alt_summary.uptime_seconds == 1234


@pytest.mark.anyio
async def test_ssh_client_disallows_unsafe_commands() -> None:
    """Commands outside the allow-list are strictly rejected before execution."""
    client = MovistarAskeySSHClient("192.168.1.1", "secret")
    with pytest.raises(ValueError, match="not allowed"):
        await client.async_run_command("show wifi")
    with pytest.raises(ValueError, match="not allowed"):
        await client.async_run_command("sh")


class _FakeSSHReader:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    async def read(self, n: int) -> str:
        if not self.responses:
            return ""
        return self.responses.pop(0)


class _FakeSSHWriter:
    def __init__(self) -> None:
        self.data: list[str] = []

    def write(self, data: str) -> None:
        self.data.append(data)

    async def drain(self) -> None:
        pass


class _FakeProcess:
    def __init__(self, responses: list[str]) -> None:
        self.stdout = _FakeSSHReader(responses)
        self.stdin = _FakeSSHWriter()
        self.closed = False
        self.waited_closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.waited_closed = True


class _FakeConnection:
    def __init__(self, process: _FakeProcess) -> None:
        self._process = process
        self._closed = False
        self.waited_closed = False

    def is_closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def abort(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        self.waited_closed = True

    async def create_process(self, **kwargs: object) -> _FakeProcess:
        return self._process


@pytest.mark.anyio
async def test_ssh_client_connect_and_session_reuse() -> None:
    """Valid SSH session reuses the PTY connection between calls."""
    process = _FakeProcess(
        [
            " > ",  # initial login prompt
            f"show map_info\r\n{TOPOLOGY_SAMPLE}\r\n > ",
            "show sys_info\r\nuptime 500\r\n > ",
        ]
    )
    fake_conn = _FakeConnection(process)

    with patch.object(asyncssh, "connect", AsyncMock(return_value=fake_conn)):
        client = MovistarAskeySSHClient("192.168.1.1", "secret")
        try:
            devices = await client.async_get_devices()
            assert "2E:47:93:F1:D8:0C" in devices
            assert client.stats["logins"] == 1
            assert client.stats["session_reuses"] == 0

            status = await client.async_get_status()
            assert status.summary is not None
            assert status.summary.uptime_seconds == 500
            assert client.stats["session_reuses"] == 1
            assert client.stats["logins"] == 1
        finally:
            await client.async_close()


@pytest.mark.anyio
async def test_ssh_client_auth_failure() -> None:
    """Permission denied from SSH server raises InvalidAuthError."""
    with patch.object(
        asyncssh,
        "connect",
        AsyncMock(side_effect=asyncssh.PermissionDenied("Auth failed")),
    ):
        client = MovistarAskeySSHClient("192.168.1.1", "wrong_password")
        with pytest.raises(InvalidAuthError):
            await client.async_get_devices()


@pytest.mark.anyio
async def test_ssh_client_connect_failure() -> None:
    """Connection errors or timeouts raise CannotConnectError."""
    with patch.object(
        asyncssh,
        "connect",
        AsyncMock(side_effect=TimeoutError("Connection timed out")),
    ):
        client = MovistarAskeySSHClient("192.168.1.1", "secret")
        with pytest.raises(CannotConnectError):
            await client.async_get_devices()


@pytest.mark.anyio
async def test_ssh_client_reconnects_after_session_drop() -> None:
    """When a command fails with connection error, client reconnects once."""
    # proc1 answers initial login prompt, then raises on command execution
    proc1_responses = [" > ", ConnectionError("Broken pipe")]

    class _DroppingReader:
        async def read(self, n: int) -> str:
            val = proc1_responses.pop(0)
            if isinstance(val, Exception):
                raise val
            return val

    proc1 = _FakeProcess([])
    proc1.stdout = _DroppingReader()  # type: ignore[assignment]
    conn1 = _FakeConnection(proc1)

    proc2 = _FakeProcess(
        [
            " > ",  # reconnect prompt
            f"show map_info\r\n{TOPOLOGY_SAMPLE}\r\n > ",
        ]
    )
    conn2 = _FakeConnection(proc2)

    with patch.object(asyncssh, "connect", AsyncMock(side_effect=[conn1, conn2])):
        client = MovistarAskeySSHClient("192.168.1.1", "secret")
        try:
            devices = await client.async_get_devices()
            assert "2E:47:93:F1:D8:0C" in devices
            assert client.stats["session_expirations"] == 1
            assert client.stats["logins"] == 2
        finally:
            await client.async_close()


@pytest.mark.anyio
async def test_ssh_client_async_close_cleans_resources() -> None:
    """async_close cleanly closes both process and connection and awaits them."""
    process = _FakeProcess([" > ", "show map_info\r\n\r\n > "])
    conn = _FakeConnection(process)

    with patch.object(asyncssh, "connect", AsyncMock(return_value=conn)):
        client = MovistarAskeySSHClient("192.168.1.1", "secret")
        await client.async_run_command("show map_info")
        assert not conn.is_closed()
        assert not process.closed

        await client.async_close()
        assert conn.is_closed()
        assert conn.waited_closed
        assert process.closed
        assert process.waited_closed
        assert client._conn is None
        assert client._process is None
