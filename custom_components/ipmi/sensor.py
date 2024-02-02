"""Provides sensors to track various status aspects of an IPMI server."""
from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Final, cast
from datetime import timedelta

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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from . import IpmiServer
from .helpers import get_ipmi_data, get_ipmi_server
from .const import (
    COORDINATOR,
    DOMAIN,
    KEY_STATUS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_NEW_SENSOR_SIGNAL,
    IPMI_UPDATE_SENSOR_SIGNAL,
    IPMI_DEV_INFO_TO_DEV_INFO,
    DISPATCHERS
)

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

def create_entity_sensors(ipmi_data: object, filter: list = []) -> dict:
    coordinator = ipmi_data[COORDINATOR]
    data = ipmi_data[IPMI_DATA]
    unique_id = ipmi_data[IPMI_UNIQUE_ID]
    status = coordinator.data
    entities = []
    # _LOGGER.critical(status)

    for id in status.sensors.get("temperature"):
        if (id in filter):
            data.add_known_sensor(id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=id,
                        name=status.sensors["temperature"][id],
                        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                        device_class=SensorDeviceClass.TEMPERATURE,
                        state_class=SensorStateClass.MEASUREMENT,
                        # entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                )
            )

    for id in status.sensors.get("voltage"):
        if (id in filter):
            data.add_known_sensor(id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=id,
                        name=status.sensors["voltage"][id],
                        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                        device_class=SensorDeviceClass.VOLTAGE,
                        state_class=SensorStateClass.MEASUREMENT,
                        # entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                )
            )

    for id in status.sensors.get("fan"):
        if (id in filter):
            data.add_known_sensor(id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=id,
                        name=status.sensors["fan"][id],
                        icon="mdi:fan",
                        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
                        state_class=SensorStateClass.MEASUREMENT,
                        # entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                )
            )

    for id in status.sensors.get("power"):
        if (id in filter):
            data.add_known_sensor(id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=id,
                        name=status.sensors["power"][id],
                        native_unit_of_measurement=UnitOfPower.WATT,
                        device_class=SensorDeviceClass.POWER,
                        state_class=SensorStateClass.MEASUREMENT,
                        # entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                )
            )

    for id in status.sensors.get("time"):
        if (id in filter):
            data.add_known_sensor(id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=id,
                        name=status.sensors["time"][id],
                        native_unit_of_measurement=UnitOfTime.SECONDS,
                        device_class=SensorDeviceClass.DURATION,
                        state_class=SensorStateClass.MEASUREMENT,
                        # entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                )
            )

    return entities

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPMI sensors."""

    server_id = config_entry.entry_id
    ipmiserver = get_ipmi_server(hass, server_id)
    coordinator = ipmiserver[COORDINATOR]
    data = ipmiserver[IPMI_DATA]
    unique_id = ipmiserver[IPMI_UNIQUE_ID]
    async_add_entities([
        IpmiSensor(
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
    ])

    _LOGGER.debug("Sensors added")

    registry = er.async_get(hass)

    @callback
    def async_new_sensors(new_entities):
        _async_add_entities(hass, registry, async_add_entities, server_id, new_entities)

    unsub = async_dispatcher_connect(
        hass, IPMI_NEW_SENSOR_SIGNAL.format(server_id), async_new_sensors
    )
    get_ipmi_data(hass)[DISPATCHERS][server_id].append(unsub)
    _LOGGER.debug("New entity listener created")

@callback
def _async_add_entities(hass, registry, async_add_entities, server_id, new_entities):
    """Set up IPMI sensors."""
    ipmiserver = get_ipmi_server(hass, server_id)

    if (ipmiserver):
        _LOGGER.debug("New entities: %s", new_entities)
        entities = create_entity_sensors(ipmiserver, new_entities)
        async_add_entities(entities, True)


class IpmiSensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, str]]], SensorEntity):
    """Representation of a sensor entity for IPMI status values."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, str]],
        sensor_description: SensorEntityDescription,
        data: IpmiServer,
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
        else:
            if len(status.states) == 0:
                return False

            state = status.states.get(self.entity_description.key, None)
            
            return (state is not None)

    @property
    def native_value(self) -> str | None:
        """Return entity state from server states."""
        status = self.coordinator.data

        if self.entity_description.key == KEY_STATUS:
            if status.power_on:
                return STATE_ON
            else:
                return STATE_OFF
        else:
            if not status.states:
                return self.available

            state = status.states.get(self.entity_description.key, None)

            if state is not None:
                return state
            else:
                return STATE_UNKNOWN