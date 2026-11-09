"""
Reduce raw router responses to structure-only diagnostics.

Diagnostics must help support new router models and firmware (endpoint
availability, field names, nesting, enum values) without exporting personal
data. Identifiers such as MAC and IP addresses, SSIDs, host names and serial
numbers are never included; other free-text values are reduced to a shape in
which digits become ``9`` and letters become ``a``.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

from .router import Capture, RouterDevice, is_private_mac
from .status import WifiClient

_MAX_DISTINCT = 20

# Tag names whose values are exported as-is: firmware identity and enums.
_SAFE_TAGS = frozenset(
    {
        "Result",
        "HWVersion",
        "SWVersion",
        "SWVersionS",
        "SWCountry",
        "ModelName",
        "DeviceModel",
        "DeviceManufacturer",
        "ProfileName",
        "BootloaderVersion",
        "PrivateVersion",
        "RevisionNumber",
        "Customization",
        "ConfigInfo",
        "country_code",
        "standard",
    }
)

# Substrings marking identifying fields; their values are never exported.
_SENSITIVE = ("mac", "ssid", "ip", "addr", "host", "serial", "key", "pass", "psk")

_SHORT_NUMBER = re.compile(r"^-?\d{1,6}(\.\d+)?$")
_DEVICE_DATA = re.compile(r"var\s+deviceData\s*=\s*([\w\W]+?);")
_LOGIN_MARKERS = ("loginpassword", "te_acceso_router")

# deviceData column meanings, as far as known.
_DEVICE_COLUMNS = {
    0: "active",
    1: "hostname",
    2: "device_type",
    3: "ipv4",
    4: "interface",
    5: "open_port",
    6: "mac",
    7: "link",
    8: "address_source",
    9: "ipv6",
}
_ENUM_COLUMNS = frozenset({0, 2, 4, 5, 7, 8})


def value_shape(value: str) -> str:
    """Return the shape of a value: digits become 9, letters become a."""
    shape = re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", value))
    return shape[:40]


def _is_sensitive(tag: str) -> bool:
    lowered = tag.lower()
    return tag not in _SAFE_TAGS and any(part in lowered for part in _SENSITIVE)


def _describe_values(tag: str, values: list[str]) -> dict[str, Any]:
    info: dict[str, Any] = {"count": len(values)}
    if _is_sensitive(tag):
        info["values"] = "redacted"
    elif tag in _SAFE_TAGS or all(_SHORT_NUMBER.match(v) for v in values if v):
        info["values"] = sorted(set(values))[:_MAX_DISTINCT]
    else:
        info["shapes"] = sorted({value_shape(v) for v in values})[:_MAX_DISTINCT]
    return info


def _looks_like_login(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _LOGIN_MARKERS)


def summarize_xml(body: str) -> dict[str, Any]:
    """Describe an XML response by its structure, enums and value shapes."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return {
            "xml": False,
            "length": len(body),
            "looks_like_login_page": _looks_like_login(body),
        }

    paths: Counter[str] = Counter()
    values: dict[str, list[str]] = {}

    def walk(element: ET.Element, path: str) -> None:
        children = list(element)
        if not children:
            values.setdefault(element.tag, []).append((element.text or "").strip())
            return
        for child in children:
            child_path = f"{path}/{child.tag}"
            paths[child_path] += 1
            walk(child, child_path)

    walk(root, root.tag)
    return {
        "xml": True,
        "root": root.tag,
        "result": (root.findtext(".//Result") or "").strip() or None,
        "paths": dict(sorted(paths.items())),
        "fields": {
            tag: _describe_values(tag, tag_values)
            for tag, tag_values in sorted(values.items())
        },
    }


def summarize_device_map(page: str) -> dict[str, Any]:
    """Describe the deviceData array by row length and per-column values."""
    match = _DEVICE_DATA.search(page)
    if match is None:
        return {
            "device_data_found": False,
            "length": len(page),
            "looks_like_login_page": _looks_like_login(page),
        }
    try:
        rows = ast.literal_eval(match.group(1).replace("\\", ""))
    except SyntaxError, ValueError:
        return {"device_data_found": True, "parse_error": True}

    columns: dict[str, Any] = {}
    width = max((len(row) for row in rows), default=0)
    for index in range(width):
        cells = [str(row[index]).strip() for row in rows if len(row) > index]
        name = f"{index}:{_DEVICE_COLUMNS.get(index, 'unknown')}"
        if index in _ENUM_COLUMNS:
            columns[name] = dict(Counter(cells))
        elif index == 3:
            columns[name] = dict(
                Counter(
                    "empty" if not c else c if c == "0.0.0.0" else "ipv4" for c in cells
                )
            )
        elif index == 6:
            columns[name] = dict(
                Counter(
                    "private_mac"
                    if is_private_mac(c)
                    else "mac"
                    if re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", c)
                    else "invalid"
                    for c in cells
                )
            )
        else:
            columns[name] = {
                "empty": sum(not c for c in cells),
                "non_empty": sum(bool(c) for c in cells),
            }
    return {
        "device_data_found": True,
        "rows": len(rows),
        "row_lengths": dict(Counter(len(row) for row in rows)),
        "columns": columns,
    }


def summarize_capture(name: str, capture: Capture) -> dict[str, Any]:
    """Describe one captured endpoint response."""
    info: dict[str, Any] = {"http_status": capture.status}
    if capture.error:
        info["error"] = capture.error
        return info
    if capture.cookie_names:
        info["cookie_names"] = list(capture.cookie_names)
    if name.endswith((".asp", ".cgi")):
        info["page"] = summarize_device_map(capture.body)
    else:
        info["response"] = summarize_xml(capture.body)
    return info


def link_crosstab(
    devices: dict[str, RouterDevice],
    present: frozenset[str],
    wifi_clients: dict[str, WifiClient],
) -> dict[str, dict[str, int]]:
    """
    Cross-tabulate the device-map link field with the observed attachment.

    For each link value, count clients by router association band, or by
    interface when the router does not list them. This verifies the link
    field's meaning on other models and firmware.
    """
    table: dict[str, Counter[str]] = {}
    for mac in present:
        if (device := devices.get(mac)) is None:
            continue
        client = wifi_clients.get(mac)
        observed = (
            f"router {client.band}"
            if client
            else f"{device.interface or 'unknown'} not associated with router"
        )
        table.setdefault(str(device.link), Counter())[observed] += 1
    return {link: dict(counts) for link, counts in sorted(table.items())}
