"""Shared entity helpers for the IPMI integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_UNSET = object()


class IpmiCoordinatorEntity(CoordinatorEntity):
    """Coordinator entity that writes state only when its own value changes.

    The IPMI coordinator carries all readings for a server. A changing fan,
    temperature, or duration reading therefore wakes every entity, including
    otherwise static buttons and power controls. Avoid reporting an unchanged
    entity state on each shared coordinator refresh.
    """

    _last_coordinator_signature: Any = _UNSET

    def _coordinator_signature(self) -> Any:
        """Return the entity values that should trigger a state write."""
        return (self.available, self.state, self.extra_state_attributes)

    def _remember_coordinator_signature(self) -> None:
        """Remember the entity's current externally visible values."""
        self._last_coordinator_signature = self._coordinator_signature()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates and establish the initial state baseline."""
        await super().async_added_to_hass()
        self._remember_coordinator_signature()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write state only when this entity's visible values changed."""
        signature = self._coordinator_signature()
        if signature == self._last_coordinator_signature:
            return
        self._last_coordinator_signature = signature
        self.async_write_ha_state()
