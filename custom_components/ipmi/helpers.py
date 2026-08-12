from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, TypedDict, cast

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, IPMI_DEV_INFO_TO_DEV_INFO, SERVERS

if TYPE_CHECKING:
    from .server import IpmiServer


class IpmiData(TypedDict):
    """Typed description of ipmi data stored in `hass.data`."""

    servers: dict[str, Any]
    dispatchers: dict[str, list[CALLBACK_TYPE]]


def get_ipmi_data(hass: HomeAssistant) -> IpmiData:
    """Get typed data from hass.data."""
    return hass.data[DOMAIN]


def get_ipmi_server(hass: HomeAssistant, server_id: str) -> dict[str, Any]:
    """Get IPMI server runtime dict from hass.data."""
    return get_ipmi_data(hass)[SERVERS][server_id]


def device_info_from_ipmi_server(data: IpmiServer, unique_id: str) -> DeviceInfo:
    """Build DeviceInfo for entities attached to an IPMI server."""
    device_name = data.name.title()
    info = DeviceInfo(
        identifiers={(DOMAIN, unique_id)},
        name=device_name,
    )
    if data.device_info and data.device_info.device:
        ipmi_dev_infos = asdict(data.device_info)["device"]
        info.update(
            cast(
                DeviceInfo,
                {
                    info_key: ipmi_dev_infos[ipmi_key]
                    for ipmi_key, info_key in IPMI_DEV_INFO_TO_DEV_INFO.items()
                    if ipmi_dev_infos.get(ipmi_key) is not None
                },
            )
        )
    return info
