from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .helpers import device_info_from_ipmi_server, get_ipmi_server
from .const import (
    COORDINATOR,
    DOMAIN,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
)
from .server import IpmiServer

_LOGGER = logging.getLogger(__name__)


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
                entity_registry_enabled_default=True,
            ),
            data,
            unique_id,
        )
    )

    async_add_entities(entities, True)


class IpmiSwitch(CoordinatorEntity[DataUpdateCoordinator[dict[str, str]]], SwitchEntity):
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

        # unique_id / entity_id scheme kept for BC
        id_suffix = f"{data._alias}_{switch_description.key}"
        id_suffix = re.sub(r"[^\w]", "_", id_suffix).lower()

        self.entity_id = "switch." + DOMAIN + "_" + id_suffix
        self._attr_unique_id = f"{unique_id}_{id_suffix}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)
        self.ipmi_data = data

    @property
    def is_on(self) -> bool:
        """If switch is on."""
        status = self.coordinator.data
        return bool(status.power_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on relay."""
        await self.hass.async_add_executor_job(self.ipmi_data.power_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off relay."""
        await self.hass.async_add_executor_job(self.ipmi_data.soft_shutdown)
        await self.coordinator.async_request_refresh()
