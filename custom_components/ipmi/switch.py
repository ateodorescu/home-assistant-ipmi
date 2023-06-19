from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any, cast

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
    SwitchDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_SW_VERSION,
    PERCENTAGE,
    STATE_UNKNOWN,
    STATE_OFF,
    STATE_ON,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    REVOLUTIONS_PER_MINUTE
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import PyIpmiData
from .const import (
    COORDINATOR,
    DOMAIN,
    PYIPMI_DATA,
    PYIPMI_UNIQUE_ID,
)

ENTITY_ID_FORMAT = DOMAIN + ".{}"

IPMI_DEV_INFO_TO_DEV_INFO: dict[str, str] = {
    "manufacturer": ATTR_MANUFACTURER,
    "product_name": ATTR_MODEL,
    "fw_revision": ATTR_SW_VERSION,
}

_LOGGER = logging.getLogger(__name__)

def _get_ipmi_device_info(data: PyIpmiData) -> DeviceInfo:
    """Return a DeviceInfo object filled with IPMI device info."""
    ipmi_dev_infos = asdict(data.device_info)
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
    pyipmi_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = pyipmi_data[COORDINATOR]
    data = pyipmi_data[PYIPMI_DATA]
    unique_id = pyipmi_data[PYIPMI_UNIQUE_ID]
    status = coordinator.data
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
        data: PyIpmiData,
        unique_id: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = switch_description

        device_name = data.name.title()
        self.entity_id = DOMAIN + "." + data._alias + "." + switch_description.key
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
        self.async_write_ha_state()
        self.ipmi_data.power_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off relay."""
        self.async_write_ha_state()
        self.ipmi_data.soft_shutdown()

