"""The nut component."""
from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_SW_VERSION,
)

DOMAIN = "ipmi"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

DEFAULT_NAME = "IPMI Server"
DEFAULT_ALIAS = "server"
DEFAULT_HOST = ""
DEFAULT_PORT = 623
DEFAULT_USERNAME = "ADMIN"
DEFAULT_PASSWORD = ""
CONF_ADDON_PORT = "addon_port"
DEFAULT_ADDON_PORT = 9595

IPMI_URL = "http://localhost"

KEY_STATUS = "status"

COORDINATOR = "coordinator"
DEFAULT_SCAN_INTERVAL = 10

PYIPMI_DATA = "data"
PYIPMI_UNIQUE_ID = "unique_id"

IPMI_DEV_INFO_TO_DEV_INFO: dict[str, str] = {
    "manufacturer_name": ATTR_MANUFACTURER,
    "product_name": ATTR_MODEL,
    "firmware_revision": ATTR_SW_VERSION,
}

USER_AVAILABLE_COMMANDS = "user_available_commands"

COMMAND_POWER_ON = "power_on"
COMMAND_POWER_OFF = "power_off"
COMMAND_POWER_CYCLE = "power_cycle"
COMMAND_POWER_RESET = "power_reset"
COMMAND_POWER_SOFT = "soft_shutdown"

INTEGRATION_SUPPORTED_COMMANDS = {
    COMMAND_POWER_ON,
    COMMAND_POWER_OFF,
    COMMAND_POWER_CYCLE,
    COMMAND_POWER_RESET,
    COMMAND_POWER_SOFT
}
