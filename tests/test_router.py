"""Tests for the standalone Movistar Askey router parser."""

import pytest

from custom_components.movistar_rft8115vw.router import (
    RouterParseError,
    _authentication_failed,
    encode_router_value,
    parse_device_data,
)


def test_encode_router_value_is_reversible() -> None:
    """Applying the router's XOR transform twice restores the input."""
    password = "correct horse battery staple"
    assert encode_router_value(encode_router_value(password)) == password


def test_parse_connected_devices() -> None:
    """Only active records with valid MAC addresses are returned."""
    page = """
    <script>
    var deviceData=[
      ['1','Kitchen speaker','','192.168.1.42','','','AA:BB:CC:DD:EE:01'],
      ['0','Old phone','','192.168.1.43','','','AA:BB:CC:DD:EE:02'],
      ['1','','','192.168.1.44','','','aa-bb-cc-dd-ee-03'],
      ['1','Broken','','192.168.1.45','','','not-a-mac']
    ];
    </script>
    """

    devices = parse_device_data(page)

    assert list(devices) == ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:03"]
    assert devices["AA:BB:CC:DD:EE:01"].name == "Kitchen speaker"
    assert devices["AA:BB:CC:DD:EE:03"].name == "AA:BB:CC:DD:EE:03"
    assert devices["AA:BB:CC:DD:EE:03"].ip == "192.168.1.44"


def test_parse_rejects_page_without_device_data() -> None:
    """A login or incompatible page is not treated as an empty network."""
    with pytest.raises(RouterParseError, match="did not contain deviceData"):
        parse_device_data("<html>loginPassword</html>")


def test_authenticated_map_can_reference_login_endpoint() -> None:
    """The router map may mention its login endpoint after authentication."""
    map_page = """
    <script>
    var logoutUrl = '/cgi-bin/te_acceso_router.cgi';
    var deviceData=[['1','Laptop','','192.168.1.42','','','AA:BB:CC:DD:EE:01']];
    </script>
    """

    assert not _authentication_failed(map_page, "")


def test_login_page_without_device_data_is_auth_failure() -> None:
    """A login response without a device map is rejected as invalid auth."""
    assert _authentication_failed("<html>loginPassword</html>", "")
