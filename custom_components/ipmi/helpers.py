from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant

from .const import DOMAIN, SERVERS

if TYPE_CHECKING:
    from . import IpmiServer

class IpmiData(TypedDict):
    """Typed description of impi data stored in `hass.data`."""

    servers: dict[str, IpmiServer]
    dispatchers: dict[str, list[CALLBACK_TYPE]]

def get_ipmi_data(hass: HomeAssistant) -> IpmiData:
    """Get typed data from hass.data."""
    return hass.data[DOMAIN]


def get_ipmi_server(hass: HomeAssistant, server_id: str) -> IpmiServer:
    """Get IPMI server from hass.data."""
    return get_ipmi_data(hass)[SERVERS][server_id]
