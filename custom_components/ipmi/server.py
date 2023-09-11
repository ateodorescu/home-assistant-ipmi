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
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    CONF_ADDON_PORT,
    DOMAIN,
    PLATFORMS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_NEW_SENSOR_SIGNAL,
    IPMI_UPDATE_SENSOR_SIGNAL,
    USER_AVAILABLE_COMMANDS,
    INTEGRATION_SUPPORTED_COMMANDS,
    IPMI_URL,
    SERVERS,
    DISPATCHERS,
    IPMI_DEV_INFO_TO_DEV_INFO
)

_LOGGER = logging.getLogger(__name__)

@dataclass
class IpmiDeviceInfo:
    """Device information for the IPMI server."""

    device: dict[str, str] = None
    power_on: bool | False = False
    sensors: dict[str, str] = None
    states: dict[str, str] = None
    alias: str = None

class IpmiServer:
    """Stores the data retrieved from IPMI.

    For each entity to use, acts as the single point responsible for fetching
    updates from the server.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        alias: str | None,
        username: str | None,
        password: str | None,
        addon_port: str | None,
    ) -> None:
        """Initialize the data object."""

        self._entry_id = entry_id
        self.hass = hass
        self._host = host
        self._port = port
        self._alias = alias
        self._username = username
        self._password = password
        self._addon_url = IPMI_URL + ":" + addon_port
        
# when addon runs in dev mode (local web server)
#         self._addon_url += '/repositories/home-assistant-addons/ipmi-server/rootfs/app/public'

        self._device_info: IpmiDeviceInfo | None = None
        self._known_sensors = []

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

        if (info is not None):
            new_sensors = []
            # _LOGGER.critical(repr(info))
            # _LOGGER.critical(self._known_sensors)

            if (len(info.states) == 0):
                self._known_sensors.clear()
            else:
                to_remove = []
                for id in self._known_sensors:
                    if (id not in info.states):
                        to_remove.append(id)
                for id in to_remove:
                    self._known_sensors.remove(id)

                for id in info.states:
                    if (self._known_sensors.count(id) == 0):
                        new_sensors.append(id)

                if (len(new_sensors) > 0):
                    async_dispatcher_send(
                        self.hass,
                        IPMI_NEW_SENSOR_SIGNAL.format(self._entry_id),
                        new_sensors,
                    )

    def add_known_sensor(self, id: str) -> None:
        if self._known_sensors.count(id) == 0:
            self._known_sensors.append(id)

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

