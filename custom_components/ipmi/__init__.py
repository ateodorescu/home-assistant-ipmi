"""
The "ipmi" custom component.

This component implements the bare minimum that a component should implement.

Configuration:

To use the ipmi component you will need to add the following to your
configuration.yaml file.

ipmi:
"""
from __future__ import annotations

import asyncio
import async_timeout
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import cast
import pyipmi
import pyipmi.interfaces
from pyipmi.errors import IpmiConnectionError
import pyipmi.sensor
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

# The domain of your component. Should be equal to the name of your component.
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ALIAS,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RESOURCES,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    PYIPMI_DATA,
    PYIPMI_UNIQUE_ID,
    USER_AVAILABLE_COMMANDS,
    INTEGRATION_SUPPORTED_COMMANDS
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Network UPS Tools (NUT) from a config entry."""

    # strip out the stale options CONF_RESOURCES,
    # maintain the entry in data in case of version rollback
    if CONF_RESOURCES in entry.options:
        new_data = {**entry.data, CONF_RESOURCES: entry.options[CONF_RESOURCES]}
        new_options = {k: v for k, v in entry.options.items() if k != CONF_RESOURCES}
        hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options
        )

    config = entry.data
    host = config[CONF_HOST]
    port = config[CONF_PORT]

    alias = config.get(CONF_ALIAS)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    data = PyIpmiData(host, port, alias, username, password)

    async def async_update_data() -> IpmiDeviceInfo:
        """Fetch data from IPMI."""
        async with async_timeout.timeout(10):
            await hass.async_add_executor_job(data.update)
            if not data.device_info:
                raise UpdateFailed("Error fetching IPMI state")
            return data.device_info

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="IPMI resource status",
        update_method=async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    deviceInfo = coordinator.data
    # _LOGGER.info(repr(deviceInfo))
    # _LOGGER.info(repr(deviceInfo.sensors))

    _LOGGER.debug("IPMI Sensors Available: %s", deviceInfo)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    unique_id = alias + _unique_id_from_status(deviceInfo)
    if unique_id is None:
        unique_id = entry.entry_id

    user_available_commands = set()
    # if username is not None and password is not None:
    #     user_available_commands = {
    #         device_supported_command
    #         for device_supported_command in data.list_commands() or {}
    #         if device_supported_command in INTEGRATION_SUPPORTED_COMMANDS
    #     }
    # else:
    #     user_available_commands = set()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        PYIPMI_DATA: data,
        PYIPMI_UNIQUE_ID: unique_id,
        USER_AVAILABLE_COMMANDS: INTEGRATION_SUPPORTED_COMMANDS,
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, unique_id)},
        name=data.name.title(),
        manufacturer=data._device_info.manufacturer,
        model=data._device_info.product_name,
        sw_version=data._device_info.fw_revision,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)

def _unique_id_from_status(device_info: IpmiDeviceInfo) -> str | None:
    """Find the best unique id value from the status."""
    serial = device_info.serial_number
    # We must have a serial for this to be unique
    if not serial:
        return None

    manufacturer = device_info.manufacturer
    product_name = device_info.product_name

    unique_id_group = []
    if manufacturer:
        unique_id_group.append(manufacturer)
    # if product_name:
    #     unique_id_group.append(product_name)
    if serial:
        unique_id_group.append(serial)
    return "_".join(unique_id_group)

@dataclass
class IpmiDeviceInfo:
    """Device information for the IPMI server."""

    device_id: str | None = None
    revision: str | None = None
    fw_revision: str | None = None
    ipmi_version: str | None = None
    manufacturer: str | None = None
    product_name: str | None = None
    serial_number: str | None = None
    power_on: bool | False = False
    sensors: IpmiSensors | None = None

class IpmiSensors:
    temp: dict[str, str] = {}
    fan: dict[str, str] = {}
    voltage: dict[str, str] = {}
    states: dict[str, str] = {}

class PyIpmiData:
    """Stores the data retrieved from IPMI.

    For each entity to use, acts as the single point responsible for fetching
    updates from the server.
    """

    def __init__(
        self,
        host: str,
        port: int,
        alias: str | None,
        username: str | None,
        password: str | None,
    ) -> None:
        """Initialize the data object."""

        self._host = host
        self._port = port
        self._alias = alias
        self._username = username
        self._password = password

        # Establish client with persistent=False to open/close connection on
        # each update call.  This is more reliable with async.
        # self._client = PyNUTClient(self._host, port, username, password, 5, False)
        # self.ups_list: dict[str, str] | None = None
        # self._status: dict[str, str] | None = None
        self._device_info: IpmiDeviceInfo | None = None

    # @property
    # def status(self) -> dict[str, str] | None:
    #     """Get latest update if throttle allows. Return status."""
    #     return self._status

    @property
    def name(self) -> str:
        """Return the name of the IPMI server."""
        return self._alias or f"IPMI-{self._host}"

    @property
    def device_info(self) -> IpmiDeviceInfo:
        """Return the device info for the IPMI server."""
        return self._device_info

    def connect(self) -> pyipmi.Ipmi:
        interface = pyipmi.interfaces.create_interface('rmcp',
                                            slave_address=0x81,
                                            host_target_address=0x20,
                                            keep_alive_interval=0)
        ipmi = pyipmi.create_connection(interface)
        ipmi.session.set_session_type_rmcp(self._host, self._port)
        ipmi.session.set_auth_type_user(self._username, self._password)
        ipmi.session.establish()
        ipmi.target = pyipmi.Target(ipmb_address=0x20)

        return ipmi

    def update(self) -> None:
        try:
            ipmi = self.connect()

            inv = ipmi.get_fru_inventory()
                
            device_id = ipmi.get_device_id()
            manufacturer = inv.product_info_area.manufacturer.string
            product_name = inv.product_info_area.part_number.string
            serial_number =inv.product_info_area.serial_number.string
            revision = device_id.revision
            fw_revision = device_id.fw_revision.version_to_string()
            ipmi_version = device_id.ipmi_version.version_to_string()
            power_on = ipmi.get_chassis_status().power_on

            sensors = IpmiSensors()
            iter_fct = None

            if device_id.supports_function('sdr_repository'):
                iter_fct = ipmi.sdr_repository_entries
            elif device_id.supports_function('sensor'):
                iter_fct = ipmi.device_sdr_entries

            for s in iter_fct():
                name = getattr(s, 'device_id_string', None)
                id_string = re.sub('[^0-9a-zA-Z ]+', '', name)
                id_string = id_string.replace(' ', '_').lower()
                sensor_type = getattr(s, 'sensor_type_code', None)
                value = None

                try:
                    states = None

                    if s.type is pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD:
                        (value, states) = ipmi.get_sensor_reading(s.number)
                        if value is not None:
                            value = s.convert_sensor_raw_to_value(value)

                    elif s.type is pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD:
                        (value, states) = ipmi.get_sensor_reading(s.number)

                except pyipmi.errors.CompletionCodeError as e:
                    if s.type in (pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD,
                                pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD):
                        _LOGGER.debug('0x{:04x} | {:3d} | {:18s} | ERR: CC=0x{:02x}'.format(
                            s.id,
                            s.number,
                            s.device_id_string,
                            e.cc))

                if sensor_type == pyipmi.sensor.SENSOR_TYPE_TEMPERATURE:
                    sensors.temp[id_string] = name
                    sensors.states[id_string] = value

                elif sensor_type == pyipmi.sensor.SENSOR_TYPE_FAN:
                    sensors.fan[id_string] = name
                    sensors.states[id_string] = value

                elif sensor_type == pyipmi.sensor.SENSOR_TYPE_VOLTAGE:
                    sensors.voltage[id_string] = name
                    sensors.states[id_string] = value

            device_info = IpmiDeviceInfo(device_id, revision, fw_revision, ipmi_version, manufacturer, product_name, serial_number, power_on, sensors)
            ipmi.session.close()

        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)
            device_info = None
            sensors = None

        self._device_info = device_info
        self._sensors = sensors

    def power_on(self) -> None:
        try:
            ipmi = self.connect()
            ipmi.chassis_control(pyipmi.chassis.CONTROL_POWER_UP)
            ipmi.session.close()
        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)

    def power_off(self) -> None:
        try:
            ipmi = self.connect()
            ipmi.chassis_control(pyipmi.chassis.CONTROL_POWER_DOWN)
            ipmi.session.close()
        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)

    def power_cycle(self) -> None:
        try:
            ipmi = self.connect()
            ipmi.chassis_control(pyipmi.chassis.CONTROL_POWER_CYCLE)
            ipmi.session.close()
        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)

    def power_reset(self) -> None:
        try:
            ipmi = self.connect()
            ipmi.chassis_control(pyipmi.chassis.CONTROL_HARD_RESET)
            ipmi.session.close()
        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)

    def soft_shutdown(self) -> None:
        try:
            ipmi = self.connect()
            ipmi.chassis_control(pyipmi.chassis.CONTROL_SOFT_SHUTDOWN)
            ipmi.session.close()
        except (IpmiConnectionError, ConnectionResetError) as err:
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)

