"""Client naming, description and roam detection helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .router import NODE_REPEATER, RouterDevice
from .status import WifiClient

_CONNECTION_NAMES = {"WIFI": "Wi-Fi", "ETH": "Ethernet"}


@dataclass(frozen=True, slots=True)
class Attachment:
    """Where a client is attached: mesh node and, when known, band."""

    node: str | None
    band: str | None


def mac_suffix(mac: str) -> str:
    """Return the last two octets of a MAC address."""
    return mac[-5:]


def update_suffixed(devices: dict[str, RouterDevice], suffixed: set[str]) -> set[str]:
    """
    Return the MACs whose names need a MAC suffix to be unique.

    Once a device gets a suffix it keeps it, so names stay stable when a
    duplicate device leaves the network.
    """
    counts = Counter(device.name for device in devices.values())
    return suffixed | {
        mac
        for mac, device in devices.items()
        if counts[device.name] > 1 and device.name != mac
    }


def display_name(device: RouterDevice, suffixed: set[str]) -> str:
    """Return the name to show for a client."""
    if device.mac in suffixed:
        return f"{device.name} ({mac_suffix(device.mac)})"
    return device.name


def client_model(device: RouterDevice, band: str | None = None) -> str | None:
    """Return a short description for the device card's model line."""
    connection = _CONNECTION_NAMES.get(device.interface)
    if connection == "Wi-Fi" and band:
        connection = f"Wi-Fi {band}"
    parts = [
        part
        for part in (
            connection,
            "private address" if device.is_private_mac else None,
        )
        if part
    ]
    return " · ".join(parts) or None


def attachment(device: RouterDevice, wifi_client: WifiClient | None) -> Attachment:
    """Return the node and band of a client from the device map and associations."""
    band = wifi_client.band if wifi_client else None
    return Attachment(node=device.node, band=band)


def access_point_name(
    device: RouterDevice, wifi_client: WifiClient | None
) -> str | None:
    """Return a readable access point name for a client."""
    if wifi_client is not None:
        return wifi_client.access_point
    if device.node == NODE_REPEATER:
        return "Repeater"
    return None


def detect_roams(
    previous: dict[str, Attachment],
    current: dict[str, Attachment],
) -> list[tuple[str, Attachment, Attachment]]:
    """
    Return clients whose node or band changed between two successful polls.

    Only clients present in both polls with a known node in both are
    considered, so reconnections after an absence are not reported as roams.
    A band change is only reported when the band is known in both polls.
    """
    roams: list[tuple[str, Attachment, Attachment]] = []
    for mac, now in current.items():
        before = previous.get(mac)
        if before is None or before.node is None or now.node is None:
            continue
        band_changed = (
            before.band is not None and now.band is not None and before.band != now.band
        )
        if before.node != now.node or band_changed:
            roams.append((mac, before, now))
    return roams
