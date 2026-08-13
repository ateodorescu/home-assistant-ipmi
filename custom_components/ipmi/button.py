"""Button entities for IPMI power commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import re

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    COMMAND_POWER_CYCLE,
    COMMAND_POWER_OFF,
    COMMAND_POWER_ON,
    COMMAND_POWER_RESET,
    COMMAND_POWER_SOFT,
    COORDINATOR,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
)
from .helpers import async_run_chassis_command, device_info_from_ipmi_server, get_ipmi_server
from .server import IpmiServer

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class IpmiButtonEntityDescription(ButtonEntityDescription):
    """Describes an IPMI button entity."""

    press_action: str


BUTTON_TYPES: tuple[IpmiButtonEntityDescription, ...] = (
    IpmiButtonEntityDescription(
        key=COMMAND_POWER_ON,
        translation_key=COMMAND_POWER_ON,
        icon="mdi:power-on",
        press_action=COMMAND_POWER_ON,
    ),
    IpmiButtonEntityDescription(
        key=COMMAND_POWER_OFF,
        translation_key=COMMAND_POWER_OFF,
        icon="mdi:power-off",
        press_action=COMMAND_POWER_OFF,
    ),
    IpmiButtonEntityDescription(
        key=COMMAND_POWER_CYCLE,
        translation_key=COMMAND_POWER_CYCLE,
        icon="mdi:restart",
        press_action=COMMAND_POWER_CYCLE,
    ),
    IpmiButtonEntityDescription(
        key=COMMAND_POWER_RESET,
        translation_key=COMMAND_POWER_RESET,
        icon="mdi:restart-alert",
        press_action=COMMAND_POWER_RESET,
    ),
    IpmiButtonEntityDescription(
        key=COMMAND_POWER_SOFT,
        translation_key=COMMAND_POWER_SOFT,
        icon="mdi:power-sleep",
        press_action=COMMAND_POWER_SOFT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IPMI buttons."""
    ipmiserver = get_ipmi_server(hass, config_entry.entry_id)
    coordinator = ipmiserver[COORDINATOR]
    data = ipmiserver[IPMI_DATA]
    unique_id = ipmiserver[IPMI_UNIQUE_ID]

    async_add_entities(
        [
            IpmiButton(coordinator, description, data, unique_id)
            for description in BUTTON_TYPES
        ],
        True,
    )


class IpmiButton(CoordinatorEntity[DataUpdateCoordinator], ButtonEntity):
    """Button that runs a chassis power command."""

    _attr_has_entity_name = True
    entity_description: IpmiButtonEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: IpmiButtonEntityDescription,
        data: IpmiServer,
        unique_id: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        entity_key = f"{data._alias}_{description.key}"
        entity_key = re.sub(r"[^\w]", "_", entity_key).lower()
        self._attr_unique_id = f"{unique_id}_{entity_key}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)
        self.ipmi_data = data

    async def async_press(self) -> None:
        """Handle the button press."""
        action: Callable[[], None] = getattr(
            self.ipmi_data, self.entity_description.press_action
        )
        await async_run_chassis_command(self.hass, action)
        await self.coordinator.async_request_refresh()
