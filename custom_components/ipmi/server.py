"""IPMI connection owner: addon HTTP API first, python-ipmi RMCP fallback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any

import pyipmi
import pyipmi.interfaces
import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import dispatcher_send

from .const import (
    ADDON_FAILURE_SKIP_THRESHOLD,
    ADDON_META_PATH,
    ADDON_SKIP_SECONDS,
    BACKEND_ADDON,
    BACKEND_NONE,
    BACKEND_PREFERENCE_ADDON,
    BACKEND_PREFERENCE_AUTO,
    BACKEND_PREFERENCE_RMCP,
    BACKEND_RMCP,
    CONF_IGNORE_CHECKSUM_ERRORS,
    DEFAULT_BACKEND_PREFERENCE,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_SENSOR_TYPES,
    IPMI_NEW_SENSOR_SIGNAL,
    SENSOR_TYPES,
)
from .util import (
    addon_action_succeeded,
    categorize_rmcp_sensor,
    effective_sensor_types,
    generate_sensor_id,
    IpmiChassisCommandError,
    iter_discovered_sensor_ids,
    looks_like_auth_error,
    normalize_addon_mapping,
    normalize_addon_sensor_groups,
    power_only_poll,
    redact_connection_secrets,
    update_addon_capabilities,
)

_LOGGER = logging.getLogger(__name__)

# HTTP statuses that mean "this addon build does not accept POST" → fall back to GET.
_POST_UNSUPPORTED_STATUSES = frozenset({404, 405, 501})


@dataclass
class IpmiDeviceInfo:
    """Device information for the IPMI server."""

    device: dict[str, Any] = field(default_factory=dict)
    power_on: bool = False
    sensors: dict[str, dict[str, str]] = field(default_factory=dict)
    states: dict[str, Any] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    alias: str | None = None


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
        self._backend_preference = connection_data.get(
            "backend_preference", DEFAULT_BACKEND_PREFERENCE
        )
        self._sensor_types = effective_sensor_types(
            connection_data, default_types=DEFAULT_SENSOR_TYPES
        )

        self._device_info: IpmiDeviceInfo | None = None
        self._known_sensors: set[str] = set()
        self.last_backend = BACKEND_NONE
        self.auth_failed = False
        self._last_rmcp_error: str | None = None

        # Addon HTTP: GET is the supported API (query params). POST is only used after
        # a successful probe so we never break addons that ignore JSON bodies.
        self._addon_use_post: bool = False
        self._addon_fail_count = 0
        self._addon_skip_until: float = 0.0
        self._addon_capabilities: set[str] = set()
        self._addon_version: str | None = None
        self._addon_api_version: int | None = None
        self._addon_meta_probed: bool = False

        # Reused RMCP session (reconnected on error).
        self._rmcp_ipmi: pyipmi.Ipmi | None = None
        self._rmcp_lock = threading.Lock()

    @property
    def name(self) -> str:
        """Return the name of the IPMI server."""
        return self._alias or f"IPMI-{self._host}"

    @property
    def device_info(self) -> IpmiDeviceInfo | None:
        """Return the device info for the IPMI server."""
        return self._device_info

    def set_backend_preference(self, preference: str) -> None:
        """Update backend preference (e.g. after options reload)."""
        self._backend_preference = preference or DEFAULT_BACKEND_PREFERENCE

    def set_sensor_types(self, sensor_types: list[str]) -> None:
        """Update requested sensor types (e.g. after options reload)."""
        self._sensor_types = list(sensor_types)

    @property
    def addon_capabilities(self) -> set[str]:
        """Capabilities reported by the ipmi-server addon, if any."""
        return set(self._addon_capabilities)

    @property
    def addon_version(self) -> str | None:
        """ipmi-server add-on version string from the last capability payload."""
        return self._addon_version

    def _power_only_poll(self) -> bool:
        """Return True when polling should skip sensor/FRU discovery."""
        return power_only_poll(self._sensor_types)

    @staticmethod
    def _empty_sensor_groups() -> dict[str, dict[str, str]]:
        """Return empty sensor buckets for all dynamic sensor types."""
        return {sensor_type: {} for sensor_type in SENSOR_TYPES}

    def _addon_query_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build addon request parameters (auth + optional extras)."""
        params: dict[str, Any] = {
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

        poll_params = self._addon_poll_query_params()
        if poll_params:
            params.update(poll_params)

        if extra:
            params.update(extra)
        return params

    def _addon_poll_query_params(self) -> dict[str, str]:
        """Optional poll query params (additive; ignored by older addon builds)."""
        if self._power_only_poll():
            return {"sensor_types": ""}
        if set(self._sensor_types) >= set(SENSOR_TYPES):
            return {}
        return {"sensor_types": ",".join(self._sensor_types)}

    def _ingest_addon_capabilities(self, response: Mapping[str, Any]) -> None:
        """Update cached addon version/capabilities from a JSON payload."""
        self._addon_capabilities = update_addon_capabilities(
            self._addon_capabilities, response
        )
        addon_version = response.get("addon_version")
        if isinstance(addon_version, str) and addon_version:
            self._addon_version = addon_version
        api_version = response.get("api_version")
        if isinstance(api_version, int):
            self._addon_api_version = api_version
        elif isinstance(api_version, str) and api_version.isdigit():
            self._addon_api_version = int(api_version)

    def _probe_addon_meta(self) -> None:
        """Probe GET /meta once for capability discovery (no BMC credentials)."""
        if self._addon_meta_probed or not self._should_try_addon():
            return
        self._addon_meta_probed = True
        url = f"{self._addon_url}/{ADDON_META_PATH}"
        try:
            http_resp = requests.get(url, timeout=10)
            if http_resp.status_code in {404, 405}:
                return
            http_resp.raise_for_status()
            payload = http_resp.json()
            if isinstance(payload, dict):
                self._ingest_addon_capabilities(payload)
                self._record_addon_transport_success()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug(
                "Addon meta probe at %s failed (%s); continuing with legacy behavior",
                url,
                type(err).__name__,
            )

    def _should_try_addon(self) -> bool:
        """Whether this poll/action should attempt the addon HTTP API."""
        if self._backend_preference == BACKEND_PREFERENCE_RMCP:
            return False
        if self._backend_preference == BACKEND_PREFERENCE_ADDON:
            return True
        # auto: skip briefly after repeated transport failures
        if self._addon_fail_count >= ADDON_FAILURE_SKIP_THRESHOLD:
            if time.monotonic() < self._addon_skip_until:
                _LOGGER.debug(
                    "Skipping addon probe for %s until cooldown ends",
                    self._addon_url,
                )
                return False
            # Cooldown expired — allow another probe attempt.
            self._addon_fail_count = 0
        return True

    def _should_try_rmcp(self) -> bool:
        """Whether RMCP fallback / primary is allowed."""
        return self._backend_preference != BACKEND_PREFERENCE_ADDON

    def _record_addon_transport_failure(self) -> None:
        """Track consecutive addon transport failures for auto-mode short-circuit."""
        if self._backend_preference != BACKEND_PREFERENCE_AUTO:
            return
        self._addon_fail_count += 1
        if self._addon_fail_count >= ADDON_FAILURE_SKIP_THRESHOLD:
            self._addon_skip_until = time.monotonic() + ADDON_SKIP_SECONDS
            _LOGGER.debug(
                "Addon unreachable %s times; skipping probes for %ss",
                self._addon_fail_count,
                ADDON_SKIP_SECONDS,
            )

    def _record_addon_transport_success(self) -> None:
        """Reset addon failure short-circuit after a successful HTTP response."""
        self._addon_fail_count = 0
        self._addon_skip_until = 0.0

    def get_from_addon(
        self,
        path: str | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Call the addon / standalone HTTP API.

        Uses GET with query params (the supported addon API). Optional POST is
        only used after it has been proven to return a successful payload; a
        POST that returns HTTP 200 with ``success: false`` (common when the
        addon ignores JSON bodies) must not block GET.
        """
        if not self._should_try_addon():
            return None

        params = self._addon_query_params(extra)
        url = self._addon_url
        if path is not None:
            url = f"{url}/{path}"

        _LOGGER.debug(
            "Addon request url=%s host=%s port=%s user=%s path=%s post=%s",
            url,
            self._host,
            self._port,
            self._username,
            path,
            self._addon_use_post,
        )

        try:
            if self._addon_use_post:
                try:
                    http_resp = requests.post(
                        url, json=params, timeout=DEFAULT_HTTP_TIMEOUT
                    )
                    if http_resp.status_code not in _POST_UNSUPPORTED_STATUSES:
                        http_resp.raise_for_status()
                        response = http_resp.json()
                        if addon_action_succeeded(response):
                            self._record_addon_transport_success()
                            if isinstance(response, dict):
                                self._ingest_addon_capabilities(response)
                            return response
                    # POST not usable for this addon build — stick to GET.
                    self._addon_use_post = False
                    _LOGGER.debug(
                        "Addon POST not usable; using GET for %s", self._addon_url
                    )
                except Exception:  # pylint: disable=broad-except
                    self._addon_use_post = False

            http_resp = requests.get(
                url, params=params, timeout=DEFAULT_HTTP_TIMEOUT
            )
            http_resp.raise_for_status()
            response = http_resp.json()
            self._record_addon_transport_success()
            if isinstance(response, dict):
                self._ingest_addon_capabilities(response)
            return response
        except Exception as err:  # pylint: disable=broad-except
            err_msg = redact_connection_secrets(
                str(err), self._password, self._kg_key
            )
            self._record_addon_transport_failure()
            _LOGGER.warning(
                "ipmi-server addon unavailable at %s (%s: %s); falling back to RMCP",
                self._addon_url,
                type(err).__name__,
                err_msg,
            )
            return None

    def _run_addon_action(self, path: str) -> bool:
        """Run a chassis action via addon. True if succeeded; False to try RMCP."""
        payload = self.get_from_addon(path)
        if payload is None:
            return False
        if addon_action_succeeded(payload):
            return True
        message = str(payload.get("message") or payload.get("output") or payload)
        _LOGGER.warning(
            "Addon action %s failed (%s); falling back to RMCP if allowed",
            path,
            redact_connection_secrets(message, self._password, self._kg_key),
        )
        return False

    def get_from_rmcp(self) -> dict[str, Any] | None:
        """Poll device info and sensors via python-ipmi (RMCP)."""
        with self._rmcp_lock:
            if self._power_only_poll():
                return self._get_from_rmcp_power_only()
            return self._get_from_rmcp_full()

    def _get_from_rmcp_power_only(self) -> dict[str, Any] | None:
        """Poll chassis power and basic device id only (no FRU/SDR). Caller holds RMCP lock."""
        try:
            json: dict[str, Any] = {
                "device": {},
                "sensors": self._empty_sensor_groups(),
                "states": {},
                "power_on": False,
            }
            ipmi = self._connect_unlocked()
            try:
                device_id = ipmi.get_device_id()
                json["device"]["manufacturer_name"] = "None"
                json["device"]["product_name"] = "None"
                json["device"]["firmware_revision"] = (
                    device_id.fw_revision.version_to_string()
                )
                json["device"]["product_id"] = device_id.product_id
                json["power_on"] = ipmi.get_chassis_status().power_on
            except Exception:
                self._invalidate_rmcp_session_unlocked()
                raise
        except Exception as err:  # pylint: disable=broad-except
            self._last_rmcp_error = f"{type(err).__name__}: {err}"
            _LOGGER.warning(
                "RMCP power-only poll for IPMI server %s failed: %s",
                self._host,
                self._last_rmcp_error,
            )
            return None

        return json

    def _get_from_rmcp_full(self) -> dict[str, Any] | None:
        """Poll full device info, FRU metadata, and SDR sensors via python-ipmi. Caller holds RMCP lock."""
        try:
            json: dict[str, Any] = {
                "device": {},
                "sensors": self._empty_sensor_groups(),
                "states": {},
                "power_on": False,
            }
            ipmi = self._connect_unlocked()
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
                        id_string = generate_sensor_id(name) if name else name

                        sensor_type = getattr(s, "sensor_type_code", None)
                        value = None

                        try:
                            if s.type is pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD:
                                (value, _states) = ipmi.get_sensor_reading(s.number)
                                if value is not None:
                                    value = s.convert_sensor_raw_to_value(value)

                            elif s.type is pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD:
                                (value, _states) = ipmi.get_sensor_reading(s.number)

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

                        category = categorize_rmcp_sensor(
                            sensor_type, getattr(s, "units_2", None)
                        )

                        if category and id_string is not None:
                            json["sensors"][category][id_string] = name
                            json["states"][id_string] = value
            except Exception:
                # Drop cached session so the next call reconnects.
                self._invalidate_rmcp_session_unlocked()
                raise

        except Exception as err:  # pylint: disable=broad-except
            self._last_rmcp_error = f"{type(err).__name__}: {err}"
            _LOGGER.warning(
                "RMCP connection to IPMI server %s failed: %s",
                self._host,
                self._last_rmcp_error,
            )
            return None

        return json

    def run_rmcp_command(self, command: int) -> None:
        """Send a chassis control command over RMCP.

        Raises:
            IpmiChassisCommandError: When the command cannot be sent or completes with error.
        """
        with self._rmcp_lock:
            try:
                ipmi = self._connect_unlocked()
                try:
                    ipmi.chassis_control(command)
                except Exception:
                    self._invalidate_rmcp_session_unlocked()
                    raise
            except Exception as err:
                raise IpmiChassisCommandError(
                    f"RMCP chassis command failed for {self._host}: "
                    f"{type(err).__name__}: {err}"
                ) from err

    def _invalidate_rmcp_session_unlocked(self) -> None:
        """Close and forget the cached RMCP session (caller must hold ``_rmcp_lock``)."""
        self._close_ipmi(self._rmcp_ipmi)
        self._rmcp_ipmi = None

    def _invalidate_rmcp_session(self) -> None:
        """Close and forget the cached RMCP session."""
        with self._rmcp_lock:
            self._invalidate_rmcp_session_unlocked()

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

    def close(self) -> None:
        """Release the cached RMCP session (call on unload)."""
        with self._rmcp_lock:
            self._invalidate_rmcp_session_unlocked()

    def connect(self) -> pyipmi.Ipmi:
        """Return a (re)used native RMCP IPMI session."""
        with self._rmcp_lock:
            return self._connect_unlocked()

    def _connect_unlocked(self) -> pyipmi.Ipmi:
        """Return a (re)used RMCP session. Caller must hold ``_rmcp_lock``."""
        if self._rmcp_ipmi is not None:
            return self._rmcp_ipmi

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
                "Kg key specified but python-ipmi library does not support Kg key "
                "authentication. Kg key will be ignored. Consider using the "
                "ipmi-server addon for full feature support."
            )

        if self._privilege_level:
            ipmi.session.set_priv_level(self._privilege_level)

        ipmi.target = pyipmi.Target(ipmb_address=0x20)
        ipmi.open()
        self._rmcp_ipmi = ipmi
        return ipmi

    def update(self) -> None:
        """Refresh device info from the preferred backend(s)."""
        info = None
        self.auth_failed = False
        self._last_rmcp_error = None
        self.last_backend = BACKEND_NONE

        json: dict[str, Any] | None = None

        self._probe_addon_meta()

        if self._should_try_addon():
            json = self.get_from_addon(None)
            if json is not None:
                if not json.get("success"):
                    message = str(json.get("message", ""))
                    _LOGGER.error(message)
                    self.auth_failed = looks_like_auth_error(message)
                    # Unsuccessful addon payload: try RMCP unless addon-only.
                    json = None
                else:
                    self.last_backend = BACKEND_ADDON

            if json is None and self._should_try_rmcp():
                json = self.get_from_rmcp()
                if json is not None:
                    self.last_backend = BACKEND_RMCP
                else:
                    self.auth_failed = looks_like_auth_error(self._last_rmcp_error)
        elif self._should_try_rmcp():
            json = self.get_from_rmcp()
            if json is not None:
                self.last_backend = BACKEND_RMCP
            else:
                self.auth_failed = looks_like_auth_error(self._last_rmcp_error)

        if json is not None:
            info = IpmiDeviceInfo()
            info.device = json.get("device") if isinstance(json.get("device"), dict) else {}
            info.power_on = bool(json.get("power_on"))
            info.sensors = normalize_addon_sensor_groups(
                json.get("sensors"), sensor_types=SENSOR_TYPES
            )
            info.states = normalize_addon_mapping(json.get("states"))
            info.statuses = normalize_addon_mapping(json.get("statuses"))
            info.alias = self._alias
            self._device_info = info
            self.auth_failed = False
        else:
            self._device_info = None

        if info is not None:
            sensor_ids = iter_discovered_sensor_ids(info.sensors, info.states)
            # _known_sensors tracks sensor ids that already have entities. It
            # must only ever grow: entities are never removed at runtime, so a
            # sensor that drops out of a poll (host powered off, BMC returning
            # no readings) and later reappears must NOT be announced as new,
            # or the platform re-creates an entity whose unique_id already
            # exists ("Platform ipmi does not generate unique IDs").
            new_sensors = [
                sensor_id
                for sensor_id in sensor_ids
                if sensor_id not in self._known_sensors
            ]
            if new_sensors:
                dispatcher_send(
                    self.hass, IPMI_NEW_SENSOR_SIGNAL.format(self._entry_id)
                )

    def is_known_sensor(self, sensor_id: str) -> bool:
        """Return True if this sensor id already has an entity."""
        return sensor_id in self._known_sensors

    def add_known_sensor(self, sensor_id: str) -> None:
        """Remember that an entity was created for this sensor id."""
        self._known_sensors.add(sensor_id)

    def _chassis_command(self, addon_path: str, rmcp_command: int) -> None:
        """Run chassis control via addon when possible, else RMCP.

        Raises:
            IpmiChassisCommandError: When the command fails on all available backends.
        """
        _LOGGER.info(
            "Sending chassis command %s to %s (%s)",
            addon_path,
            self.name,
            self._host,
        )
        if self._should_try_addon() and self._run_addon_action(addon_path):
            _LOGGER.info("Chassis command %s succeeded via addon", addon_path)
            return
        if not self._should_try_rmcp():
            raise IpmiChassisCommandError(
                f"Chassis command {addon_path} failed and RMCP is disabled by "
                f"backend preference '{self._backend_preference}'"
            )
        self.run_rmcp_command(rmcp_command)
        _LOGGER.info("Chassis command %s succeeded via RMCP", addon_path)

    def power_on(self) -> None:
        """Power up the chassis."""
        self._chassis_command("power_on", pyipmi.chassis.CONTROL_POWER_UP)

    def power_off(self) -> None:
        """Hard power off the chassis."""
        self._chassis_command("power_off", pyipmi.chassis.CONTROL_POWER_DOWN)

    def power_cycle(self) -> None:
        """Power cycle the chassis."""
        self._chassis_command("power_cycle", pyipmi.chassis.CONTROL_POWER_CYCLE)

    def power_reset(self) -> None:
        """Hard reset the chassis."""
        self._chassis_command("power_reset", pyipmi.chassis.CONTROL_HARD_RESET)

    def soft_shutdown(self) -> None:
        """Request a soft shutdown."""
        self._chassis_command("soft_shutdown", pyipmi.chassis.CONTROL_SOFT_SHUTDOWN)

    def send_command(self, command: str, ignore_errors: bool) -> str:
        """Send a custom ipmitool-style command through the addon only."""
        cmd = command.replace("$host$", self._host or "")
        cmd = cmd.replace("$port$", str(self._port))
        cmd = cmd.replace("$username$", self._username or "")
        cmd = cmd.replace("$password$", self._password or "")

        # Pass the command in the request body/params (not baked into the path)
        # so POST keeps the ipmitool string out of the URL when supported.
        response = self.get_from_addon("command", extra={"params": cmd})

        if response is None:
            err = (
                "send_command requires the ipmi-server addon or standalone HTTP API; "
                f"addon unreachable or backend preference is "
                f"'{self._backend_preference}' (last backend={self.last_backend}). "
                f"Command not sent: {command}"
            )
            if ignore_errors:
                _LOGGER.error(err)
                return ""
            raise RuntimeError(err)

        if not addon_action_succeeded(response):
            err = "Error executing command: {}, Error: {}".format(
                command, response.get("output", response)
            )
            if ignore_errors:
                _LOGGER.error(err)
                return ""
            raise RuntimeError(err)

        return str(response.get("output", ""))

    # Backward-compatible aliases for any external callers / older code paths.
    getFromAddon = get_from_addon
    getFromRmcp = get_from_rmcp
    runRmcpCommand = run_rmcp_command
    generateId = staticmethod(generate_sensor_id)
