"""Provides sensors to track various status aspects of an IPMI server."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_OFF,
    STATE_ON,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfPower,
    UnitOfElectricCurrent,
    UnitOfTime,
    UnitOfEnergy,
    REVOLUTIONS_PER_MINUTE,
)
from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
)

from .entity import IpmiCoordinatorEntity
from .helpers import device_info_from_ipmi_server, get_ipmi_data, get_ipmi_server
from .const import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_SENSOR_TYPES,
    COORDINATOR,
    DEFAULT_CREATE_ENERGY_SENSORS,
    DEFAULT_SENSOR_TYPES,
    DOMAIN,
    ENERGY_SENSOR_KEY_SUFFIX,
    KEY_CONNECTION_BACKEND,
    KEY_STATUS,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
    IPMI_NEW_SENSOR_SIGNAL,
    DISPATCHERS,
    SENSOR_TYPE_CURRENT,
    SENSOR_TYPE_FAN,
    SENSOR_TYPE_POWER,
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_TIME,
    SENSOR_TYPE_VOLTAGE,
)
from .server import IpmiServer
from .util import (
    as_str_list,
    energy_sensor_key,
    energy_sensors_enabled,
    integrate_power_left_riemann,
)

_LOGGER = logging.getLogger(__name__)

# Specs for dynamically discovered SDR / addon sensors (key = sensor group).
_DYNAMIC_SENSOR_SPECS: Final[dict[str, dict]] = {
    SENSOR_TYPE_TEMPERATURE: {
        "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
    },
    SENSOR_TYPE_VOLTAGE: {
        "native_unit_of_measurement": UnitOfElectricPotential.VOLT,
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
        "suggested_display_precision": 2,
    },
    SENSOR_TYPE_FAN: {
        "icon": "mdi:fan",
        "native_unit_of_measurement": REVOLUTIONS_PER_MINUTE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
    },
    SENSOR_TYPE_POWER: {
        "native_unit_of_measurement": UnitOfPower.WATT,
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
    },
    SENSOR_TYPE_CURRENT: {
        "native_unit_of_measurement": UnitOfElectricCurrent.AMPERE,
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
        "suggested_display_precision": 2,
    },
    SENSOR_TYPE_TIME: {
        "native_unit_of_measurement": UnitOfTime.SECONDS,
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_registry_enabled_default": True,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IPMI sensors."""

    server_id = config_entry.entry_id
    ipmiserver = get_ipmi_server(hass, server_id)

    if ipmiserver:
        coordinator = ipmiserver[COORDINATOR]
        data = ipmiserver[IPMI_DATA]
        unique_id = ipmiserver[IPMI_UNIQUE_ID]
        async_add_entities(
            [
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
                ),
                IpmiConnectionBackendSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=KEY_CONNECTION_BACKEND,
                        translation_key=KEY_CONNECTION_BACKEND,
                        icon="mdi:lan-connect",
                        entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                    ),
                    data,
                    unique_id,
                ),
            ]
        )

        _LOGGER.debug("State sensor added")

        @callback
        def async_new_sensors() -> None:
            """Set up IPMI sensors."""
            # Always read the live entry so options from config/create are current.
            entry = hass.config_entries.async_get_entry(server_id) or config_entry
            create_entity_sensors(ipmiserver, unique_id, async_add_entities, entry)

        get_ipmi_data(hass)[DISPATCHERS][server_id].append(
            async_dispatcher_connect(
                hass,
                IPMI_NEW_SENSOR_SIGNAL.format(server_id),
                async_new_sensors,
            )
        )
        _LOGGER.debug("Entity listener created")
        async_new_sensors()


@callback
def create_entity_sensors(
    ipmi_data: object,
    unique_id: str,
    async_add_entities: AddEntitiesCallback,
    config_entry: ConfigEntry,
) -> None:
    """Create entities for newly discovered sensors, respecting options filters."""
    coordinator = ipmi_data[COORDINATOR]
    data = ipmi_data[IPMI_DATA]
    status = coordinator.data
    entities = []

    enabled_types = set(
        as_str_list(
            config_entry.options.get(CONF_SENSOR_TYPES),
            DEFAULT_SENSOR_TYPES,
        )
    )
    create_energy_sensors = energy_sensors_enabled(
        enabled_types,
        bool(
            config_entry.options.get(
                CONF_CREATE_ENERGY_SENSORS, DEFAULT_CREATE_ENERGY_SENSORS
            )
        ),
        default_types=DEFAULT_SENSOR_TYPES,
    )

    _LOGGER.debug(
        "Discovering sensors (enabled=%s, energy=%s)",
        enabled_types,
        create_energy_sensors,
    )

    for sensor_type, spec in _DYNAMIC_SENSOR_SPECS.items():
        # Skip without marking known so enabling a type later (options reload)
        # can still create entities.
        if sensor_type not in enabled_types:
            continue

        sensors = status.sensors.get(sensor_type) or {}
        for sensor_id, name in sensors.items():
            if data.is_known_sensor(sensor_id):
                continue

            _LOGGER.debug("%s sensor will be added", sensor_id)
            data.add_known_sensor(sensor_id)

            entities.append(
                IpmiSensor(
                    coordinator,
                    SensorEntityDescription(
                        key=sensor_id,
                        name=name,
                        **dict(spec),
                    ),
                    data,
                    unique_id,
                )
            )

            if sensor_type == SENSOR_TYPE_POWER and create_energy_sensors:
                energy_key = energy_sensor_key(
                    sensor_id, suffix=ENERGY_SENSOR_KEY_SUFFIX
                )
                if data.is_known_sensor(energy_key):
                    continue

                _LOGGER.debug("%s energy sensor will be added", energy_key)
                data.add_known_sensor(energy_key)
                entities.append(
                    IpmiEnergySensor(
                        coordinator,
                        SensorEntityDescription(
                            key=energy_key,
                            name=f"{name} energy",
                            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                            device_class=SensorDeviceClass.ENERGY,
                            state_class=SensorStateClass.TOTAL_INCREASING,
                            entity_registry_enabled_default=True,
                            suggested_display_precision=3,
                        ),
                        data,
                        unique_id,
                        config_entry,
                        power_sensor_key=sensor_id,
                    )
                )

    async_add_entities(entities, True)


class IpmiSensor(
    IpmiCoordinatorEntity, SensorEntity
):
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

        # unique_id scheme kept for BC: {entry_id}_{alias}_{key}
        self._attr_unique_id = f"{unique_id}_{data._alias}_{sensor_description.key}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)

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

            return state is not None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose IPMI SDR status when the backend provides it (addon)."""
        if self.entity_description.key == KEY_STATUS:
            return None
        ipmi_status = self.coordinator.data.statuses.get(
            self.entity_description.key
        )
        if ipmi_status:
            return {"ipmi_status": ipmi_status}
        return None

    @property
    def native_value(self) -> str | float | None:
        """Return entity state from server states."""
        status = self.coordinator.data

        if self.entity_description.key == KEY_STATUS:
            if status.power_on:
                return STATE_ON
            else:
                return STATE_OFF
        else:
            if not status.states:
                return None

            state = status.states.get(self.entity_description.key, None)

            if state is not None:
                return float(state)
            # Missing reading → None (not STATE_UNKNOWN) for numeric sensors.
            return None


class IpmiEnergySensor(
    CoordinatorEntity[DataUpdateCoordinator[dict[str, str]]], RestoreSensor
):
    """Energy sensor derived from an IPMI power reading (kWh, left Riemann sum)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, str]],
        sensor_description: SensorEntityDescription,
        data: IpmiServer,
        unique_id: str,
        config_entry: ConfigEntry,
        *,
        power_sensor_key: str,
    ) -> None:
        """Initialize the energy sensor."""
        super().__init__(coordinator)
        self.entity_description = sensor_description
        self._config_entry = config_entry
        self._power_sensor_key = power_sensor_key
        self._power_sensor_unique_id = f"{unique_id}_{data._alias}_{power_sensor_key}"
        self._energy_kwh = 0.0
        self._last_power_w: float | None = None
        self._last_integration_time: datetime | None = None

        self._attr_unique_id = f"{unique_id}_{data._alias}_{sensor_description.key}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)

    def _energy_monitoring_enabled(self) -> bool:
        """Return True when power is monitored and energy companions are enabled."""
        return energy_sensors_enabled(
            self._config_entry.options.get(CONF_SENSOR_TYPES),
            bool(
                self._config_entry.options.get(
                    CONF_CREATE_ENERGY_SENSORS, DEFAULT_CREATE_ENERGY_SENSORS
                )
            ),
            default_types=DEFAULT_SENSOR_TYPES,
        )

    def _source_power_entity_enabled(self) -> bool:
        """Return False when the linked power sensor entity is disabled in HA."""
        entity_registry = er.async_get(self.hass)
        entity_id = entity_registry.async_get_entity_id(
            "sensor", DOMAIN, self._power_sensor_unique_id
        )
        if entity_id is None:
            return True
        entry = entity_registry.async_get(entity_id)
        return entry is not None and not entry.disabled

    async def async_added_to_hass(self) -> None:
        """Restore accumulated energy after restart."""
        await super().async_added_to_hass()
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            if last_sensor_data.native_value is not None:
                self._energy_kwh = float(last_sensor_data.native_value)
        self._last_integration_time = dt_util.utcnow()

    @property
    def available(self) -> bool:
        """Return True when power monitoring is active and the reading exists."""
        if not self._energy_monitoring_enabled():
            return False
        if not self._source_power_entity_enabled():
            return False
        status = self.coordinator.data
        if not status.states:
            return False
        return self._power_sensor_key in status.states

    @property
    def native_value(self) -> float:
        """Return accumulated energy in kWh."""
        return round(self._energy_kwh, 3)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Integrate the latest power sample when the coordinator updates."""
        if not self._energy_monitoring_enabled() or not self._source_power_entity_enabled():
            self._last_integration_time = dt_util.utcnow()
            super()._handle_coordinator_update()
            return

        status = self.coordinator.data
        now = dt_util.utcnow()

        if self._last_integration_time is None:
            self._last_integration_time = now

        if status.states:
            power_raw = status.states.get(self._power_sensor_key)
            if power_raw is not None:
                current_power_w = float(power_raw)
                elapsed = (now - self._last_integration_time).total_seconds()
                self._energy_kwh = integrate_power_left_riemann(
                    previous_power_w=self._last_power_w,
                    elapsed_seconds=elapsed,
                    accumulated_kwh=self._energy_kwh,
                )
                self._last_power_w = current_power_w

        self._last_integration_time = now
        super()._handle_coordinator_update()


class IpmiConnectionBackendSensor(
    IpmiCoordinatorEntity, SensorEntity
):
    """Diagnostic sensor showing whether addon or RMCP was used.

    This is the only dynamic/status helper marked diagnostic; it is enabled by
    default so the active backend is visible without extra setup.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = True

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
        self.ipmi_data = data
        self._attr_unique_id = f"{unique_id}_{data._alias}_{sensor_description.key}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)

    async def async_added_to_hass(self) -> None:
        """Run when entity is added; re-enable if previously integration-disabled."""
        await super().async_added_to_hass()
        if (
            self.registry_entry is not None
            and self.registry_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        ):
            er.async_get(self.hass).async_update_entity(
                self.entity_id, disabled_by=None
            )

    @property
    def available(self) -> bool:
        """Backend sensor stays available for diagnostics."""
        return True

    @property
    def native_value(self) -> str:
        """Return the last successful connection backend."""
        return self.ipmi_data.last_backend
