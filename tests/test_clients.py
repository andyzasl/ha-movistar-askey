"""Tests for client naming, description, node and roam detection."""

from custom_components.movistar_rft8115vw.clients import (
    Attachment,
    access_point_name,
    client_model,
    detect_roams,
    display_name,
    update_suffixed,
)
from custom_components.movistar_rft8115vw.router import (
    RouterDevice,
    is_private_mac,
    parse_device_data,
)

PAGE = """
var deviceData=[
  ['1','Mac','0','192.168.1.41','WIFI','no','DE:48:DB:E8:5F:C4','1','DHCP',''],
  ['1','SynHome','4','192.168.1.135','ETH','no','90:09:D0:00:00:01','1','DHCP',''],
  ['1','iPhone','0','192.168.1.50','WIFI','no','CE:FD:DE:2D:81:7E','7','DHCP',''],
  ['1','iPhone','0','192.168.1.34','WIFI','no','C6:86:EC:9E:BB:1A','7','DHCP',''],
  ['1','wiz','0','192.168.1.55','WIFI','no','D8:A0:11:BF:0A:B5','0','DHCP',''],
  ['0','Watch','0','192.168.1.48','NONE','no','AA:01:C9:00:00:01','-1','DHCP','']
];
"""


def test_node_from_device_map_link() -> None:
    """Index 7 maps to router or repeater for Wi-Fi clients only."""
    devices = parse_device_data(PAGE)

    assert devices["DE:48:DB:E8:5F:C4"].node == "router"
    assert devices["D8:A0:11:BF:0A:B5"].node == "router"
    assert devices["CE:FD:DE:2D:81:7E"].node == "repeater"
    assert devices["90:09:D0:00:00:01"].node is None


def test_private_mac() -> None:
    """The locally administered bit marks randomized addresses."""
    assert is_private_mac("CE:FD:DE:2D:81:7E")
    assert is_private_mac("2E:47:93:F1:D8:0C")
    assert not is_private_mac("D8:A0:11:BF:0A:B5")


def test_duplicate_names_get_stable_mac_suffix() -> None:
    """Duplicated names get a suffix that persists after the duplicate leaves."""
    devices = parse_device_data(PAGE)
    suffixed = update_suffixed(devices, set())

    assert display_name(devices["CE:FD:DE:2D:81:7E"], suffixed) == "iPhone (81:7E)"
    assert display_name(devices["C6:86:EC:9E:BB:1A"], suffixed) == "iPhone (BB:1A)"
    assert display_name(devices["DE:48:DB:E8:5F:C4"], suffixed) == "Mac"

    remaining = {"CE:FD:DE:2D:81:7E": devices["CE:FD:DE:2D:81:7E"]}
    suffixed = update_suffixed(remaining, suffixed)
    assert display_name(devices["CE:FD:DE:2D:81:7E"], suffixed) == "iPhone (81:7E)"


def test_client_model() -> None:
    """The model line shows connection, band and private address."""
    devices = parse_device_data(PAGE)

    assert (
        client_model(devices["CE:FD:DE:2D:81:7E"])
        == "Repeater · Wi-Fi · private address"
    )
    assert (
        client_model(devices["D8:A0:11:BF:0A:B5"], "2.4 GHz")
        == "Router · Wi-Fi 2.4 GHz"
    )
    assert client_model(devices["90:09:D0:00:00:01"]) == "Ethernet"


def test_repeater_access_point_name() -> None:
    """Repeater clients without router association are named Repeater."""
    device = RouterDevice(
        mac="CE:FD:DE:2D:81:7E", ip="", name="iPhone", interface="WIFI", link=7
    )
    assert access_point_name(device, None) == "Repeater"


def test_detect_roams() -> None:
    """Node and band changes are roams; absences and unknowns are not."""
    previous = {
        "A": Attachment("router", "5 GHz"),
        "B": Attachment("router", "5 GHz"),
        "C": Attachment("router", "2.4 GHz"),
        "D": Attachment(None, None),
    }
    current = {
        "A": Attachment("repeater", None),
        "B": Attachment("router", "5 GHz"),
        "C": Attachment("router", "5 GHz"),
        "D": Attachment("router", "5 GHz"),
        "E": Attachment("router", "5 GHz"),
    }

    roams = {mac for mac, _, _ in detect_roams(previous, current)}

    assert roams == {"A", "C"}
