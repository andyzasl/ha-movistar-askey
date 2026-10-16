"""Tests for the router's XML status parsers."""

from custom_components.movistar_rft8115vw.status import (
    BAND_5GHZ,
    parse_associations,
    parse_radio,
    parse_summary,
)

ASSOCIATIONS = """<?xml version="1.0" encoding="UTF-8"?>
<Response><cbListWifiAccPtAssociation>
  <wifi_association_group>
    <dpm_cfg_wifi_acc_pt_0i>1</dpm_cfg_wifi_acc_pt_0i>
    <dpm_cfg_wifi_acc_pt_id>1</dpm_cfg_wifi_acc_pt_id>
    <ssid>Home</ssid>
    <rtm_cfg_wifi_association>
      <rtm_cfg_wifi_association_0i>0</rtm_cfg_wifi_association_0i>
      <mac_addr>aa:bb:cc:dd:ee:01</mac_addr>
      <is_auth>1</is_auth>
      <is_wds_peer>0</is_wds_peer>
      <standard>A, N, AC, AX</standard>
      <link_rate>1201/1201 Mbps</link_rate>
      <opr_rate>328.664/8031.672 Mbps</opr_rate>
      <associated_time>2239</associated_time>
      <rssi>-49</rssi>
      <ipv4_addr>192.168.1.51</ipv4_addr>
    </rtm_cfg_wifi_association>
  </wifi_association_group>
  <wifi_association_group>
    <dpm_cfg_wifi_acc_pt_0i>7</dpm_cfg_wifi_acc_pt_0i>
    <dpm_cfg_wifi_acc_pt_id>7</dpm_cfg_wifi_acc_pt_id>
    <ssid>Backhaul</ssid>
    <rtm_cfg_wifi_association>
      <mac_addr>aa:bb:cc:dd:ee:02</mac_addr>
      <is_wds_peer>1</is_wds_peer>
      <rssi>-68</rssi>
    </rtm_cfg_wifi_association>
  </wifi_association_group>
  <Result>0</Result>
</cbListWifiAccPtAssociation></Response>
"""

RADIO = """<Response><cbGetWifi><dpm_cfg_wifi>
  <dpm_cfg_wifi_0i>1</dpm_cfg_wifi_0i>
  <radio_opr_status>1</radio_opr_status>
  <opr_channel>36</opr_channel>
  <opr_bandwidth>3</opr_bandwidth>
  <Result>0</Result>
</dpm_cfg_wifi></cbGetWifi></Response>"""

SUMMARY = """<Response><cbGetSummary>
  <HWVersion>REV4</HWVersion>
  <SWVersion>GL_g1.18_R8316_V2.19</SWVersion>
  <SysUptime>10023</SysUptime>
  <MemUsage>45</MemUsage>
  <CpuUsage>16</CpuUsage>
  <ModelName>RTF8316VW</ModelName>
  <Result>0</Result>
</cbGetSummary></Response>"""


def test_parse_associations() -> None:
    """Stations are keyed by upper-case MAC; WDS peers are skipped."""
    clients = parse_associations(ASSOCIATIONS, BAND_5GHZ)

    assert list(clients) == ["AA:BB:CC:DD:EE:01"]
    client = clients["AA:BB:CC:DD:EE:01"]
    assert client.band == BAND_5GHZ
    assert client.ap_id == 1
    assert client.rssi == -49
    assert client.link_rate == "1201/1201 Mbps"
    assert client.standard == "A, N, AC, AX"
    assert client.associated_seconds == 2239


def test_parse_radio() -> None:
    """Operational channel and bandwidth are decoded."""
    radio = parse_radio(RADIO, BAND_5GHZ)

    assert radio is not None
    assert radio.enabled
    assert radio.channel == 36
    assert radio.bandwidth_mhz == 80


def test_parse_summary() -> None:
    """System summary fields are decoded."""
    summary = parse_summary(SUMMARY)

    assert summary is not None
    assert summary.uptime_seconds == 10023
    assert summary.cpu_usage == 16
    assert summary.memory_usage == 45
    assert summary.firmware == "GL_g1.18_R8316_V2.19"
    assert summary.hardware == "REV4"


def test_access_point_names() -> None:
    """Main access points get a short name; others include their id."""
    clients = parse_associations(ASSOCIATIONS, BAND_5GHZ)

    assert clients["AA:BB:CC:DD:EE:01"].access_point == "Router 5 GHz"
    other = parse_associations(
        ASSOCIATIONS.replace(
            ">1</dpm_cfg_wifi_acc_pt_id>", ">3</dpm_cfg_wifi_acc_pt_id>"
        ),
        BAND_5GHZ,
    )
    assert other["AA:BB:CC:DD:EE:01"].access_point == "Router 5 GHz (AP 3)"


def test_failed_result_and_login_page_yield_no_data() -> None:
    """A non-zero Result or a non-XML login page is treated as no data."""
    assert parse_summary("<cbGetSummary><Result>4</Result></cbGetSummary>") is None
    assert parse_radio("<html>loginPassword</html>", BAND_5GHZ) is None
    assert parse_associations("<html>loginPassword", BAND_5GHZ) == {}
