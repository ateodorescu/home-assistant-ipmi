from __future__ import annotations

from dataclasses import dataclass
import logging

import pyipmi
import pyipmi.interfaces
import pyipmi.sensor
import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send

from .const import (
    BACKEND_ADDON,
    BACKEND_NONE,
    BACKEND_RMCP,
    CONF_IGNORE_CHECKSUM_ERRORS,
    DEFAULT_HTTP_TIMEOUT,
    IPMI_NEW_SENSOR_SIGNAL,
)
from .util import (
    generate_sensor_id,
    looks_like_auth_error,
    redact_connection_secrets,
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
        entry_id: str | None,
        connection_data: dict,
    ) -> None:
        """Initialize the data object."""

        self._entry_id = entry_id
        self.hass = hass
        self._host = connection_data.get("host")
        self._port = connection_data.get("port")
        self._alias = connection_data.get("alias")
        self._username = connection_data.get("username")
        self._password = connection_data.get("password")
        self._kg_key = connection_data.get("kg_key")
        self._privilege_level = connection_data.get("privilege_level")
        self._addon_url = (
            f"{connection_data.get('ipmi_server_host')}:"
            f"{connection_data.get('addon_port')}"
        )
        self._addon_interface = connection_data.get("addon_interface")
        self._addon_extra_params = connection_data.get("addon_extra_params")
        self._ignore_checksum_errors = connection_data.get(
            CONF_IGNORE_CHECKSUM_ERRORS, False
        )

        self._device_info: IpmiDeviceInfo | None = None
        self._known_sensors = []
        self.last_backend = BACKEND_NONE
        self.auth_failed = False
        self._last_rmcp_error: str | None = None

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
                "password": self._password,
            }

            if self._addon_interface is not None and self._addon_interface != "auto":
                params["interface"] = self._addon_interface

            if self._kg_key:
                params["kg_key"] = self._kg_key

            if self._privilege_level:
                params["privilege_level"] = self._privilege_level

            if self._addon_extra_params:
                params["extra"] = self._addon_extra_params

            url = self._addon_url

            if path is not None:
                url += "/" + path

            _LOGGER.debug(
                "Addon request url=%s host=%s port=%s user=%s path=%s",
                url,
                self._host,
                self._port,
                self._username,
                path,
            )
            ipmi = requests.get(url, params=params, timeout=DEFAULT_HTTP_TIMEOUT)
            response = ipmi.json()
        except Exception as err:  # pylint: disable=broad-except
            err_msg = redact_connection_secrets(
                str(err), self._password, self._kg_key
            )
            _LOGGER.warning(
                "ipmi-server addon unavailable at %s (%s: %s); falling back to RMCP",
                self._addon_url,
                type(err).__name__,
                err_msg,
            )

        return response

    def generateId(self, name: str):
        return generate_sensor_id(name)

    def getFromRmcp(self):
        try:
            json = {
                "device": {},
                "sensors": {
                    "temperature": {},
                    "voltage": {},
                    "fan": {},
                    "power": {},
                    "current": {},
                    "time": {},
                },
                "states": {},
                "power_on": False,
            }
            ipmi = self.connect()
            try:
                device_id = ipmi.get_device_id()

                try:
                    inv = ipmi.get_fru_inventory(
                        ignore_checksum=self._ignore_checksum_errors
                    )
                    json["device"]["manufacturer_name"] = (
                        inv.product_info_area.manufacturer.string
                    )
                    json["device"]["product_name"] = (
                        inv.board_info_area.product_name.string
                    )
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.warning("Error getting FRU Inventory Device")
                    json["device"]["manufacturer_name"] = "None"
                    json["device"]["product_name"] = "None"

                json["device"]["firmware_revision"] = (
                    device_id.fw_revision.version_to_string()
                )
                json["device"]["product_id"] = device_id.product_id
                json["power_on"] = ipmi.get_chassis_status().power_on

                iter_fct = None

                if device_id.supports_function("sdr_repository"):
                    iter_fct = ipmi.sdr_repository_entries
                elif device_id.supports_function("sensor"):
                    iter_fct = ipmi.device_sdr_entries

                if iter_fct is None:
                    _LOGGER.warning(
                        "IPMI server %s does not expose SDR/sensor repository",
                        self._host,
                    )
                else:
                    for s in iter_fct():
                        name = getattr(s, "device_id_string", None)
                        if name:
                            id_string = self.generateId(name)
                        else:
                            id_string = name

                        sensor_type = getattr(s, "sensor_type_code", None)
                        value = None
                        category = None

                        try:
                            if s.type is pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD:
                                (value, states) = ipmi.get_sensor_reading(s.number)
                                if value is not None:
                                    value = s.convert_sensor_raw_to_value(value)

                            elif s.type is pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD:
                                (value, states) = ipmi.get_sensor_reading(s.number)

                        except pyipmi.errors.CompletionCodeError as e:
                            if s.type in (
                                pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD,
                                pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD,
                            ):
                                _LOGGER.debug(
                                    "0x{:04x} | {:3d} | {:18s} | ERR: CC=0x{:02x}".format(
                                        s.id, s.number, s.device_id_string, e.cc
                                    )
                                )

                        if sensor_type == pyipmi.sensor.SENSOR_TYPE_TEMPERATURE:
                            category = "temperature"
                        elif sensor_type == pyipmi.sensor.SENSOR_TYPE_FAN:
                            category = "fan"
                        elif sensor_type == pyipmi.sensor.SENSOR_TYPE_VOLTAGE:
                            category = "voltage"
                        elif sensor_type == pyipmi.sensor.SENSOR_TYPE_CURRENT:
                            category = "current"
                        else:
                            # IPMI unit type codes (Table 43-15) on full/compact records
                            category = {
                                0x05: "current",  # Amps
                                0x06: "power",  # Watts
                                0x15: "time",  # seconds
                            }.get(getattr(s, "units_2", None))

                        if category and id_string is not None:
                            json["sensors"][category][id_string] = name
                            json["states"][id_string] = value
            finally:
                self._close_ipmi(ipmi)

        except Exception as err:  # pylint: disable=broad-except
            self._last_rmcp_error = f"{type(err).__name__}: {err}"
            _LOGGER.warning(
                "RMCP connection to IPMI server %s failed: %s",
                self._host,
                self._last_rmcp_error,
            )
            json = None

        return json

    def runRmcpCommand(self, command: int):
        ipmi = None
        try:
            ipmi = self.connect()
            ipmi.chassis_control(command)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error connecting to IPMI server %s: %s: %s",
                self._host,
                type(err).__name__,
                err,
            )
        finally:
            self._close_ipmi(ipmi)

    def _close_ipmi(self, ipmi: pyipmi.Ipmi | None) -> None:
        """Close an IPMI connection, ignoring teardown errors."""
        if ipmi is None:
            return
        try:
            ipmi.close()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug(
                "Error closing IPMI connection to %s: %s: %s",
                self._host,
                type(err).__name__,
                err,
            )

    def connect(self) -> pyipmi.Ipmi:
        """Create and open a native RMCP IPMI session.

        python-ipmi >= 0.5.8 requires interface.open() before session traffic;
        ipmi.open() does that and then establishes the session. Target must be
        set before open (see python-ipmi RMCP example).
        """
        interface = pyipmi.interfaces.create_interface(
            "rmcp", slave_address=0x81, host_target_address=0x20, keep_alive_interval=0
        )
        ipmi = pyipmi.create_connection(interface)
        ipmi.session.set_session_type_rmcp(self._host, int(self._port))
        ipmi.session.set_auth_type_user(
            self._username or "", self._password or ""
        )

        # Note: python-ipmi library does not support Kg keys - only ipmi-server addon supports this
        if self._kg_key:
            _LOGGER.warning(
                "Kg key specified but python-ipmi library does not support Kg key authentication. Kg key will be ignored. Consider using the ipmi-server addon for full feature support."
            )

        # Set privilege level if provided
        if self._privilege_level:
            ipmi.session.set_priv_level(self._privilege_level)

        ipmi.target = pyipmi.Target(ipmb_address=0x20)
        ipmi.open()

        return ipmi

    def update(self) -> None:
        info = None
        self.auth_failed = False
        self._last_rmcp_error = None
        self.last_backend = BACKEND_NONE

        json = self.getFromAddon(None)

        if json is not None:
            if not json["success"]:
                message = str(json.get("message", ""))
                _LOGGER.error(message)
                self.auth_failed = looks_like_auth_error(message)
                json = None
            else:
                self.last_backend = BACKEND_ADDON
        else:
            json = self.getFromRmcp()
            if json is not None:
                self.last_backend = BACKEND_RMCP
            else:
                self.auth_failed = looks_like_auth_error(self._last_rmcp_error)

        if json is not None:
            info = IpmiDeviceInfo()
            info.device = json["device"]
            info.power_on = json["power_on"]
            info.sensors = json["sensors"]
            info.states = json["states"]
            info.alias = self._alias
            self._device_info = info
            self.auth_failed = False
        else:
            self._device_info = None

        if info is not None:
            new_sensors = []

            if len(info.states) == 0:
                self._known_sensors.clear()
            else:
                to_remove = []
                for id in self._known_sensors:
                    if id not in info.states:
                        to_remove.append(id)
                for id in to_remove:
                    self._known_sensors.remove(id)

                for id in info.states:
                    if self._known_sensors.count(id) == 0:
                        new_sensors.append(id)

                if len(new_sensors) > 0:
                    dispatcher_send(
                        self.hass, IPMI_NEW_SENSOR_SIGNAL.format(self._entry_id)
                    )

    def is_known_sensor(self, id: str) -> bool:
        return self._known_sensors.count(id) > 0

    def add_known_sensor(self, id: str) -> None:
        if self._known_sensors.count(id) == 0:
            self._known_sensors.append(id)

    def power_on(self) -> None:
        json = self.getFromAddon("power_on")

        if json is None:
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_UP)

    def power_off(self) -> None:
        json = self.getFromAddon("power_off")

        if json is None:
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_DOWN)

    def power_cycle(self) -> None:
        json = self.getFromAddon("power_cycle")

        if json is None:
            self.runRmcpCommand(pyipmi.chassis.CONTROL_POWER_CYCLE)

    def power_reset(self) -> None:
        json = self.getFromAddon("power_reset")

        if json is None:
            self.runRmcpCommand(pyipmi.chassis.CONTROL_HARD_RESET)

    def soft_shutdown(self) -> None:
        json = self.getFromAddon("soft_shutdown")

        if json is None:
            self.runRmcpCommand(pyipmi.chassis.CONTROL_SOFT_SHUTDOWN)

    def send_command(self, command: str, ignore_errors: bool) -> str:
        cmd = command.replace("$host$", self._host)
        cmd = cmd.replace("$port$", str(self._port))
        cmd = cmd.replace("$username$", self._username)
        cmd = cmd.replace("$password$", self._password)

        uri_encoded = requests.utils.quote(cmd)
        response = self.getFromAddon("command?params=" + uri_encoded)

        if response is None:
            err = "Error executing command: {}".format(command)
            if ignore_errors:
                _LOGGER.error(err)
            else:
                raise Exception(err)

        if response["success"] == False:
            err = "Error executing command: {}, Error: {}".format(
                command, response["output"]
            )
            if ignore_errors:
                _LOGGER.error(err)
            else:
                raise Exception(err)

        return response["output"]
