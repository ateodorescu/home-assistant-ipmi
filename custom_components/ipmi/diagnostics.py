"""Diagnostics support for IPMI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_KG_KEY, COORDINATOR, DEFAULT_BACKEND_PREFERENCE, IPMI_DATA
from .helpers import get_ipmi_server

TO_REDACT = {CONF_PASSWORD, CONF_KG_KEY, "password", "kg_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    ipmiserver = get_ipmi_server(hass, entry.entry_id)
    data = ipmiserver[IPMI_DATA]
    coordinator = ipmiserver[COORDINATOR]
    device_info = data.device_info

    sensor_keys: dict[str, list[str]] = {}
    if device_info and device_info.sensors:
        sensor_keys = {
            sensor_type: sorted(sensors.keys())
            for sensor_type, sensors in device_info.sensors.items()
            if isinstance(sensors, dict)
        }

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "connection": {
            "backend": data.last_backend,
            "backend_preference": getattr(
                data, "_backend_preference", DEFAULT_BACKEND_PREFERENCE
            ),
            "sensor_types_poll": list(getattr(data, "_sensor_types", [])),
            "power_only_poll": data._power_only_poll(),
            "auth_failed": data.auth_failed,
            "addon_url": data._addon_url,
            "addon_use_post": data._addon_use_post,
            "addon_version": data.addon_version,
            "addon_api_version": getattr(data, "_addon_api_version", None),
            "addon_capabilities": sorted(data.addon_capabilities),
            "host": data._host,
            "port": data._port,
            "last_rmcp_error": data._last_rmcp_error,
        },
        "compatibility": {
            # Intentionally entry-id based; remove/re-add creates new entity unique IDs.
            "entity_unique_id_scheme": "{entry_id}_{alias}_{key}",
            "config_entry_unique_id": "alias (lowercase)",
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "device": device_info.device if device_info else None,
        "power_on": device_info.power_on if device_info else None,
        "sensors": sensor_keys,
        "state_keys": sorted(device_info.states.keys())
        if device_info and device_info.states
        else [],
    }
