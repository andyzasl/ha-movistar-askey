"""Tests for structure-only diagnostics."""

import json

from custom_components.movistar_rft8115vw.diag import (
    link_crosstab,
    summarize_capture,
    summarize_device_map,
    summarize_xml,
    value_shape,
)
from custom_components.movistar_rft8115vw.router import Capture, parse_device_data
from custom_components.movistar_rft8115vw.status import BAND_5GHZ, parse_associations

SECRETS = (
    "AA:BB:CC:DD:EE:01",
    "aa:bb:cc:dd:ee:01",
    "192.168.1.51",
    "HomeNetwork",
    "Kitchen-Laptop",
    "ABCD12345678",
)

ASSOCIATIONS = """<Response><cbListWifiAccPtAssociation>
<wifi_association_group><dpm_cfg_wifi_acc_pt_id>1</dpm_cfg_wifi_acc_pt_id>
<ssid>HomeNetwork</ssid>
<rtm_cfg_wifi_association><mac_addr>aa:bb:cc:dd:ee:01</mac_addr>
<is_wds_peer>0</is_wds_peer><standard>A, N, AC, AX</standard>
<link_rate>1201/1201 Mbps</link_rate><rssi>-49</rssi>
<ipv4_addr>192.168.1.51</ipv4_addr></rtm_cfg_wifi_association>
</wifi_association_group><Result>0</Result></cbListWifiAccPtAssociation></Response>"""

SUMMARY = """<Response><cbGetSummary><ModelName>RTF8316VW</ModelName>
<SWVersion>GL_g1.18_R8316_V2.19</SWVersion><OnuSerialNumber>ABCD12345678</OnuSerialNumber>
<SysUptime>10023</SysUptime><Result>0</Result></cbGetSummary></Response>"""

PAGE = """var deviceData=[
  ['1','Kitchen-Laptop','0','192.168.1.51','WIFI','no','AA:BB:CC:DD:EE:01','1','DHCP',''],
  ['0','','0','0.0.0.0','NONE','no','CE:FD:DE:2D:81:7E','-1','DHCP','']
];"""


def test_value_shape() -> None:
    """Digits and letters are replaced; punctuation is kept."""
    assert value_shape("1201/1201 Mbps") == "9999/9999 aaaa"


def test_xml_summary_keeps_structure_and_firmware_but_no_identifiers() -> None:
    """Field names, enums and firmware stay; identifiers are removed."""
    associations = summarize_xml(ASSOCIATIONS)
    summary = summarize_xml(SUMMARY)

    assert associations["result"] == "0"
    assert associations["fields"]["rssi"]["values"] == ["-49"]
    assert associations["fields"]["standard"]["values"] == ["A, N, AC, AX"]
    assert associations["fields"]["link_rate"]["shapes"] == ["9999/9999 aaaa"]
    assert associations["fields"]["mac_addr"]["values"] == "redacted"
    assert summary["fields"]["SWVersion"]["values"] == ["GL_g1.18_R8316_V2.19"]
    assert summary["fields"]["OnuSerialNumber"]["values"] == "redacted"
    dumped = json.dumps([associations, summary])
    assert not any(secret in dumped for secret in SECRETS)


def test_device_map_summary_has_columns_but_no_identifiers() -> None:
    """The device map is described per column without names or addresses."""
    summary = summarize_device_map(PAGE)

    assert summary["rows"] == 2
    assert summary["columns"]["7:link"] == {"1": 1, "-1": 1}
    assert summary["columns"]["6:mac"] == {"private_mac": 2}
    assert summary["columns"]["1:hostname"] == {"empty": 1, "non_empty": 1}
    assert not any(secret in json.dumps(summary) for secret in SECRETS)


def test_login_page_and_errors_are_reported() -> None:
    """A login page or transport error is visible without its content."""
    login = summarize_capture(
        "te_mapa_red_local.asp", Capture(status=200, body="<form>loginPassword</form>")
    )
    error = summarize_capture("cbGetWifi.xml", Capture(error="TimeoutError"))

    assert login["page"] == {
        "device_data_found": False,
        "length": 26,
        "looks_like_login_page": True,
    }
    assert error == {"http_status": None, "error": "TimeoutError"}


def test_link_crosstab() -> None:
    """Link values are matched with the observed router association."""
    devices = parse_device_data(PAGE)
    clients = parse_associations(ASSOCIATIONS, BAND_5GHZ)

    table = link_crosstab(devices, frozenset(devices), clients)

    assert table == {"1": {"router 5 GHz": 1}}
