"""Constants for the Movistar Askey Router integration."""

from typing import Final

DOMAIN: Final = "movistar_rft8115vw"

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_CONSIDER_HOME: Final = "consider_home"

DEFAULT_HOST: Final = "192.168.1.1"
DEFAULT_SCAN_INTERVAL: Final = 300
DEFAULT_CONSIDER_HOME: Final = 600

FAILURE_TOLERANCE: Final = 3

EVENT_ROUTER_REBOOTED: Final = f"{DOMAIN}_router_rebooted"

MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600

ROUTER_MANUFACTURER: Final = "Askey"
ROUTER_MODEL: Final = "RTF8115VW / RTF8316VW"
ROUTER_NAME: Final = "Movistar Askey Router"
