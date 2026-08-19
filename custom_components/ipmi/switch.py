from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .helpers import async_run_chassis_command, device_info_from_ipmi_server, get_ipmi_server
from .const import (
    CONF_POWER_OFF_DELAY,
    COORDINATOR,
    DEFAULT_POWER_OFF_DELAY,
    DOMAIN,
    IPMI_DATA,
    IPMI_UNIQUE_ID,
)
from .entity import IpmiCoordinatorEntity
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
            config_entry,
        )
    )

    async_add_entities(entities, True)


class IpmiSwitch(IpmiCoordinatorEntity, SwitchEntity):
    """Entity that controls a power on / soft shutdown of the IPMI server."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, str]],
        hass: HomeAssistant,
        switch_description: SwitchEntityDescription,
        data: IpmiServer,
        unique_id: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.entity_description = switch_description
        self._config_entry = config_entry
        self._pending_off_until: datetime | None = None
        self._unsub_pending_off: Callable[[], None] | None = None

        # unique_id / entity_id scheme kept for BC
        id_suffix = f"{data._alias}_{switch_description.key}"
        id_suffix = re.sub(r"[^\w]", "_", id_suffix).lower()

        self.entity_id = "switch." + DOMAIN + "_" + id_suffix
        self._attr_unique_id = f"{unique_id}_{id_suffix}"
        self._attr_device_info = device_info_from_ipmi_server(data, unique_id)
        self.ipmi_data = data

    @property
    def _power_off_delay(self) -> int:
        """Seconds to keep the switch off after a soft shutdown request."""
        return int(
            self._config_entry.options.get(
                CONF_POWER_OFF_DELAY, DEFAULT_POWER_OFF_DELAY
            )
        )

    @property
    def is_on(self) -> bool:
        """If switch is on."""
        if self._pending_off_until and dt_util.utcnow() < self._pending_off_until:
            return False
        status = self.coordinator.data
        return bool(status.power_on)

    def _clear_pending_off(self) -> None:
        """Cancel any active post-shutdown display hold."""
        self._pending_off_until = None
        if self._unsub_pending_off is not None:
            self._unsub_pending_off()
            self._unsub_pending_off = None

    def _start_pending_off(self) -> None:
        """Hold the switch off while the host finishes shutting down."""
        delay = self._power_off_delay
        if delay <= 0:
            return

        self._clear_pending_off()
        self._pending_off_until = dt_util.utcnow() + timedelta(seconds=delay)

        @callback
        def _pending_off_expired(_now: datetime) -> None:
            self._pending_off_until = None
            self._unsub_pending_off = None
            self._remember_coordinator_signature()
            self.async_write_ha_state()
            self.hass.async_create_task(self.coordinator.async_request_refresh())

        self._unsub_pending_off = async_track_point_in_time(
            self.hass, _pending_off_expired, self._pending_off_until
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on relay."""
        self._clear_pending_off()
        await async_run_chassis_command(self.hass, self.ipmi_data.power_on)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off relay."""
        await async_run_chassis_command(self.hass, self.ipmi_data.soft_shutdown)
        self._start_pending_off()
        if self._power_off_delay > 0:
            self._remember_coordinator_signature()
            self.async_write_ha_state()
        else:
            await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is removed."""
        self._clear_pending_off()
        await super().async_will_remove_from_hass()
