"""Provides sensors to track various status aspects of an IPMI server."""
from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Final, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNKNOWN,
    STATE_OFF,
    STATE_ON,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfPower,
    UnitOfTime,
    REVOLUTIONS_PER_MINUTE
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import PyIpmiData
from .const import (
    COORDINATOR,
    DOMAIN,
    KEY_STATUS,
    PYIPMI_DATA,
    PYIPMI_UNIQUE_ID,
    IPMI_DEV_INFO_TO_DEV_INFO
)

_LOGGER = logging.getLogger(__name__)

def _get_ipmi_device_info(data: PyIpmiData) -> DeviceInfo:
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
    """Set up the IPMI sensors."""

    pyipmi_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = pyipmi_data[COORDINATOR]
    data = pyipmi_data[PYIPMI_DATA]
    unique_id = pyipmi_data[PYIPMI_UNIQUE_ID]
    status = coordinator.data
    entities = []

    for id in status.sensors["temperature"]:
        enabled = True
        value = status.states[id]

        if not value:
            enabled = False

        entities.append(
            IPMISensor(
                coordinator,
                SensorEntityDescription(
                    key=id,
                    name=status.sensors["temperature"][id],
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                    device_class=SensorDeviceClass.TEMPERATURE,
                    state_class=SensorStateClass.MEASUREMENT,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=enabled,
                ),
                data,
                unique_id,
            )
        )

    for id in status.sensors["voltage"]:
        enabled = True
        value = status.states[id]

        if not value:
            enabled = False

        entities.append(
            IPMISensor(
                coordinator,
                SensorEntityDescription(
                    key=id,
                    name=status.sensors["voltage"][id],
                    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                    device_class=SensorDeviceClass.VOLTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=enabled,
                ),
                data,
                unique_id,
            )
        )

    for id in status.sensors["fan"]:
        enabled = True
        value = status.states[id]

        if not value:
            enabled = False

        entities.append(
            IPMISensor(
                coordinator,
                SensorEntityDescription(
                    key=id,
                    name=status.sensors ["fan"][id],
                    icon="mdi:fan",
                    native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
                    state_class=SensorStateClass.MEASUREMENT,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=enabled,
                ),
                data,
                unique_id,
            )
        )

    for id in status.sensors["power"]:
        enabled = True
        value = status.states[id]

        if not value:
            enabled = False

        entities.append(
            IPMISensor(
                coordinator,
                SensorEntityDescription(
                    key=id,
                    name=status.sensors ["power"][id],
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=enabled,
                ),
                data,
                unique_id,
            )
        )

    for id in status.sensors["time"]:
        enabled = True
        value = status.states[id]

        if not value:
            enabled = False

        entities.append(
            IPMISensor(
                coordinator,
                SensorEntityDescription(
                    key=id,
                    name=status.sensors ["time"][id],
                    native_unit_of_measurement=UnitOfTime.SECONDS,
                    device_class=SensorDeviceClass.DURATION,
                    state_class=SensorStateClass.MEASUREMENT,
                    # entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=enabled,
                ),
                data,
                unique_id,
            )
        )

    entities.append(
        IPMISensor(
            coordinator,
            SensorEntityDescription(
                key=KEY_STATUS,
                name="State",
                icon="mdi:power",
                entity_registry_enabled_default=True,
            ),
            data,
            unique_id,
        )
    )

    _LOGGER.info("Sensors added")
    async_add_entities(entities, True)


class IPMISensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, str]]], SensorEntity):
    """Representation of a sensor entity for IPMI status values."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, str]],
        sensor_description: SensorEntityDescription,
        data: PyIpmiData,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = sensor_description

        device_name = data.name.title()
        self._attr_unique_id = f"{unique_id}_{sensor_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=device_name,
        )
        self._attr_device_info.update(_get_ipmi_device_info(data))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        status = self.coordinator.data

        if self.entity_description.key == KEY_STATUS:
            return True
        elif status.states[self.entity_description.key] is not None:
            return True
        else:
            return False

    @property
    def native_value(self) -> str | None:
        """Return entity state from server states."""
        status = self.coordinator.data

        if self.entity_description.key == KEY_STATUS:
            if status.power_on:
                return STATE_ON
            else:
                return STATE_OFF
        elif (status.states[self.entity_description.key] is not None):
            return status.states[self.entity_description.key]
        else:
            return STATE_UNKNOWN


