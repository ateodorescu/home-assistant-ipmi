"""
The "ipmi" custom component.

This component implements the bare minimum that a component should implement.

Configuration:

To use the ipmi component you will need to add the following to your
configuration.yaml file.

ipmi:
"""
from __future__ import annotations

import async_timeout
import requests
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
    DEFAULT_TIMEOUT,
    CONF_ADDON_PORT,
    DOMAIN,
    PLATFORMS,
    PYIPMI_DATA,
    PYIPMI_UNIQUE_ID,
    USER_AVAILABLE_COMMANDS,
    INTEGRATION_SUPPORTED_COMMANDS,
    IPMI_URL,
    IPMI_DEV_INFO_TO_DEV_INFO
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPMI from a config entry."""

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

    alias = config[CONF_ALIAS]
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    addon_port = config[CONF_ADDON_PORT]
    
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    data = PyIpmiData(host, port, alias, username, password, addon_port)

    async def async_update_data() -> IpmiDeviceInfo:
        """Fetch data from IPMI."""
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
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

    _LOGGER.debug("IPMI Sensors Available: %s", deviceInfo)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # unique_id = alias + _unique_id_from_status(deviceInfo)
    # if unique_id is None:
    unique_id = entry.entry_id

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
        manufacturer=data._device_info.device["manufacturer_name"],
        model=data._device_info.device["product_name"],
        sw_version=data._device_info.device["firmware_revision"],
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
    alias = device_info.alias
    # We must have an alias for this to be unique
    if not alias:
        return None

    product_id = device_info.device["product_id"]

    unique_id_group = []
    if product_id:
        product_id = re.sub("\(.*?\)", '', product_id)
        unique_id_group.append(product_id)
    if alias:
        unique_id_group.append(alias)

    return "_".join(unique_id_group)

@dataclass
class IpmiDeviceInfo:
    """Device information for the IPMI server."""

    device: dict[str, str] = None
    power_on: bool | False = False
    sensors: dict[str, str] = None
    states: dict[str, str] = None
    alias: str = None

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
        addon_port: str | None,
    ) -> None:
        """Initialize the data object."""

        self._host = host
        self._port = port
        self._alias = alias
        self._username = username
        self._password = password
        self._addon_url = IPMI_URL + ":" + addon_port

        self._device_info: IpmiDeviceInfo | None = None

    @property
    def name(self) -> str:
        """Return the name of the IPMI server."""
        return self._alias or f"IPMI-{self._host}"

    @property
    def device_info(self) -> IpmiDeviceInfo:
        """Return the device info for the IPMI server."""
        return self._device_info

    def getFromAddon(self, path: str | None):
        response = None

        try:    
            params = {
                "host": self._host,
                "port": self._port,
                "user": self._username,
                "password": self._password
            }
            url = self._addon_url

            if path is not None:
                url += "/" + path

            ipmi = requests.get(url, params=params)
            response = ipmi.json()
        except (Exception) as err: # pylint: disable=broad-except
            _LOGGER.debug("'ipmi-server' addon is not available. Let's use RMCP.")

        return response
    
    def generateId(self, name: str):
        id = re.sub('[^A-Za-z0-9 _]+', '', name)
        id = id.replace(' ', '_').lower()

        return id

    def getFromRmcp(self):
        try:    
            json = {
                "device": {},
                "sensors": {
                    "temperature": {},
                    "voltage": {},
                    "fan": {},
                    "power": {},
                    "time": {}
                },
                "states": {},
                "power_on": False
            }
            ipmi = self.connect()

            inv = ipmi.get_fru_inventory()
                
            device_id = ipmi.get_device_id()
            
            json["device"]["manufacturer_name"] = inv.product_info_area.manufacturer.string
            json["device"]["product_name"] = inv.board_info_area.product_name.string
            json["device"]["firmware_revision"] = device_id.fw_revision.version_to_string()
            json["device"]["product_id"] = device_id.product_id
            json["power_on"] = ipmi.get_chassis_status().power_on

            iter_fct = None

            if device_id.supports_function('sdr_repository'):
                iter_fct = ipmi.sdr_repository_entries
            elif device_id.supports_function('sensor'):
                iter_fct = ipmi.device_sdr_entries

            for s in iter_fct():
                name = getattr(s, 'device_id_string', None)
                if name:
                    id_string = self.generateId(name)
                else:
                    id_string = name

                sensor_type = getattr(s, 'sensor_type_code', None)
                value = None

                try:
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
                    json["sensors"]["temperature"][id_string] = name
                    json["states"][id_string] = value

                elif sensor_type == pyipmi.sensor.SENSOR_TYPE_FAN:
                    json["sensors"]["fan"][id_string] = name
                    json["states"][id_string] = value

                elif sensor_type == pyipmi.sensor.SENSOR_TYPE_VOLTAGE:
                    json["sensors"]["voltage"][id_string] = name
                    json["states"][id_string] = value

            ipmi.session.close()
        
        # except (IpmiConnectionError, ConnectionResetError) as err:
        except (Exception) as err: # pylint: disable=broad-except
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)
            json = None

        return json
    
    def runRmcpCommand(self, command: int):
        try:
            ipmi = self.connect()
            ipmi.chassis_control(command)
            ipmi.session.close()
        except (Exception) as err: # pylint: disable=broad-except
            _LOGGER.error("Error connecting to IPMI server %s: %s", self._host, err)


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
        info = None

        json = self.getFromAddon(None)

        if (json is not None):
            if (json["debug"] is not None)
                _LOGGER.debug(json["debug"])

            if (not json["success"]):
                _LOGGER.error(json["message"])
                json = None
        else:
            json = self.getFromRmcp()

        if (json is not None):
            info = IpmiDeviceInfo()
            info.device = json["device"]
            info.power_on = json["power_on"]
            info.sensors = json["sensors"]
            info.states = json["states"]
            info.alias = self._alias
            self._device_info = info
        else:
            self._device_info = None

    def power_on(self) -> None:
        json = self.getFromAddon("power_on")

        if (json is None):
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_UP)

    def power_off(self) -> None:
        json = self.getFromAddon("power_off")

        if (json is None):
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_DOWN)

    def power_cycle(self) -> None:
        json = self.getFromAddon("power_cycle")

        if (json is None):
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_CYCLE)

    def power_reset(self) -> None:
        json = self.getFromAddon("power_reset")

        if (json is None):
            self.runRmcpCommand(pyipmi.chassis.CONTROL_HARD_RESET)

    def soft_shutdown(self) -> None:
        json = self.getFromAddon("soft_shutdown")

        if (json is None):
            self.runRmcpCommand(pyipmi.chassis.CONTROL_SOFT_SHUTDOWN)

