"""Unit tests for coordinator entity state-write filtering."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _load_entity_module():
    """Load entity.py with small Home Assistant stubs."""
    homeassistant = ModuleType("homeassistant")
    core = ModuleType("homeassistant.core")
    helpers = ModuleType("homeassistant.helpers")
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

    def callback(func):
        return func

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = MagicMock()

        @property
        def available(self):
            return self.coordinator.last_update_success

        async def async_added_to_hass(self):
            self.coordinator.async_add_listener(self._handle_coordinator_update)

        def async_write_ha_state(self):
            raise NotImplementedError

    core.callback = callback
    update_coordinator.CoordinatorEntity = CoordinatorEntity

    modules = {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }
    previous = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        path = (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "ipmi"
            / "entity.py"
        )
        spec = importlib.util.spec_from_file_location("ipmi_entity_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old_module in previous.items():
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module


class FakeCoordinator:
    def __init__(self):
        self.last_update_success = True
        self.listener = None

    def async_add_listener(self, listener, context=None):
        self.listener = listener
        return lambda: None


def test_unchanged_entity_does_not_write_state() -> None:
    module = _load_entity_module()
    coordinator = FakeCoordinator()

    class Entity(module.IpmiCoordinatorEntity):
        state = "on"
        extra_state_attributes = {"backend": "rmcp"}

        def __init__(self):
            super().__init__(coordinator)
            self.writes = 0

        def async_write_ha_state(self):
            self.writes += 1

    entity = Entity()
    asyncio.run(entity.async_added_to_hass())

    assert coordinator.listener is not None
    coordinator.listener()
    assert entity.writes == 0


def test_changed_state_or_availability_writes_once() -> None:
    module = _load_entity_module()
    coordinator = FakeCoordinator()

    class Entity(module.IpmiCoordinatorEntity):
        extra_state_attributes = None

        def __init__(self):
            super().__init__(coordinator)
            self.current_state = "on"
            self.writes = 0

        @property
        def state(self):
            return self.current_state

        def async_write_ha_state(self):
            self.writes += 1

    entity = Entity()
    asyncio.run(entity.async_added_to_hass())

    entity.current_state = "off"
    coordinator.listener()
    coordinator.listener()
    coordinator.last_update_success = False
    coordinator.listener()

    assert entity.writes == 2


def test_button_signature_can_ignore_last_pressed_state() -> None:
    module = _load_entity_module()
    coordinator = FakeCoordinator()

    class Button(module.IpmiCoordinatorEntity):
        state = "2026-08-18T20:00:00+00:00"
        extra_state_attributes = None

        def __init__(self):
            super().__init__(coordinator)
            self.writes = 0

        def _coordinator_signature(self):
            return self.available

        def async_write_ha_state(self):
            self.writes += 1

    button = Button()
    asyncio.run(button.async_added_to_hass())

    button.state = "2026-08-18T20:01:00+00:00"
    coordinator.listener()
    assert button.writes == 0

    coordinator.last_update_success = False
    coordinator.listener()
    assert button.writes == 1
