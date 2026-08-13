"""Pure helpers used by the IPMI integration (no Home Assistant imports)."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

_AUTH_ERROR_MARKERS = (
    "auth",
    "password",
    "privilege",
    "unauthorized",
    "not authorized",
    "access denied",
    "login",
    "credentials",
    "invalid user",
)

# IPMI sensor type codes (Table 42-3) → integration sensor groups.
_RMCP_SENSOR_TYPE_TO_CATEGORY: dict[int, str] = {
    0x01: "temperature",
    0x02: "voltage",
    0x03: "current",
    0x04: "fan",
}

# IPMI unit type codes (Table 43-15) on full/compact records.
_RMCP_UNIT_TO_CATEGORY: dict[int, str] = {
    0x05: "current",  # Amps
    0x06: "power",  # Watts
    0x15: "time",  # seconds
}


def format_entry_unique_id(alias: str) -> str:
    """Stable config-entry unique_id from the user-chosen server alias."""
    return str(alias).strip().lower()


def generate_sensor_id(name: str) -> str:
    """Normalize an SDR / addon sensor name into an entity key fragment."""
    sensor_id = re.sub("[^A-Za-z0-9 _]+", "", name)
    return sensor_id.replace(" ", "_").lower()


def energy_sensor_key(power_sensor_key: str, suffix: str = "_energy") -> str:
    """Return the entity key for a power sensor's energy counterpart."""
    return f"{power_sensor_key}{suffix}"


def integrate_power_left_riemann(
    *,
    previous_power_w: float | None,
    elapsed_seconds: float,
    accumulated_kwh: float,
) -> float:
    """Integrate power (W) over elapsed time using a left Riemann sum."""
    if previous_power_w is None or elapsed_seconds <= 0:
        return accumulated_kwh
    return accumulated_kwh + (previous_power_w * elapsed_seconds / 3600.0 / 1000.0)


def energy_sensors_enabled(
    enabled_types: Any,
    create_energy_sensors: bool,
    *,
    default_types: list[str] | None = None,
) -> bool:
    """Return True when companion energy entities should be active."""
    types = set(as_str_list(enabled_types, default_types))
    return "power" in types and create_energy_sensors


def normalize_addon_mapping(value: Any) -> dict[str, Any]:
    """Return a dict; PHP encodes empty associative arrays as JSON lists."""
    if isinstance(value, dict):
        return value
    return {}


def normalize_addon_sensor_groups(
    value: Any,
    *,
    sensor_types: list[str],
) -> dict[str, dict[str, str]]:
    """Normalize addon sensor buckets; empty PHP arrays decode as JSON lists."""
    raw = value if isinstance(value, dict) else {}
    groups: dict[str, dict[str, str]] = {}
    for sensor_type in sensor_types:
        group = raw.get(sensor_type)
        if isinstance(group, dict):
            groups[sensor_type] = {str(k): str(v) for k, v in group.items()}
        else:
            groups[sensor_type] = {}
    return groups


def iter_discovered_sensor_ids(
    sensors: dict[str, Any],
    states: dict[str, Any],
) -> set[str]:
    """Return all sensor keys from SDR metadata and/or live readings."""
    ids: set[str] = set()
    if isinstance(states, dict):
        ids.update(states.keys())
    if isinstance(sensors, dict):
        for group in sensors.values():
            if isinstance(group, dict):
                ids.update(group.keys())
    return ids


def effective_sensor_types(
    config: Mapping[str, Any],
    *,
    default_types: list[str] | None = None,
) -> list[str]:
    """Return sensor types for polling and entity filters (empty list = power only)."""
    if config.get("minimal_ipmi"):
        return []
    if "sensor_types" not in config:
        return list(default_types or [])
    return as_str_list(config["sensor_types"], default_types)


def power_only_poll(sensor_types: list[str]) -> bool:
    """Return True when no dynamic sensor types are requested."""
    return not sensor_types


def update_addon_capabilities(
    cached: set[str] | None,
    response: Mapping[str, Any],
) -> set[str]:
    """Merge capability names from an addon JSON payload."""
    capabilities = set(cached or ())
    raw = response.get("capabilities")
    if isinstance(raw, list):
        capabilities.update(str(item) for item in raw if item)
    elif isinstance(raw, str) and raw:
        capabilities.add(raw)
    return capabilities


def addon_has_capability(capabilities: set[str], name: str) -> bool:
    """Return True when the addon reported a capability."""
    return name in capabilities


def normalize_options(config: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize options; legacy minimal_ipmi maps to an empty sensor_types list."""
    normalized = dict(config)
    if normalized.get("minimal_ipmi"):
        normalized["sensor_types"] = []
        normalized["create_energy_sensors"] = False
        normalized["ignore_checksum_errors"] = False
    return normalized


def normalize_minimal_options(config: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for ``normalize_options``."""
    return normalize_options(config)


def as_str_list(value: Any, default: list[str] | None = None) -> list[str]:
    """Normalize multi-select option values to a list of strings.

    Selectors may return a bare string when only one option is chosen;
    ``set("temperature")`` would then split into characters and break matching.
    """
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        return [value] if value else list(default or [])
    return [str(item) for item in value]


def redact_connection_secrets(
    message: str,
    password: str | None = None,
    kg_key: str | None = None,
) -> str:
    """Remove password / kg key substrings from log-facing error text."""
    redacted = message
    if password:
        redacted = redacted.replace(str(password), "***")
    if kg_key:
        redacted = redacted.replace(str(kg_key), "***")
    return redacted


def looks_like_auth_error(message: str | None) -> bool:
    """Return True if an error message likely indicates bad credentials."""
    if not message:
        return False
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def validate_kg_key(value: str | None) -> str:
    """Validate and normalize a Kg key; return empty string when unset.

    Raises:
        ValueError: if the value is present but not valid hex / length.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if not value.strip():
        return ""
    value = value.strip()
    if len(value) % 2 != 0:
        raise ValueError(
            "Kg key must have an even number of hexadecimal characters (valid octets)"
        )
    if len(value) > 40:
        raise ValueError(
            "Kg key must be at most 40 hexadecimal characters (20 bytes)"
        )
    try:
        int(value, 16)
    except ValueError as err:
        raise ValueError(
            "Kg key must contain only hexadecimal characters (0-9, A-F)"
        ) from err
    return value.upper()


def categorize_rmcp_sensor(
    sensor_type_code: int | None,
    units_2: int | None,
) -> str | None:
    """Map RMCP SDR type/units to a sensor group name, or None if unsupported."""
    if sensor_type_code is not None:
        category = _RMCP_SENSOR_TYPE_TO_CATEGORY.get(sensor_type_code)
        if category is not None:
            return category
    if units_2 is not None:
        return _RMCP_UNIT_TO_CATEGORY.get(units_2)
    return None


def addon_action_succeeded(response: dict[str, Any] | None) -> bool:
    """Return True when an addon HTTP JSON payload indicates success."""
    return bool(response) and bool(response.get("success"))


class IpmiChassisCommandError(RuntimeError):
    """Raised when a chassis power command fails on all available backends."""
