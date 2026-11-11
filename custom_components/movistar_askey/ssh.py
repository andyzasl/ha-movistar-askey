"""Asynchronous SSH client and parser for compatible Movistar Askey routers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from typing import Final

import asyncssh

from .const import (
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    ROUTER_MODEL,
)
from .router import (
    LINK_REPEATER,
    LINK_ROUTER_5GHZ,
    LINK_ROUTER_24GHZ,
    NODE_REPEATER,
    NODE_ROUTER,
    CannotConnectError,
    Capture,
    InvalidAuthError,
    RouterDevice,
    RouterParseError,
    RouterStatus,
    RouterSummary,
)
from .status import (
    BAND_5GHZ,
    BAND_24GHZ,
    RadioInfo,
    WifiClient,
)

_LOGGER = logging.getLogger(__name__)

MAC_PATTERN: Final = r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"
MAC_RE: Final = re.compile(rf"^{MAC_PATTERN}$")
IP_RE: Final = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Restricted CLI prompt on Askey routers running aspsh / Reduced_CLI_HGU.
PROMPT: Final = re.compile(r"(?:^|\n)[ \t]*>[ \t]*$")

# Only allow-listed read-only commands may be executed over SSH.
# Commands that print credentials (e.g. show wifi) must never be executed.
SSH_COMMAND_MAP_INFO: Final = "show map_info"
SSH_COMMAND_SYS_INFO: Final = "show sys_info"
SSH_ALLOWED_COMMANDS: Final = frozenset({SSH_COMMAND_MAP_INFO, SSH_COMMAND_SYS_INFO})

# Keywords in DHCP or station tables that represent lease types or placeholders,
# not device hostnames.
IGNORED_HOSTNAMES: Final = frozenset(
    {
        "dynamic",
        "static",
        "ignored",
        "unknown",
        "none",
        "null",
        "*",
        "-",
        "--",
    }
)

MAX_RESPONSE: Final = 2 * 1024 * 1024


def _extract_dhcp_hostname(parts: list[str]) -> str | None:
    """
    Extract a device hostname from a DHCP or ARP table line.

    Lines may be formatted as:
      IP MAC dynamic/static EXPIRY WiFi 2.4GHz/5 GHz SSID HOSTNAME true/false
      IP MAC dynamic/static EXPIRY Ethernet HOSTNAME true/false
      IP MAC HOSTNAME EXPIRY true/false
    """
    if len(parts) < 3:
        return None

    # Strip trailing true/false active/bound flag if present
    trailing_flag = parts[-1].lower() in ("true", "false")
    tokens = parts[2:-1] if trailing_flag else parts[2:]
    if not tokens:
        return None

    # Check for Ethernet row: e.g. ["dynamic", "39917", "Ethernet", "SynHome"]
    eth_indices = [i for i, t in enumerate(tokens) if t.lower() == "ethernet"]
    if eth_indices:
        candidate = " ".join(tokens[eth_indices[0] + 1 :]).strip()
        return (
            candidate
            if candidate and candidate.lower() not in IGNORED_HOSTNAMES
            else None
        )

    # Check for Wi-Fi row: e.g. ["dynamic", "40012", "WiFi", "5", "GHz", "SSID", "name"]
    wifi_indices = [i for i, t in enumerate(tokens) if t.lower() in ("wifi", "wi-fi")]
    if wifi_indices:
        idx = wifi_indices[0]
        after_wifi = tokens[idx + 1 :]
        # Skip frequency tokens: "2.4GHz", "5GHz", "6GHz", "5", "2.4", "GHz"
        sub_idx = 0
        while sub_idx < len(after_wifi) and (
            re.match(r"^(?:2\.4|5|6)(?:ghz)?$", after_wifi[sub_idx], re.IGNORECASE)
            or after_wifi[sub_idx].lower() == "ghz"
        ):
            sub_idx += 1
        # Next token is SSID: skip it
        if sub_idx < len(after_wifi):
            sub_idx += 1
        candidate = " ".join(after_wifi[sub_idx:]).strip()
        return (
            candidate
            if candidate and candidate.lower() not in IGNORED_HOSTNAMES
            else None
        )

    # Fallback: filter out lease keywords, numbers, or placeholders
    filtered = [
        t for t in tokens if t.lower() not in IGNORED_HOSTNAMES and not t.isdigit()
    ]
    candidate = " ".join(filtered).strip()
    return (
        candidate if candidate and candidate.lower() not in IGNORED_HOSTNAMES else None
    )


def parse_ssh_map_info(
    text: str,
) -> tuple[dict[str, RouterDevice], dict[str, WifiClient], dict[str, RadioInfo]]:
    """
    Parse the output of ``show map_info`` from the router's restricted CLI.

    Returns a tuple of (devices, wifi_clients, radios).
    """
    devices: dict[str, RouterDevice] = {}
    wifi_clients: dict[str, WifiClient] = {}
    radios: dict[str, RadioInfo] = {}
    dhcp_names: dict[str, str] = {}

    current_node: str | None = None
    current_band: str | None = None
    current_section: str | None = None
    seen_nodes: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        mesh_match = re.search(r"Mesh Level N(\d+)", line, re.IGNORECASE)
        if mesh_match:
            current_node = NODE_ROUTER if mesh_match.group(1) == "0" else NODE_REPEATER
            seen_nodes.add(current_node)
            current_band = None
            current_section = "mesh"
            continue

        if re.search(r"\bdhcp_table\b", line, re.IGNORECASE):
            current_section = "dhcp"
            current_band = None
            continue

        if re.search(r"\barp_table\b", line, re.IGNORECASE):
            current_section = "arp"
            current_band = None
            continue

        if re.search(r"\beth\d*[_ ]device\b", line, re.IGNORECASE):
            current_section = "eth"
            current_band = None
            continue

        if re.search(r"\bwifi(?:_plus)? station_info\b", line, re.IGNORECASE):
            current_band = BAND_5GHZ if "wifi_plus" in line.lower() else BAND_24GHZ
            radios[current_band] = RadioInfo(
                band=current_band, enabled=True, channel=None, bandwidth_mhz=None
            )
            current_section = "wifi"
            continue

        parts = line.split()
        if len(parts) >= 2 and IP_RE.fullmatch(parts[0]) and MAC_RE.fullmatch(parts[1]):
            ip = parts[0]
            mac = parts[1].upper().replace("-", ":")

            if current_section in ("dhcp", "arp"):
                hostname = _extract_dhcp_hostname(parts)
                if hostname:
                    dhcp_names[mac] = hostname
            elif (
                current_section == "wifi"
                and current_node is not None
                and current_band is not None
                and len(parts) >= 3
            ):
                rssi: int | None = None
                try:
                    val = int(parts[-1])
                    if -127 <= val <= 0:
                        rssi = val
                except ValueError:
                    rssi = None

                link = (
                    LINK_REPEATER
                    if current_node == NODE_REPEATER
                    else (
                        LINK_ROUTER_5GHZ
                        if current_band == BAND_5GHZ
                        else LINK_ROUTER_24GHZ
                    )
                )

                # Format: IP MAC SSID [hostname...] RSSI
                # middle contains tokens between MAC and RSSI (or after MAC if no RSSI)
                middle = parts[2:-1] if rssi is not None else parts[2:]
                hostname: str | None = None
                if len(middle) >= 2:
                    # middle[0] is the SSID; remaining tokens are the device hostname
                    candidate = " ".join(middle[1:]).strip()
                    if candidate and candidate.lower() not in IGNORED_HOSTNAMES:
                        hostname = candidate

                name = hostname or dhcp_names.get(mac, mac)
                devices[mac] = RouterDevice(
                    mac=mac,
                    ip=ip,
                    name=name,
                    interface="WIFI",
                    link=link,
                )
                wifi_clients[mac] = WifiClient(
                    mac=mac,
                    band=current_band,
                    ap_id=1 if current_band == BAND_5GHZ else 0,
                    rssi=rssi,
                    link_rate="",
                    standard="",
                    associated_seconds=None,
                )
            elif current_section == "eth":
                # eth row format: IP MAC [hostname...] [status/rate]
                has_trailing_metric = len(parts) >= 4 and (
                    parts[-1].startswith("-")
                    or parts[-1].isdigit()
                    or parts[-1].endswith("M")
                )
                middle = parts[2:-1] if has_trailing_metric else parts[2:]
                candidate = " ".join(middle).strip() if middle else ""
                hostname = (
                    candidate
                    if candidate and candidate.lower() not in IGNORED_HOSTNAMES
                    else None
                )
                name = hostname or dhcp_names.get(mac, mac)
                devices[mac] = RouterDevice(
                    mac=mac,
                    ip=ip,
                    name=name,
                    interface="ETH",
                    link=None,
                )

    if not seen_nodes and not devices:
        raise RouterParseError("Unrecognized or empty SSH map_info output")

    # Update hostnames for any devices that only resolved to fallback MAC name
    for mac, name in dhcp_names.items():
        if mac in devices and devices[mac].name == mac:
            dev = devices[mac]
            devices[mac] = RouterDevice(
                mac=mac,
                ip=dev.ip,
                name=name,
                interface=dev.interface,
                link=dev.link,
            )

    return devices, wifi_clients, radios


def parse_ssh_sys_info(text: str) -> RouterSummary:
    """
    Parse the output of ``show sys_info`` from the router's restricted CLI.

    Extracts uptime in seconds and system metrics.
    """
    uptime_match = re.search(
        r"^\s*(?:sys)?uptime\s*[:=]?\s*(\d+)\s*(?:s|seconds)?\s*$",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    uptime_seconds = int(uptime_match.group(1)) if uptime_match else None

    cpu_match = re.search(
        r"(?:load(?:15min|1min|5min)?|cpu(?:_usage)?)\s*[:=]?\s*([\d.]+)",
        text,
        re.IGNORECASE,
    )
    cpu_usage: int | None = None
    if cpu_match:
        with contextlib.suppress(ValueError):
            val = float(cpu_match.group(1))
            cpu_usage = round(val) if val <= 100 else 100

    free_mem_match = re.search(r"\bfreeMem\s*[:=]?\s*(\d+)", text, re.IGNORECASE)
    commit_limit_match = re.search(
        r"\bcommitLimit\s*[:=]?\s*(\d+)", text, re.IGNORECASE
    )
    total_mem_match = re.search(
        r"\b(?:totalMem|memTotal|total_memory)\s*[:=]?\s*(\d+)",
        text,
        re.IGNORECASE,
    )

    memory_usage: int | None = None
    if free_mem_match:
        free_mem = int(free_mem_match.group(1))
        total_mem = (
            int(total_mem_match.group(1))
            if total_mem_match
            else (int(commit_limit_match.group(1)) * 2 if commit_limit_match else None)
        )
        if total_mem and total_mem > free_mem:
            memory_usage = max(
                0, min(100, round(((total_mem - free_mem) / total_mem) * 100))
            )
    else:
        mem_pct_match = re.search(
            r"\b(?:mem(?:ory)?(?:_usage)?|memusage)\s*[:=]?\s*(\d{1,3})(?:\s*%)?\b",
            text,
            re.IGNORECASE,
        )
        if mem_pct_match:
            with contextlib.suppress(ValueError):
                val = int(mem_pct_match.group(1))
                if 0 <= val <= 100:
                    memory_usage = val

    return RouterSummary(
        uptime_seconds=uptime_seconds,
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        firmware="",
        hardware="",
        model=ROUTER_MODEL,
    )


class MovistarAskeySSHClient:
    """Fetch router network map and status via interactive SSH console."""

    def __init__(
        self,
        host: str,
        password: str,
        username: str = DEFAULT_SSH_USERNAME,
        port: int = DEFAULT_SSH_PORT,
        key_file: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        """Initialize an SSH console client."""
        self._host = host.strip()
        self._password = password
        self._username = username.strip()
        self._port = port
        self._key_file = key_file
        self._timeout = timeout

        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None

        self._cached_wifi_clients: dict[str, WifiClient] = {}
        self._cached_radios: dict[str, RadioInfo] = {}

        self.captures: dict[str, Capture] = {}
        self.stats: dict[str, int] = {
            "logins": 0,
            "session_reuses": 0,
            "session_expirations": 0,
        }

    async def async_get_devices(self) -> dict[str, RouterDevice]:
        """Fetch and return all connected network clients over SSH."""
        text = await self.async_run_command(SSH_COMMAND_MAP_INFO)
        self.captures[f"ssh:{SSH_COMMAND_MAP_INFO}"] = Capture(
            status=0,
            body=text,
        )
        devices, wifi_clients, radios = parse_ssh_map_info(text)
        self._cached_wifi_clients = wifi_clients
        self._cached_radios = radios
        return devices

    async def async_get_status(self) -> RouterStatus:
        """Return Wi-Fi clients, radios, and router summary from SSH."""
        text = await self.async_run_command(SSH_COMMAND_SYS_INFO)
        self.captures[f"ssh:{SSH_COMMAND_SYS_INFO}"] = Capture(
            status=0,
            body=text,
        )
        summary = parse_ssh_sys_info(text)
        return RouterStatus(
            wifi_clients=dict(self._cached_wifi_clients),
            radios=dict(self._cached_radios),
            summary=summary,
        )

    async def async_run_command(self, command: str) -> str:
        """Execute an allow-listed command in the interactive PTY session."""
        if command not in SSH_ALLOWED_COMMANDS:
            raise ValueError(f"SSH command {command!r} is not allowed")

        if self._conn is None or self._process is None or self._conn.is_closed():
            await self._async_connect()
        else:
            self.stats["session_reuses"] += 1

        try:
            return await self._async_send_command(command)
        except (
            asyncssh.Error,
            OSError,
            TimeoutError,
            ConnectionError,
        ) as err:
            _LOGGER.debug(
                "SSH session error (%s), reconnecting: %s",
                type(err).__name__,
                err,
            )
            self.stats["session_expirations"] += 1
            await self._async_connect()
            return await self._async_send_command(command)

    async def _async_send_command(self, command: str) -> str:
        """Send command to process stdin and read output until prompt."""
        if self._process is None or self._process.stdin is None:
            raise CannotConnectError("SSH process is not active")

        self._process.stdin.write(command + "\n")
        await self._process.stdin.drain()

        output = await self._async_read_prompt()
        lines = output.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() == command:
            lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
        return "\n".join(lines)

    async def _async_connect(self) -> None:
        """Establish an interactive SSH session with PTY allocation."""
        await self.async_close()
        client_keys = [self._key_file] if self._key_file else None

        try:
            conn = await asyncio.wait_for(
                asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._username,
                    password=self._password or None,
                    client_keys=client_keys,
                    known_hosts=None,
                ),
                timeout=self._timeout,
            )
            self._conn = conn
            process = await asyncio.wait_for(
                conn.create_process(
                    term_type="vt100",
                    term_size=(250, 1000),
                    encoding="latin-1",
                ),
                timeout=self._timeout,
            )
            self._process = process
            await self._async_read_prompt()
            self.stats["logins"] += 1
        except asyncssh.PermissionDenied as err:
            await self.async_close()
            raise InvalidAuthError("The router rejected the SSH credentials") from err
        except (
            asyncssh.Error,
            OSError,
            TimeoutError,
        ) as err:
            await self.async_close()
            raise CannotConnectError(f"Could not establish SSH session: {err}") from err

    async def _async_read_prompt(self) -> str:
        """Read data from process stdout until the router prompt is encountered."""
        if self._process is None or self._process.stdout is None:
            raise CannotConnectError("SSH process stdout is unavailable")

        buf = ""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("SSH prompt timeout")

            chunk = await asyncio.wait_for(
                self._process.stdout.read(65536),
                timeout=remaining,
            )
            if not chunk:
                raise ConnectionError("SSH channel closed unexpectedly")

            buf += chunk.replace("\r", "")
            if len(buf) > MAX_RESPONSE:
                raise RouterParseError("SSH response exceeds size limit")

            if PROMPT.search(buf):
                return PROMPT.sub("", buf)

    async def async_test_credentials(self) -> None:
        """Test whether credentials and command execution succeed."""
        await self.async_get_devices()

    async def async_close(self) -> None:
        """Close the active SSH process and connection cleanly."""
        process = self._process
        conn = self._conn
        self._process = None
        self._conn = None

        if process is not None:
            with contextlib.suppress(Exception):
                process.close()
                if hasattr(process, "wait_closed"):
                    await asyncio.wait_for(process.wait_closed(), timeout=2.0)

        if conn is not None:
            try:
                conn.close()
                if hasattr(conn, "wait_closed"):
                    await asyncio.wait_for(conn.wait_closed(), timeout=2.0)
            except TimeoutError:
                if hasattr(conn, "abort"):
                    with contextlib.suppress(Exception):
                        conn.abort()
            except Exception:
                pass
