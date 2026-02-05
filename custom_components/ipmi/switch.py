from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any, cast

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import IpmiServer
from .helpers import get_ipmi_server
from .const import (
    COORDINATOR,
    DOMAIN,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_DEV_INFO_TO_DEV_INFO
)

ENTITY_ID_FORMAT = DOMAIN + ".{}"

_LOGGER = logging.getLogger(__name__)

def _get_ipmi_device_info(data: IpmiServer) -> DeviceInfo:
    """Return a DeviceInfo object filled with IPMI device info."""
    ipmi_dev_infos = asdict(data.device_info)["device"]
    ipmi_infos = {
        info_key: ipmi_dev_infos[ipmi_key]
        for ipmi_key, info_key in IPMI_DEV_INFO_TO_DEV_INFO.items()
        if ipmi_dev_infos[ipmi_key] is not None
    }

    return cast(DeviceInfo, ipmi_infos)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for device."""
    ipmiserver = get_ipmi_server(hass, config_entry.entry_id)
    coordinator = ipmiserver[COORDINATOR]
    data = ipmiserver[IPMI_DATA]
    unique_id = ipmiserver[IPMI_UNIQUE_ID]
    entities = []

    entities.append(
        IpmiSwitch(
            coordinator,
            hass,
            SwitchEntityDescription(
                key="chassis",
                name="Power on/Soft shutdown",
                icon="mdi:power",
                # device_class=SwitchDeviceClass.OUTLET,
                entity_registry_enabled_default=True,
            ),
            data,
            unique_id,
        )
    )

    async_add_entities(entities, True)

class IpmiSwitch(CoordinatorEntity[DataUpdateCoordinator[dict[str, str]]],SwitchEntity):
    """Entity that controls a power on / soft shutdown of the IPMI server."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, str]],
        hass: HomeAssistant,
        switch_description: SwitchEntityDescription,
        data: IpmiServer,
        unique_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = switch_description

        device_name = data.name.title()
        self.entity_id = DOMAIN + "_" + data._alias + "_" + switch_description.key
        self._attr_unique_id = f"{unique_id}_{switch_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=device_name,
        )
        self.ipmi_data = data
        self._attr_device_info.update(_get_ipmi_device_info(data))
        self.control_result: dict[str, Any] | None = None

    @property
    def is_on(self) -> bool:
        """If switch is on."""
        status = self.coordinator.data
        return bool(status.power_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on relay."""
        await self.hass.async_add_executor_job(self.ipmi_data.power_on)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off relay."""
        await self.hass.async_add_executor_job(self.ipmi_data.soft_shutdown)
        self.async_write_ha_state()
