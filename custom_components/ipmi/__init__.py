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
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    CONF_ADDON_PORT,
    CONF_IPMI_SERVER_HOST,
    DOMAIN,
    PLATFORMS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_NEW_SENSOR_SIGNAL,
    IPMI_UPDATE_SENSOR_SIGNAL,
    USER_AVAILABLE_COMMANDS,
    INTEGRATION_SUPPORTED_COMMANDS,
    SERVERS,
    DISPATCHERS,
    IPMI_DEV_INFO_TO_DEV_INFO
)

from .helpers import IpmiData, get_ipmi_data
from .server import IpmiDeviceInfo, IpmiServer

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IPMI component."""
    hass_data = IpmiData(
        servers={},
        dispatchers={}
    )
    hass.data.setdefault(DOMAIN, hass_data)

    return True

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
    ipmi_server_host = config[CONF_IPMI_SERVER_HOST]
    addon_port = config[CONF_ADDON_PORT]
    
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    data = IpmiServer(hass, entry.entry_id, host, port, alias, username, password, ipmi_server_host, addon_port)
    coordinator = IpmiCoordinator(hass, scan_interval, data)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    deviceInfo = coordinator.data

    _LOGGER.debug("IPMI Sensors Available: %s", deviceInfo)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    # unique_id = alias + _unique_id_from_status(deviceInfo)
    # if unique_id is None:
    server_id = entry.entry_id

    hass_data = get_ipmi_data(hass)
    hass_data[SERVERS][entry.entry_id] = {
        COORDINATOR: coordinator,
        IPMI_DATA: data,
        IPMI_UNIQUE_ID: server_id,
        USER_AVAILABLE_COMMANDS: INTEGRATION_SUPPORTED_COMMANDS,
    }
    hass_data[DISPATCHERS].setdefault(server_id, [])

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, server_id)},
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
        hass_data = get_ipmi_data(hass)
        hass_data[SERVERS].pop(entry.entry_id)
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
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            await self.hass.async_add_executor_job(self.ipmiData.update)
            if not self.ipmiData.device_info:
                raise UpdateFailed("Error fetching IPMI state")
            
            return self.ipmiData.device_info