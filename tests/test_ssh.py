"""Tests for the SSH client, console commands, and topology parsers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import asyncssh
import pytest

from custom_components.movistar_askey.clients import display_name, update_suffixed
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


def test_parse_ssh_sys_info_askey_memory_calculation() -> None:
    """Askey Linux commitLimit and freeMem are used to calculate real memory usage %."""
    text = """uptime 3359
load15Min 7.25
freeMem 500264
commitLimit 454672
committedMem 134880
"""
    summary = parse_ssh_sys_info(text)
    assert summary.uptime_seconds == 3359
    assert summary.cpu_usage == 7
    # commitLimit = 454672 kB -> MemTotal = 909344 kB
    # freeMem = 500264 kB -> used = 409080 kB -> 44.98% -> 45%
    assert summary.memory_usage == 45


def test_parse_ssh_map_info_live_askey_topology() -> None:
    """Real Askey router map_info extracts hostnames and resolves Ethernet."""
    sample = """dhcp_table
192.168.1.33 24:9E:7D:86:56:95 dynamic 39990 WiFi 2.4GHz SSID roborock true
192.168.1.34 8A:DE:79:12:F0:06 dynamic 40012 WiFi 5 GHz SSID iPhone true
192.168.1.35 C6:86:EC:9E:BB:1A dynamic 40032 WiFi 5 GHz SSID iPhone false
192.168.1.36 AA:F5:54:F4:42:9E dynamic 41492 WiFi 5 GHz SSID Watch false
192.168.1.38 B8:82:F2:C5:9D:B9 dynamic 39990 WiFi 2.4GHz SSID true
192.168.1.40 2C:8D:48:4C:EA:B9 dynamic 40001 WiFi 2.4GHz SSID Eufy Device true
192.168.1.41 DE:48:DB:E8:5F:C4 dynamic 39990 WiFi 5 GHz SSID Mac true
192.168.1.135 90:09:D0:26:02:11 dynamic 39917 Ethernet SynHome true
192.168.1.66 02:42:C0:A8:01:42 static 0 Ethernet true
arp_table
192.168.1.33 24:9E:7D:86:56:95 39990 WiFi 2.4GHz SSID roborock true
Mesh Level N0
wifi station_info
192.168.1.33 24:9E:7D:86:56:95 SSID roborock -26
192.168.1.38 B8:82:F2:C5:9D:B9 SSID -50
192.168.1.40 2C:8D:48:4C:EA:B9 SSID Eufy Device -62
wifi_plus station_info
192.168.1.41 DE:48:DB:E8:5F:C4 SSID Mac -50
192.168.1.34 8A:DE:79:12:F0:06 SSID iPhone -49
eth1_device information
eth2_device information
192.168.1.135 90:09:D0:26:02:11
192.168.1.66 02:42:C0:A8:01:42
Mesh Level N1(2GHz)
Agent (B0:14:DF:07:9F:10)
Connected to (8A:33:74:3D:FF:5F)
wifi station_info
wifi_plus station_info
192.168.1.35 C6:86:EC:9E:BB:1A SSID iPhone -48
192.168.1.36 AA:F5:54:F4:42:9E SSID Watch -58
"""
    devices, wifi_clients, radios = parse_ssh_map_info(sample)

    # Wi-Fi devices with hostname
    assert devices["24:9E:7D:86:56:95"].name == "roborock"
    assert devices["8A:DE:79:12:F0:06"].name == "iPhone"
    assert devices["DE:48:DB:E8:5F:C4"].name == "Mac"
    assert devices["2C:8D:48:4C:EA:B9"].name == "Eufy Device"

    # Repeater Wi-Fi devices
    assert devices["C6:86:EC:9E:BB:1A"].name == "iPhone"
    assert devices["AA:F5:54:F4:42:9E"].name == "Watch"

    # Ethernet device resolved via DHCP table
    assert devices["90:09:D0:26:02:11"].name == "SynHome"
    assert devices["90:09:D0:26:02:11"].interface == "ETH"

    # Devices without hostname default to MAC address
    assert devices["B8:82:F2:C5:9D:B9"].name == "B8:82:F2:C5:9D:B9"
    assert devices["02:42:C0:A8:01:42"].name == "02:42:C0:A8:01:42"

    # Radio and client verification
    assert wifi_clients["8A:DE:79:12:F0:06"].rssi == -49
    assert wifi_clients["C6:86:EC:9E:BB:1A"].rssi == -48
    assert "2.4 GHz" in radios
    assert "5 GHz" in radios


def test_web_and_ssh_naming_parity() -> None:
    """Device names and suffixes produced by SSH match Web method identically."""
    ssh_output = """dhcp_table
192.168.1.34 8A:DE:79:12:F0:06 dynamic 40012 WiFi 5 GHz SSID iPhone true
192.168.1.35 C6:86:EC:9E:BB:1A dynamic 40032 WiFi 5 GHz SSID iPhone false
192.168.1.41 DE:48:DB:E8:5F:C4 dynamic 39990 WiFi 5 GHz SSID Mac true
192.168.1.43 CE:FD:DE:2D:81:7E dynamic 39990 WiFi 5 GHz SSID iPhone true
192.168.1.51 2E:47:93:F1:D8:0C dynamic 39990 WiFi 5 GHz SSID Mac true
192.168.1.135 90:09:D0:26:02:11 dynamic 39917 Ethernet SynHome true
Mesh Level N0
wifi_plus station_info
192.168.1.41 DE:48:DB:E8:5F:C4 SSID Mac -50
192.168.1.51 2E:47:93:F1:D8:0C SSID Mac -75
192.168.1.34 8A:DE:79:12:F0:06 SSID iPhone -49
192.168.1.43 CE:FD:DE:2D:81:7E SSID iPhone -49
eth2_device information
192.168.1.135 90:09:D0:26:02:11
Mesh Level N1(2GHz)
Agent (B0:14:DF:07:9F:10)
Connected to (8A:33:74:3D:FF:5F)
wifi_plus station_info
192.168.1.35 C6:86:EC:9E:BB:1A SSID iPhone -48
"""
    ssh_devs, _, _ = parse_ssh_map_info(ssh_output)
    suffixed = update_suffixed(ssh_devs, set())
    names = {mac: display_name(d, suffixed) for mac, d in ssh_devs.items()}

    # Duplicate device names are suffixed identically to Web polling
    assert names["8A:DE:79:12:F0:06"] == "iPhone (F0:06)"
    assert names["C6:86:EC:9E:BB:1A"] == "iPhone (BB:1A)"
    assert names["CE:FD:DE:2D:81:7E"] == "iPhone (81:7E)"
    assert names["DE:48:DB:E8:5F:C4"] == "Mac (5F:C4)"
    assert names["2E:47:93:F1:D8:0C"] == "Mac (D8:0C)"

    # Single unique devices are not suffixed
    assert names["90:09:D0:26:02:11"] == "SynHome"


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
