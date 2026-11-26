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

# Native (python-ipmi) LAN protocol. Missing key = IPMI 1.5 (rmcp), the
# historical hard-coded behavior. Does not affect the addon / ipmitool path.
CONF_NATIVE_PROTOCOL = "native_protocol"
NATIVE_PROTOCOL_RMCP = "rmcp"  # IPMI 1.5
NATIVE_PROTOCOL_RMCPPLUS = "rmcpplus"  # IPMI 2.0 (RMCP+)
DEFAULT_NATIVE_PROTOCOL = NATIVE_PROTOCOL_RMCP
NATIVE_PROTOCOLS = [NATIVE_PROTOCOL_RMCP, NATIVE_PROTOCOL_RMCPPLUS]

# RMCP+ cipher suite for the native path ("auto" = python-ipmi default: 17, then 3).
CONF_NATIVE_CIPHER_SUITE = "native_cipher_suite"
NATIVE_CIPHER_SUITE_AUTO = "auto"
DEFAULT_NATIVE_CIPHER_SUITE = NATIVE_CIPHER_SUITE_AUTO
NATIVE_CIPHER_SUITES = [NATIVE_CIPHER_SUITE_AUTO, "1", "2", "3", "15", "16", "17"]
DEFAULT_ADDON_PORT = 9595
DEFAULT_INTERFACE_TYPE = "lanplus"
DEFAULT_TIMEOUT = 60
# Addon proxies a full BMC poll; keep aligned with the coordinator budget for
# the read phase (time to receive a response once connected).
DEFAULT_HTTP_TIMEOUT = 60
# Fail fast when the addon isn't reachable at all (container down, wrong port,
# network unreachable) instead of waiting out the full read timeout for a
# connection that was never going to be established. Established TCP
# connections to a local addon complete in milliseconds when it's up.
DEFAULT_HTTP_CONNECT_TIMEOUT = 5

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

# Optional companion energy (kWh) sensors derived from discovered power sensors.
CONF_CREATE_ENERGY_SENSORS = "create_energy_sensors"
DEFAULT_CREATE_ENERGY_SENSORS = True
ENERGY_SENSOR_KEY_SUFFIX = "_energy"

# Keep the power switch off after soft shutdown while the OS is still stopping.
CONF_POWER_OFF_DELAY = "power_off_delay"
DEFAULT_POWER_OFF_DELAY = 60
MAX_POWER_OFF_DELAY = 600

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

# Addon HTTP API capability names (reported by ipmi-server 2.6+ in JSON or GET /meta).
ADDON_CAPABILITY_SENSOR_TYPES_FILTER = "sensor_types_filter"
ADDON_CAPABILITY_RESILIENT_POLL = "resilient_poll"
ADDON_META_PATH = "meta"

# Addon request headers for BMC secrets (read by ipmi-server 2.5.1+). Keeping secrets
# in headers instead of the query string keeps them out of HTTP access logs (#90).
ADDON_PASSWORD_HEADER = "X-Ipmi-Password"
ADDON_KG_KEY_HEADER = "X-Ipmi-Kg-Key"

# Legacy option: prefer empty sensor_types (kept for config entry downgrade compatibility).
CONF_MINIMAL_IPMI = "minimal_ipmi"
DEFAULT_MINIMAL_IPMI = False

