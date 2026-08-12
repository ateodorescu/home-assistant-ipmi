"""Binary sensors for IPMI servers."""

from __future__ import annotations

import logging
import re

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import COORDINATOR, IPMI_DATA, IPMI_UNIQUE_ID
from .helpers import device_info_from_ipmi_server, get_ipmi_server
from .server import IpmiServer

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IPMI binary sensors."""
    ipmiserver = get_ipmi_server(hass, config_entry.entry_id)
    coordinator = ipmiserver[COORDINATOR]
    data = ipmiserver[IPMI_DATA]
    unique_id = ipmiserver[IPMI_UNIQUE_ID]

    async_add_entities(
        [
                IpmiPowerBinarySensor(
                coordinator,
                BinarySensorEntityDescription(
                    key="power",
                    translation_key="power",
                    device_class=BinarySensorDeviceClass.POWER,
                    entity_registry_enabled_default=True,
                ),
                data,
                unique_id,
            )
        ],
        True,
    )


class IpmiPowerBinarySensor(
    CoordinatorEntity[DataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor reflecting chassis power state."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: BinarySensorEntityDescription,
        data: IpmiServer,
        unique_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        entity_key = f"{data._alias}_{description.key}"
        entity_key = re.sub(r"[^\w]", "_", entity_key).lower()
        self._attr_unique_id = f"{unique_id}_{entity_key}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)
        self.ipmi_data = data

    @property
    def is_on(self) -> bool:
        """Return True if the server is powered on."""
        status = self.coordinator.data
        return bool(status.power_on)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return backend attribute for diagnostics."""
        return {"backend": self.ipmi_data.last_backend}
