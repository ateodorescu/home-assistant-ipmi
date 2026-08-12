"""Pure helpers used by the IPMI integration (no Home Assistant imports)."""

from __future__ import annotations

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
