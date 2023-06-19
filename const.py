"""The nut component."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ipmi"

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

DEFAULT_NAME = "IPMI Server"
DEFAULT_ALIAS = "server"
DEFAULT_HOST = ""
DEFAULT_PORT = 623
DEFAULT_USERNAME = "ADMIN"
DEFAULT_PASSWORD = ""

KEY_STATUS = "status"

COORDINATOR = "coordinator"
DEFAULT_SCAN_INTERVAL = 10

PYIPMI_DATA = "data"
PYIPMI_UNIQUE_ID = "unique_id"


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

# IPMI_SUPPORTED_COMMANDS = (
#         ('SENSOR', 'Sensor Device'),
#         ('SDR_REPOSITORY', 'SDR Repository Device'),
#         ('SEL', 'SEL Device'),
#         ('FRU_INVENTORY', 'FRU Inventory Device'),
#         ('IPMB_EVENT_RECEIVER', 'IPMB Event Receiver'),
#         ('IPMB_EVENT_GENERATOR', 'IPMB Event Generator'),
#         ('BRIDGE', 'Bridge'),
#         ('CHASSIS', 'Chassis Device')
# )