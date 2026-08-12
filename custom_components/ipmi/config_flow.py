"""Config flow for IPMI integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import exceptions
from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
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
from homeassistant.helpers import config_validation as cv, selector

from . import IpmiServer
from .const import (
    CONF_ADDON_INTERFACE,
    CONF_ADDON_PARAMS,
    CONF_ADDON_PORT,
    CONF_IGNORE_CHECKSUM_ERRORS,
    CONF_IPMI_SERVER_HOST,
    CONF_KG_KEY,
    CONF_PRIVILEGE_LEVEL,
    CONF_SENSOR_TYPES,
    DEFAULT_ADDON_PORT,
    DEFAULT_ALIAS,
    DEFAULT_HOST,
    DEFAULT_INTERFACE_TYPE,
    DEFAULT_IPMI_SERVER_HOST,
    DEFAULT_KG_KEY,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_PRIVILEGE_LEVEL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SENSOR_TYPES,
    DEFAULT_USERNAME,
    DOMAIN,
    PRIVILEGE_LEVELS,
    SENSOR_TYPES,
)
from .util import as_str_list, format_entry_unique_id, validate_kg_key

# Flow-only flag; never stored on the config entry.
CONF_ADVANCED = "advanced"

_PORT_SELECTOR = vol.All(
    selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1, max=65535, mode=selector.NumberSelectorMode.BOX
        ),
    ),
    vol.Coerce(int),
)

_INTERFACE_SELECTOR = vol.All(
    selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=["auto", "lanplus", "lan", "imb", "open"],
            multiple=False,
            mode="dropdown",
        ),
    ),
    vol.Coerce(str),
)

_PRIVILEGE_LEVEL_SELECTOR = vol.All(
    selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=PRIVILEGE_LEVELS, multiple=False, mode="dropdown"
        ),
    ),
    vol.Coerce(str),
)

_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)

_LOGGER = logging.getLogger(__name__)


def _validate_kg_key(value: str) -> str:
    """Validate the Kg key is valid hex and proper length."""
    try:
        return validate_kg_key(value)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err


def _basic_schema(
    discovery_info: zeroconf.ZeroconfServiceInfo | None,
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Schema for the essential connection settings."""
    defaults = defaults or {}
    schema: dict[Any, Any] = {}

    if not discovery_info:
        schema.update(
            {
                vol.Required(
                    CONF_ALIAS, default=defaults.get(CONF_ALIAS, DEFAULT_ALIAS)
                ): cv.string,
                vol.Required(
                    CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)
                ): cv.string,
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                ): _PORT_SELECTOR,
            }
        )
    else:
        schema[
            vol.Required(CONF_ALIAS, default=defaults.get(CONF_ALIAS, DEFAULT_ALIAS))
        ] = cv.string

    schema.update(
        {
            vol.Optional(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)
            ): cv.string,
            vol.Optional(
                CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, DEFAULT_PASSWORD)
            ): _PASSWORD_SELECTOR,
            vol.Optional(CONF_ADVANCED, default=False): cv.boolean,
        }
    )
    return vol.Schema(schema)


_SENSOR_TYPES_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=SENSOR_TYPES,
        multiple=True,
        mode="dropdown",
    )
)

_OPTION_KEYS = {CONF_SENSOR_TYPES}


def _advanced_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Schema for optional addon / auth / sensor-filter advanced settings."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Optional(
                CONF_PRIVILEGE_LEVEL,
                default=defaults.get(CONF_PRIVILEGE_LEVEL, DEFAULT_PRIVILEGE_LEVEL),
            ): _PRIVILEGE_LEVEL_SELECTOR,
            vol.Optional(
                CONF_KG_KEY, default=defaults.get(CONF_KG_KEY, DEFAULT_KG_KEY)
            ): cv.string,
            vol.Optional(
                CONF_IPMI_SERVER_HOST,
                default=defaults.get(CONF_IPMI_SERVER_HOST, DEFAULT_IPMI_SERVER_HOST),
            ): cv.string,
            vol.Optional(
                CONF_ADDON_PORT,
                default=str(defaults.get(CONF_ADDON_PORT, DEFAULT_ADDON_PORT)),
            ): cv.string,
            vol.Optional(
                CONF_ADDON_INTERFACE,
                default=defaults.get(CONF_ADDON_INTERFACE, DEFAULT_INTERFACE_TYPE),
            ): _INTERFACE_SELECTOR,
            vol.Optional(
                CONF_ADDON_PARAMS,
                default=defaults.get(CONF_ADDON_PARAMS) or "",
            ): cv.string,
            vol.Optional(
                CONF_IGNORE_CHECKSUM_ERRORS,
                default=defaults.get(CONF_IGNORE_CHECKSUM_ERRORS, False),
            ): cv.boolean,
            vol.Optional(
                CONF_SENSOR_TYPES,
                default=list(defaults.get(CONF_SENSOR_TYPES, DEFAULT_SENSOR_TYPES)),
            ): _SENSOR_TYPES_SELECTOR,
        }
    )


def _advanced_defaults() -> dict[str, Any]:
    """Default advanced values used when the advanced step is skipped."""
    return {
        CONF_KG_KEY: DEFAULT_KG_KEY,
        CONF_PRIVILEGE_LEVEL: DEFAULT_PRIVILEGE_LEVEL,
        CONF_IPMI_SERVER_HOST: DEFAULT_IPMI_SERVER_HOST,
        CONF_ADDON_PORT: str(DEFAULT_ADDON_PORT),
        CONF_ADDON_INTERFACE: DEFAULT_INTERFACE_TYPE,
        CONF_ADDON_PARAMS: None,
        CONF_IGNORE_CHECKSUM_ERRORS: False,
        CONF_SENSOR_TYPES: list(DEFAULT_SENSOR_TYPES),
    }


def _entry_data_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Config-entry data: connection fields only (no flow-only / options keys)."""
    return {
        key: value
        for key, value in config.items()
        if key != CONF_ADVANCED and key not in _OPTION_KEYS
    }


def _entry_options_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Sensor-filter options extracted from flow input."""
    return {
        CONF_SENSOR_TYPES: as_str_list(
            config.get(CONF_SENSOR_TYPES), DEFAULT_SENSOR_TYPES
        ),
    }


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    kg_key = _validate_kg_key(data.get(CONF_KG_KEY, ""))
    data[CONF_KG_KEY] = kg_key

    ipmi_data = IpmiServer(
        hass,
        None,
        {
            "host": data.get(CONF_HOST),
            "port": data.get(CONF_PORT),
            "alias": data.get(CONF_ALIAS),
            "username": data.get(CONF_USERNAME),
            "password": data.get(CONF_PASSWORD),
            "kg_key": data.get(CONF_KG_KEY),
            "privilege_level": data.get(CONF_PRIVILEGE_LEVEL),
            "ipmi_server_host": data.get(CONF_IPMI_SERVER_HOST),
            "addon_port": data.get(CONF_ADDON_PORT),
            "addon_interface": data.get(CONF_ADDON_INTERFACE),
            "addon_extra_params": data.get(CONF_ADDON_PARAMS),
            CONF_IGNORE_CHECKSUM_ERRORS: data.get(CONF_IGNORE_CHECKSUM_ERRORS, False),
        },
    )
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

    VERSION = 2
    MINOR_VERSION = 4

    def __init__(self) -> None:
        """Initialize the ipmi config flow."""
        self.ipmi_config: dict[str, Any] = {}
        self.discovery_info: zeroconf.ZeroconfServiceInfo | None = None
        self._show_advanced = False
        self.title: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Prepare configuration for a discovered ipmi device."""
        self.discovery_info = discovery_info
        # Alias is the unique_id; it is chosen in the user step.
        await self._async_handle_discovery_without_unique_id()
        self.context["title_placeholders"] = {
            CONF_PORT: discovery_info.port or DEFAULT_PORT,
            CONF_HOST: discovery_info.host,
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect essential BMC connection settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self.discovery_info:
                user_input = {
                    **user_input,
                    CONF_HOST: self.discovery_info.host,
                    CONF_PORT: self.discovery_info.port or DEFAULT_PORT,
                }

            advanced = bool(user_input.pop(CONF_ADVANCED, False))
            self.ipmi_config.update(user_input)
            self._show_advanced = advanced

            if advanced:
                return await self.async_step_advanced()

            self._merge_advanced_defaults()
            return await self._async_create_or_show_errors(errors_step="user")

        return self.async_show_form(
            step_id="user",
            data_schema=_basic_schema(self.discovery_info, self.ipmi_config),
            errors=errors,
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect optional addon and authentication settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Empty optional text fields should clear rather than keep stale values.
            if CONF_ADDON_PARAMS in user_input and not user_input[CONF_ADDON_PARAMS]:
                user_input[CONF_ADDON_PARAMS] = None
            self.ipmi_config.update(user_input)
            return await self._async_create_or_show_errors(errors_step="advanced")

        defaults = {**_advanced_defaults(), **self.ipmi_config}
        return self.async_show_form(
            step_id="advanced",
            data_schema=_advanced_schema(defaults),
            errors=errors,
        )

    def _merge_advanced_defaults(self) -> None:
        """Apply advanced defaults for keys the user did not configure."""
        for key, value in _advanced_defaults().items():
            self.ipmi_config.setdefault(key, value)

    async def _async_create_or_show_errors(self, errors_step: str) -> FlowResult:
        """Validate connection and create the entry, or re-show the given step."""
        _, errors = await self._async_validate_or_error(self.ipmi_config)
        if errors:
            if errors_step == "advanced":
                defaults = {**_advanced_defaults(), **self.ipmi_config}
                return self.async_show_form(
                    step_id="advanced",
                    data_schema=_advanced_schema(defaults),
                    errors=errors,
                )

            return self.async_show_form(
                step_id="user",
                data_schema=_basic_schema(self.discovery_info, self.ipmi_config),
                errors=errors,
            )

        if self._alias_already_configured(self.ipmi_config):
            return self.async_abort(reason="already_configured")

        # Never persist the flow-only advanced checkbox or options keys in data.
        data = _entry_data_from_config(self.ipmi_config)
        options = _entry_options_from_config(self.ipmi_config)
        await self.async_set_unique_id(format_entry_unique_id(data[CONF_ALIAS]))
        self._abort_if_unique_id_configured()
        title = _format_host_port_alias(data)
        return self.async_create_entry(title=title, data=data, options=options)

    def _alias_already_configured(
        self,
        user_input: dict[str, Any],
        exclude_entry_id: str | None = None,
    ) -> bool:
        """Return True if another entry already uses this alias."""
        alias = format_entry_unique_id(user_input[CONF_ALIAS])
        for entry in self._async_current_entries():
            if entry.entry_id == exclude_entry_id or CONF_ALIAS not in entry.data:
                continue
            if format_entry_unique_id(entry.data[CONF_ALIAS]) == alias:
                return True
        return False

    async def _async_validate_or_error(
        self, config: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        errors: dict[str, str] = {}
        info: dict[str, Any] = {}
        try:
            info = await validate_input(self.hass, config)
        except CannotConnect:
            errors[CONF_BASE] = "cannot_connect"
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception: %s", err)
            errors[CONF_BASE] = "unknown"
        return info, errors

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start reconfiguration with essential settings."""
        entry = (
            self._get_reconfigure_entry()
            if hasattr(self, "_get_reconfigure_entry")
            else self.hass.config_entries.async_get_entry(self.context["entry_id"])
        )
        assert entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            advanced = bool(user_input.pop(CONF_ADVANCED, False))
            self.ipmi_config = {**entry.data, **user_input}
            self._show_advanced = advanced
            if advanced:
                return await self.async_step_reconfigure_advanced()
            self._merge_advanced_defaults()
            return await self._async_finish_reconfigure(errors_step="reconfigure")

        self.ipmi_config = dict(entry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_basic_schema(None, self.ipmi_config),
            errors=errors,
        )

    async def async_step_reconfigure_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Optional advanced settings during reconfigure."""
        entry = (
            self._get_reconfigure_entry()
            if hasattr(self, "_get_reconfigure_entry")
            else self.hass.config_entries.async_get_entry(self.context["entry_id"])
        )
        assert entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_ADDON_PARAMS in user_input and not user_input[CONF_ADDON_PARAMS]:
                user_input[CONF_ADDON_PARAMS] = None
            self.ipmi_config.update(user_input)
            return await self._async_finish_reconfigure(
                errors_step="reconfigure_advanced"
            )

        defaults = {
            **_advanced_defaults(),
            **entry.options,
            **self.ipmi_config,
        }
        return self.async_show_form(
            step_id="reconfigure_advanced",
            data_schema=_advanced_schema(defaults),
            errors=errors,
        )

    async def _async_finish_reconfigure(self, errors_step: str) -> FlowResult:
        """Validate and apply reconfigure changes."""
        entry = self._get_reconfigure_entry() if hasattr(
            self, "_get_reconfigure_entry"
        ) else self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        _, errors = await self._async_validate_or_error(self.ipmi_config)
        if errors:
            if errors_step == "reconfigure_advanced":
                defaults = {
                    **_advanced_defaults(),
                    **entry.options,
                    **self.ipmi_config,
                }
                return self.async_show_form(
                    step_id="reconfigure_advanced",
                    data_schema=_advanced_schema(defaults),
                    errors=errors,
                )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_basic_schema(None, self.ipmi_config),
                errors=errors,
            )

        data = _entry_data_from_config(self.ipmi_config)
        if self._alias_already_configured(data, exclude_entry_id=entry.entry_id):
            return self.async_abort(reason="already_configured")

        unique_id = format_entry_unique_id(data[CONF_ALIAS])
        for other in self._async_current_entries():
            if other.entry_id != entry.entry_id and other.unique_id == unique_id:
                return self.async_abort(reason="already_configured")

        title = _format_host_port_alias(data)
        update_kwargs: dict[str, Any] = {
            "data": data,
            "title": title,
            "unique_id": unique_id,
            "reason": "reconfigure_successful",
        }
        # Sensor filters live in options; only rewrite them when advanced was shown.
        if self._show_advanced:
            update_kwargs["options"] = {
                **entry.options,
                **_entry_options_from_config(self.ipmi_config),
            }
        return self.async_update_reload_and_abort(entry, **update_kwargs)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Perform reauthentication when credentials fail."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Prompt for updated username/password."""
        entry = self._get_reauth_entry() if hasattr(
            self, "_get_reauth_entry"
        ) else self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = {**entry.data, **user_input}
            _, errors = await self._async_validate_or_error(new_data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                    reason="reauth_successful",
                )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_USERNAME,
                    default=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
                ): cv.string,
                vol.Optional(
                    CONF_PASSWORD,
                    default=entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
                ): _PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host": str(entry.data.get(CONF_HOST, "")),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handle a option flow for ipmi."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            # Normalize multi-selects in case a single choice arrived as a string.
            if CONF_SENSOR_TYPES in user_input:
                user_input[CONF_SENSOR_TYPES] = as_str_list(
                    user_input[CONF_SENSOR_TYPES], DEFAULT_SENSOR_TYPES
                )
            # Drop removed option if still present from older versions.
            user_input.pop("diagnostic_sensor_types", None)
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        sensor_types = as_str_list(
            options.get(CONF_SENSOR_TYPES), DEFAULT_SENSOR_TYPES
        )

        base_schema = {
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Clamp(min=10, max=300)
            ),
            vol.Optional(
                CONF_SENSOR_TYPES, default=list(sensor_types)
            ): _SENSOR_TYPES_SELECTOR,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(base_schema))


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
