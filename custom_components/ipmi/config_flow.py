"""Config flow for IPMI integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import exceptions
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.const import (
    CONF_ALIAS,
    CONF_BASE,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from . import IpmiServer
from .const import (
    DEFAULT_HOST, 
    DEFAULT_ALIAS, 
    DEFAULT_PORT, 
    DEFAULT_USERNAME, 
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    CONF_ADDON_PORT,
    DEFAULT_ADDON_PORT,
    CONF_IPMI_SERVER_HOST,
    DEFAULT_IPMI_SERVER_HOST,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

def _base_schema(discovery_info: zeroconf.ZeroconfServiceInfo | None) -> vol.Schema:
    """Generate base schema."""
    base_schema = {}
    if not discovery_info:
        base_schema.update(
            {
                vol.Required(CONF_ALIAS, default=DEFAULT_ALIAS): cv.string,
                vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
                vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string, 
                vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
            }
        )

    base_schema.update(
        {
            vol.Optional(CONF_IPMI_SERVER_HOST, default=DEFAULT_IPMI_SERVER_HOST): cv.string,
            vol.Optional(CONF_ADDON_PORT, default=DEFAULT_ADDON_PORT): cv.string,
        }
    )

    return vol.Schema(base_schema)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from _base_schema with values provided by the user.
    """

    host = data[CONF_HOST]
    port = data[CONF_PORT]
    alias = data[CONF_ALIAS]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    ipmi_server_host = data[CONF_IPMI_SERVER_HOST]
    addon_port = data[CONF_ADDON_PORT]

    ipmi_data = IpmiServer(hass, None, host, port, alias, username, password, ipmi_server_host, addon_port)
    await hass.async_add_executor_job(ipmi_data.update)

    if not (device_info := ipmi_data._device_info):
        raise CannotConnect

    return {"device_info": device_info}

def _format_host_port_alias(user_input: Mapping[str, Any]) -> str:
    """Format a host, port, and alias so it can be used for comparison or display."""
    host = user_input[CONF_HOST]
    port = user_input[CONF_PORT]
    alias = user_input[CONF_ALIAS]
    return f"{alias}@{host}:{port}"

class IpmiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPMI."""

    VERSION = 1.1

    def __init__(self) -> None:
        """Initialize the ipmi config flow."""
        self.ipmi_config: dict[str, Any] = {}
        self.discovery_info: zeroconf.ZeroconfServiceInfo | None = None
        self.title: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Prepare configuration for a discovered ipmi device."""
        self.discovery_info = discovery_info
        await self._async_handle_discovery_without_unique_id()
        self.context["title_placeholders"] = {
            CONF_PORT: discovery_info.port or DEFAULT_PORT,
            CONF_HOST: discovery_info.host,
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user input."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self.discovery_info:
                user_input.update(
                    {
                        CONF_HOST: self.discovery_info.host,
                        CONF_PORT: self.discovery_info.port or DEFAULT_PORT,
                    }
                )
            info, errors = await self._async_validate_or_error(user_input)

            if not errors:
                self.ipmi_config.update(user_input)
                if self._host_port_alias_already_configured(self.ipmi_config):
                    return self.async_abort(reason="already_configured")
                title = _format_host_port_alias(self.ipmi_config)
                return self.async_create_entry(title=title, data=self.ipmi_config)

        return self.async_show_form(
            step_id="user", data_schema=_base_schema(self.discovery_info), errors=errors
        )

    def _host_port_alias_already_configured(self, user_input: dict[str, Any]) -> bool:
        """See if we already have an ipmi entry matching user input configured."""
        existing_host_port_aliases = {
            _format_host_port_alias(entry.data)
            for entry in self._async_current_entries()
            if CONF_HOST in entry.data
        }
        return _format_host_port_alias(user_input) in existing_host_port_aliases

    async def _async_validate_or_error(
        self, config: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        errors = {}
        info = {}
        try:
            info = await validate_input(self.hass, config)
        except CannotConnect:
            errors[CONF_BASE] = "cannot_connect"
        except (Exception) as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception: %s", err)
            errors[CONF_BASE] = "unknown"
        return info, errors

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(OptionsFlow):
    """Handle a option flow for ipmi."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        base_schema = {
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Clamp(min=10, max=300)
            )
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(base_schema))

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""