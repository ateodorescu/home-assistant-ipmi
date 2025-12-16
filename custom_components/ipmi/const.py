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
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""
CONF_IPMI_SERVER_HOST = "ipmi_server_host"
DEFAULT_IPMI_SERVER_HOST = "http://localhost"
CONF_ADDON_PORT = "addon_port"
CONF_ADDON_INTERFACE = "addon_interface"
CONF_ADDON_PARAMS = "addon_extra_params"
CONF_KG_KEY = "kg_key"
CONF_IGNORE_CHECKSUM_ERRORS = "ignore_checksum_errors"
DEFAULT_KG_KEY = ""
CONF_PRIVILEGE_LEVEL = "privilege_level"
DEFAULT_PRIVILEGE_LEVEL = "ADMINISTRATOR"
PRIVILEGE_LEVELS = ["ADMINISTRATOR", "OPERATOR", "USER"]
DEFAULT_ADDON_PORT = 9595
DEFAULT_INTERFACE_TYPE = "lanplus"
DEFAULT_TIMEOUT = 60

KEY_STATUS = "status"

COORDINATOR = "coordinator"
DEFAULT_SCAN_INTERVAL = 60
# DEFAULT_SCAN_INTERVAL = 10
SERVERS = "servers"
DISPATCHERS = "dispatchers"

IPMI_DATA = "data"
IPMI_UNIQUE_ID = "unique_id"
IPMI_NEW_SENSOR_SIGNAL = "ipmi_new_sensor_signal.{}"
IPMI_UPDATE_SENSOR_SIGNAL = "ipmi_update_sensor_signal.{}"

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
    COMMAND_POWER_SOFT,
}

SERVICE_SEND_COMMAND = "send_command"
