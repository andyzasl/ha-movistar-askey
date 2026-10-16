"""Parsers for the router's XML status endpoints."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

BAND_24GHZ = "2.4 GHz"
BAND_5GHZ = "5 GHz"

# dpm_cfg_wifi_id / dpm_cfg_wifi_0i used by the router for each radio.
RADIO_BANDS: dict[int, str] = {0: BAND_24GHZ, 1: BAND_5GHZ}

# opr_bandwidth codes. 1 (2.4 GHz, 20 MHz) and 3 (5 GHz, 80 MHz) were
# confirmed on an RTF8316VW; 2 and 4 follow the same sequence.
_BANDWIDTH_MHZ: dict[str, int] = {"1": 20, "2": 40, "3": 80, "4": 160}

# Access points 0 (2.4 GHz) and 1 (5 GHz) carry the main SSID on an RTF8316VW.
_MAIN_ACCESS_POINT_IDS = frozenset({0, 1})


@dataclass(frozen=True, slots=True)
class WifiClient:
    """A Wi-Fi station associated with one of the router's access points."""

    mac: str
    band: str
    ap_id: int | None
    rssi: int | None
    link_rate: str
    standard: str
    associated_seconds: int | None

    @property
    def access_point(self) -> str:
        """Return a readable name for the router access point."""
        if self.ap_id is None or self.ap_id in _MAIN_ACCESS_POINT_IDS:
            return f"Router {self.band}"
        return f"Router {self.band} (AP {self.ap_id})"


@dataclass(frozen=True, slots=True)
class RadioInfo:
    """Operational state of one router radio."""

    band: str
    enabled: bool
    channel: int | None
    bandwidth_mhz: int | None


@dataclass(frozen=True, slots=True)
class RouterSummary:
    """System summary reported by the router."""

    uptime_seconds: int | None
    cpu_usage: int | None
    memory_usage: int | None
    firmware: str
    hardware: str
    model: str


def _root(xml_text: str) -> ET.Element | None:
    """Return the XML root when the router reports success, otherwise None."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    if (root.findtext(".//Result") or "").strip() != "0":
        return None
    return root


def _int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None


def parse_associations(xml_text: str, band: str) -> dict[str, WifiClient]:
    """Parse cbListWifiAccPtAssociation.xml into stations keyed by MAC address."""
    root = _root(xml_text)
    if root is None:
        return {}

    clients: dict[str, WifiClient] = {}
    for group in root.iter("wifi_association_group"):
        ap_id = _int(group.findtext("dpm_cfg_wifi_acc_pt_id"))
        for station in group.iter("rtm_cfg_wifi_association"):
            mac = (station.findtext("mac_addr") or "").strip().upper()
            if not mac or station.findtext("is_wds_peer") == "1":
                continue
            clients[mac] = WifiClient(
                mac=mac,
                band=band,
                ap_id=ap_id,
                rssi=_int(station.findtext("rssi")),
                link_rate=(station.findtext("link_rate") or "").strip(),
                standard=(station.findtext("standard") or "").strip(),
                associated_seconds=_int(station.findtext("associated_time")),
            )
    return clients


def parse_radio(xml_text: str, band: str) -> RadioInfo | None:
    """Parse cbGetWifi.xml for one radio."""
    root = _root(xml_text)
    if root is None:
        return None
    return RadioInfo(
        band=band,
        enabled=root.findtext(".//radio_opr_status") == "1",
        channel=_int(root.findtext(".//opr_channel")),
        bandwidth_mhz=_BANDWIDTH_MHZ.get(
            (root.findtext(".//opr_bandwidth") or "").strip()
        ),
    )


def parse_summary(xml_text: str) -> RouterSummary | None:
    """Parse cbGetSummary.xml."""
    root = _root(xml_text)
    if root is None:
        return None
    return RouterSummary(
        uptime_seconds=_int(root.findtext(".//SysUptime")),
        cpu_usage=_int(root.findtext(".//CpuUsage")),
        memory_usage=_int(root.findtext(".//MemUsage")),
        firmware=(root.findtext(".//SWVersion") or "").strip(),
        hardware=(root.findtext(".//HWVersion") or "").strip(),
        model=(root.findtext(".//ModelName") or "").strip(),
    )
