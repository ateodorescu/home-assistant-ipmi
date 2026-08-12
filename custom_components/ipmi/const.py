from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_SW_VERSION,
)

DOMAIN = "ipmi"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR, Platform.BUTTON]

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
# Addon proxies a full BMC poll; keep aligned with the coordinator budget.
DEFAULT_HTTP_TIMEOUT = 60

KEY_STATUS = "status"
KEY_CONNECTION_BACKEND = "connection_backend"

BACKEND_ADDON = "addon"
BACKEND_RMCP = "rmcp"
BACKEND_NONE = "none"

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

# Dynamic SDR / addon sensor groups
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_VOLTAGE = "voltage"
SENSOR_TYPE_FAN = "fan"
SENSOR_TYPE_POWER = "power"
SENSOR_TYPE_CURRENT = "current"
SENSOR_TYPE_TIME = "time"

SENSOR_TYPES = [
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_VOLTAGE,
    SENSOR_TYPE_FAN,
    SENSOR_TYPE_POWER,
    SENSOR_TYPE_CURRENT,
    SENSOR_TYPE_TIME,
]

CONF_SENSOR_TYPES = "sensor_types"
# Missing options = today's behavior: discover all types.
DEFAULT_SENSOR_TYPES = list(SENSOR_TYPES)

# Connection backend preference (options). Default "auto" preserves addon-first fallback.
CONF_BACKEND_PREFERENCE = "backend_preference"
BACKEND_PREFERENCE_AUTO = "auto"
BACKEND_PREFERENCE_ADDON = "addon"
BACKEND_PREFERENCE_RMCP = "rmcp"
DEFAULT_BACKEND_PREFERENCE = BACKEND_PREFERENCE_AUTO
BACKEND_PREFERENCES = [
    BACKEND_PREFERENCE_AUTO,
    BACKEND_PREFERENCE_ADDON,
    BACKEND_PREFERENCE_RMCP,
]

# After this many consecutive addon transport failures, briefly skip probing (auto mode).
ADDON_FAILURE_SKIP_THRESHOLD = 3
ADDON_SKIP_SECONDS = 300

