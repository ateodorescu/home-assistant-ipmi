"""The IPMI custom component."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

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
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ADDON_INTERFACE,
    CONF_ADDON_PARAMS,
    CONF_ADDON_PORT,
    CONF_BACKEND_PREFERENCE,
    CONF_IGNORE_CHECKSUM_ERRORS,
    CONF_IPMI_SERVER_HOST,
    CONF_KG_KEY,
    CONF_PRIVILEGE_LEVEL,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_MINIMAL_IPMI,
    CONF_POWER_OFF_DELAY,
    CONF_SENSOR_TYPES,
    DEFAULT_MINIMAL_IPMI,
    DEFAULT_POWER_OFF_DELAY,
    COORDINATOR,
    DEFAULT_BACKEND_PREFERENCE,
    DEFAULT_KG_KEY,
    DEFAULT_PRIVILEGE_LEVEL,
    DEFAULT_CREATE_ENERGY_SENSORS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SENSOR_TYPES,
    DEFAULT_TIMEOUT,
    DISPATCHERS,
    DOMAIN,
    INTEGRATION_SUPPORTED_COMMANDS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    PLATFORMS,
    SERVERS,
    SERVICE_SEND_COMMAND,
    USER_AVAILABLE_COMMANDS,
)
from .helpers import IpmiData, get_ipmi_data, get_ipmi_server
from .server import IpmiDeviceInfo, IpmiServer
from .util import as_str_list, effective_sensor_types, format_entry_unique_id, normalize_options

_LOGGER = logging.getLogger(__name__)


def _ensure_entry_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Keep config-entry unique_id aligned with alias (entity IDs unchanged)."""
    alias = entry.data.get(CONF_ALIAS)
    if not alias:
        return

    unique_id = format_entry_unique_id(alias)
    if entry.unique_id == unique_id:
        return

    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry.entry_id and other.unique_id == unique_id:
            _LOGGER.warning(
                "Skipping unique_id %s for entry %s; already used by %s",
                unique_id,
                entry.entry_id,
                other.entry_id,
            )
            return

    hass.config_entries.async_update_entry(entry, unique_id=unique_id)


def _normalize_options(options: dict) -> dict:
    """Apply additive defaults without changing prior behavior."""
    new_options = dict(options)
    new_options.pop("diagnostic_sensor_types", None)
    if CONF_SENSOR_TYPES not in new_options:
        new_options[CONF_SENSOR_TYPES] = list(DEFAULT_SENSOR_TYPES)
    else:
        new_options[CONF_SENSOR_TYPES] = as_str_list(
            new_options[CONF_SENSOR_TYPES], DEFAULT_SENSOR_TYPES
        )
    if CONF_BACKEND_PREFERENCE not in new_options:
        # auto = historical addon-first then RMCP behavior
        new_options[CONF_BACKEND_PREFERENCE] = DEFAULT_BACKEND_PREFERENCE
    if CONF_CREATE_ENERGY_SENSORS not in new_options:
        new_options[CONF_CREATE_ENERGY_SENSORS] = DEFAULT_CREATE_ENERGY_SENSORS
    if CONF_POWER_OFF_DELAY not in new_options:
        new_options[CONF_POWER_OFF_DELAY] = DEFAULT_POWER_OFF_DELAY
    if CONF_MINIMAL_IPMI not in new_options:
        new_options[CONF_MINIMAL_IPMI] = DEFAULT_MINIMAL_IPMI
    return normalize_options(new_options)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IPMI component."""
    hass.data.setdefault(DOMAIN, IpmiData(servers={}, dispatchers={}))

    async def handle_send_command(call: ServiceCall) -> ServiceResponse:
        """Handle the service call."""
        server = get_ipmi_server(hass, call.data.get("server"))
        message = await hass.async_add_executor_job(
            server[IPMI_DATA].send_command,
            call.data.get("command"),
            call.data.get("ignore_errors", False),
        )

        return {"message": message}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPMI from a config entry."""
    hass.data.setdefault(DOMAIN, IpmiData(servers={}, dispatchers={}))

    _ensure_entry_unique_id(hass, entry)

    # strip out the stale options CONF_RESOURCES,
    # maintain the entry in data in case of version rollback
    new_options = _normalize_options(dict(entry.options))
    update_kwargs: dict = {}
    if CONF_RESOURCES in entry.options:
        update_kwargs["data"] = {
            **entry.data,
            CONF_RESOURCES: entry.options[CONF_RESOURCES],
        }
        new_options.pop(CONF_RESOURCES, None)

    if update_kwargs or new_options != dict(entry.options):
        update_kwargs["options"] = new_options
        hass.config_entries.async_update_entry(entry, **update_kwargs)

    config = entry.data
    options = entry.options

    # keep backward compatibility
    ipmi_server_host = config.get(CONF_IPMI_SERVER_HOST)

    if ipmi_server_host is None:
        ipmi_server_host = "http://localhost"

    scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    backend_preference = options.get(
        CONF_BACKEND_PREFERENCE, DEFAULT_BACKEND_PREFERENCE
    )
    sensor_types = effective_sensor_types(options, default_types=DEFAULT_SENSOR_TYPES)

    data = IpmiServer(
        hass,
        entry.entry_id,
        {
            "host": config.get(CONF_HOST),
            "port": config.get(CONF_PORT),
            "alias": config.get(CONF_ALIAS),
            "username": config.get(CONF_USERNAME),
            "password": config.get(CONF_PASSWORD),
            "kg_key": config.get(CONF_KG_KEY, DEFAULT_KG_KEY),
            "privilege_level": config.get(
                CONF_PRIVILEGE_LEVEL, DEFAULT_PRIVILEGE_LEVEL
            ),
            "ipmi_server_host": ipmi_server_host,
            "addon_port": config.get(CONF_ADDON_PORT),
            "addon_interface": config.get(CONF_ADDON_INTERFACE),
            "addon_extra_params": config.get(CONF_ADDON_PARAMS),
            CONF_IGNORE_CHECKSUM_ERRORS: config.get(CONF_IGNORE_CHECKSUM_ERRORS, False),
            "backend_preference": backend_preference,
            CONF_SENSOR_TYPES: sensor_types,
            CONF_MINIMAL_IPMI: options.get(CONF_MINIMAL_IPMI, DEFAULT_MINIMAL_IPMI),
        },
    )
    coordinator = IpmiCoordinator(hass, scan_interval, data)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    deviceInfo = coordinator.data

    _LOGGER.debug("IPMI Sensors Available: %s", deviceInfo)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    server_id = entry.entry_id

    hass_data = get_ipmi_data(hass)
    hass_data[SERVERS][server_id] = {
        COORDINATOR: coordinator,
        IPMI_DATA: data,
        IPMI_UNIQUE_ID: server_id.lower(),
        USER_AVAILABLE_COMMANDS: INTEGRATION_SUPPORTED_COMMANDS,
    }
    hass_data[DISPATCHERS].setdefault(server_id, [])

    device_registry = dr.async_get(hass)
    device = deviceInfo.device if deviceInfo else {}
    device_registry.async_get_or_create(
        config_entry_id=server_id,
        identifiers={(DOMAIN, server_id.lower())},
        name=data.name.title(),
        manufacturer=device.get("manufacturer_name"),
        model=device.get("product_name"),
        sw_version=device.get("firmware_revision"),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass_data = get_ipmi_data(hass)
        for unsub in hass_data[DISPATCHERS].pop(entry.entry_id, []):
            unsub()
        server = hass_data[SERVERS].pop(entry.entry_id, None)
        if server and IPMI_DATA in server:
            await hass.async_add_executor_job(server[IPMI_DATA].close)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug(
        "Migrating from version %s.%s", config_entry.version, config_entry.minor_version
    )

    if config_entry.version > 2:
        # This means the user has downgraded from a future version
        return True

    if config_entry.version == 1:
        if config_entry.minor_version == 1:
            new = {**config_entry.data}
            new[CONF_ADDON_INTERFACE] = "auto"
            new[CONF_ADDON_PARAMS] = None
            hass.config_entries.async_update_entry(
                config_entry, data=new, minor_version=3, version=1
            )

    # Migrate to version 2.2 - add kg_key and privilege_level
    if config_entry.version < 2 or (
        config_entry.version == 2 and config_entry.minor_version < 2
    ):
        new = {**config_entry.data}
        if CONF_KG_KEY not in new:
            new[CONF_KG_KEY] = DEFAULT_KG_KEY
        if CONF_PRIVILEGE_LEVEL not in new:
            new[CONF_PRIVILEGE_LEVEL] = DEFAULT_PRIVILEGE_LEVEL
        hass.config_entries.async_update_entry(
            config_entry, data=new, minor_version=2, version=2
        )

    # Migrate to version 2.3 - config entry unique_id (later superseded by alias)
    if config_entry.version == 2 and config_entry.minor_version < 3:
        hass.config_entries.async_update_entry(
            config_entry, minor_version=3, version=2
        )

    # Migrate to version 2.4 - config entry unique_id is the alias (not host:port)
    if config_entry.version == 2 and config_entry.minor_version < 4:
        unique_id = config_entry.unique_id
        alias = config_entry.data.get(CONF_ALIAS)
        if alias:
            candidate = format_entry_unique_id(alias)
            conflict = any(
                other.entry_id != config_entry.entry_id
                and other.unique_id == candidate
                for other in hass.config_entries.async_entries(DOMAIN)
            )
            if not conflict:
                unique_id = candidate
        hass.config_entries.async_update_entry(
            config_entry, unique_id=unique_id, minor_version=4, version=2
        )

    # Migrate to version 2.5 - backend_preference option (default auto = prior behavior)
    if config_entry.version == 2 and config_entry.minor_version < 5:
        new_options = _normalize_options(dict(config_entry.options))
        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=5, version=2
        )

    # Migrate to version 2.6 - optional energy sensors option (additive default)
    if config_entry.version == 2 and config_entry.minor_version < 6:
        new_options = _normalize_options(dict(config_entry.options))
        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=6, version=2
        )

    # Migrate to version 2.7 - enable energy sensors by default
    if config_entry.version == 2 and config_entry.minor_version < 7:
        new_options = _normalize_options(dict(config_entry.options))
        new_options[CONF_CREATE_ENERGY_SENSORS] = DEFAULT_CREATE_ENERGY_SENSORS
        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=7, version=2
        )

    # Migrate to version 2.8 - minimal IPMI option (additive default)
    if config_entry.version == 2 and config_entry.minor_version < 8:
        new_options = _normalize_options(dict(config_entry.options))
        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=8, version=2
        )

    # Migrate to version 2.9 - legacy minimal_ipmi becomes empty sensor_types
    if config_entry.version == 2 and config_entry.minor_version < 9:
        new_options = _normalize_options(dict(config_entry.options))
        if new_options.get(CONF_MINIMAL_IPMI):
            new_options[CONF_SENSOR_TYPES] = []
            new_options[CONF_CREATE_ENERGY_SENSORS] = False
        new_options[CONF_MINIMAL_IPMI] = False
        hass.config_entries.async_update_entry(
            config_entry, options=new_options, minor_version=9, version=2
        )

    _LOGGER.debug(
        "Migration to version %s.%s successful",
        config_entry.version,
        config_entry.minor_version,
    )

    return True


class IpmiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, scan_interval, ipmiData):
        """Initialize IPMI coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="IPMI coordinator",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=scan_interval),
        )
        self.ipmiData = ipmiData

    async def _async_update_data(self) -> IpmiDeviceInfo:
        """Fetch data from IPMI server."""
        async with asyncio.timeout(DEFAULT_TIMEOUT):
            await self.hass.async_add_executor_job(self.ipmiData.update)
            if not self.ipmiData.device_info:
                if self.ipmiData.auth_failed and self.ipmiData._entry_id:
                    entry = self.hass.config_entries.async_get_entry(
                        self.ipmiData._entry_id
                    )
                    if entry is not None:
                        entry.async_start_reauth(self.hass)
                raise UpdateFailed("Error fetching IPMI state")

            return self.ipmiData.device_info
