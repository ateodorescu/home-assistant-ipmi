"""Unit tests for IPMI pure helpers (no Home Assistant install required)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

IPMI_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "ipmi"
sys.path.insert(0, str(IPMI_DIR))

import util  # noqa: E402


class TestFormatEntryUniqueId:
    def test_lowercases_alias(self) -> None:
        assert util.format_entry_unique_id("MyServer") == "myserver"

    def test_strips_whitespace(self) -> None:
        assert util.format_entry_unique_id("  rack-1  ") == "rack-1"

    def test_keeps_distinct_aliases(self) -> None:
        assert util.format_entry_unique_id("server-a") != util.format_entry_unique_id(
            "server-b"
        )


class TestAsStrList:
    def test_list_passthrough(self) -> None:
        assert util.as_str_list(["temperature", "fan"]) == ["temperature", "fan"]

    def test_single_string_becomes_one_item(self) -> None:
        assert util.as_str_list("temperature") == ["temperature"]

    def test_none_uses_default(self) -> None:
        assert util.as_str_list(None, ["voltage"]) == ["voltage"]

    def test_empty_string_uses_default(self) -> None:
        assert util.as_str_list("", ["fan"]) == ["fan"]


class TestNormalizeOptions:
    def test_unchanged_when_legacy_minimal_disabled(self) -> None:
        config = {
            "minimal_ipmi": False,
            "sensor_types": ["temperature"],
            "create_energy_sensors": True,
            "ignore_checksum_errors": True,
            "backend_preference": "addon",
        }
        assert util.normalize_options(config) == config

    def test_legacy_minimal_clears_sensor_options(self) -> None:
        normalized = util.normalize_options(
            {
                "minimal_ipmi": True,
                "sensor_types": ["temperature", "fan"],
                "create_energy_sensors": True,
                "ignore_checksum_errors": True,
                "backend_preference": "addon",
            }
        )
        assert normalized["sensor_types"] == []
        assert normalized["create_energy_sensors"] is False
        assert normalized["ignore_checksum_errors"] is False
        assert normalized["backend_preference"] == "addon"


class TestEffectiveSensorTypes:
    def test_legacy_minimal_returns_empty(self) -> None:
        assert util.effective_sensor_types({"minimal_ipmi": True}) == []

    def test_explicit_empty_list(self) -> None:
        assert util.effective_sensor_types({"sensor_types": []}) == []

    def test_default_when_missing(self) -> None:
        assert util.effective_sensor_types({}, default_types=["fan"]) == ["fan"]


class TestAddonCapabilities:
    def test_merge_capabilities(self) -> None:
        caps = util.update_addon_capabilities(
            {"statuses"},
            {"capabilities": ["sensor_types_filter", "resilient_poll"]},
        )
        assert caps == {"statuses", "sensor_types_filter", "resilient_poll"}


class TestGenerateSensorId:
    def test_spaces_and_case(self) -> None:
        assert util.generate_sensor_id("CPU Temp") == "cpu_temp"

    def test_strips_special_chars(self) -> None:
        assert util.generate_sensor_id("Fan #1 (Front)") == "fan_1_front"

    def test_keeps_underscores_and_digits(self) -> None:
        assert util.generate_sensor_id("PSU_1_VIN") == "psu_1_vin"


class TestEnergySensorHelpers:
    def test_iter_discovered_sensor_ids(self) -> None:
        sensors = {
            "fan": {"fan3b": "Fan3B", "fan1a": "Fan1A"},
            "temperature": {"inlet_temp": "Inlet Temp"},
        }
        states = {"fan1a": 7080, "inlet_temp": 32}
        assert util.iter_discovered_sensor_ids(sensors, states) == {
            "fan3b",
            "fan1a",
            "inlet_temp",
        }

    def test_iter_discovered_sensor_ids_accepts_php_empty_lists(self) -> None:
        sensors = {"fan": [], "temperature": []}
        states: list[str] = []
        assert util.iter_discovered_sensor_ids(sensors, states) == set()

    def test_normalize_addon_mapping(self) -> None:
        assert util.normalize_addon_mapping([]) == {}
        assert util.normalize_addon_mapping({"a": 1}) == {"a": 1}

    def test_normalize_addon_sensor_groups(self) -> None:
        groups = util.normalize_addon_sensor_groups(
            {"fan": [], "temperature": {"cpu": "CPU Temp"}},
            sensor_types=["fan", "temperature"],
        )
        assert groups == {"fan": {}, "temperature": {"cpu": "CPU Temp"}}

    def test_energy_sensor_key(self) -> None:
        assert util.energy_sensor_key("system_power") == "system_power_energy"

    def test_integrate_power_left_riemann(self) -> None:
        # 100 W for 3600 s = 0.1 kWh
        result = util.integrate_power_left_riemann(
            previous_power_w=100.0,
            elapsed_seconds=3600.0,
            accumulated_kwh=1.5,
        )
        assert result == pytest.approx(1.6)

    def test_integrate_skips_without_previous_power(self) -> None:
        result = util.integrate_power_left_riemann(
            previous_power_w=None,
            elapsed_seconds=60.0,
            accumulated_kwh=2.0,
        )
        assert result == 2.0


class TestEnergySensorsEnabled:
    def test_requires_power_type(self) -> None:
        assert util.energy_sensors_enabled(["temperature", "fan"], True) is False

    def test_requires_option_enabled(self) -> None:
        assert util.energy_sensors_enabled(["power", "temperature"], False) is False

    def test_true_when_power_monitored_and_option_on(self) -> None:
        assert util.energy_sensors_enabled(["power", "temperature"], True) is True


class TestRedactConnectionSecrets:
    def test_redacts_password_and_kg(self) -> None:
        message = "GET http://x/?password=s3cret&kg_key=AABB"
        assert (
            util.redact_connection_secrets(message, "s3cret", "AABB")
            == "GET http://x/?password=***&kg_key=***"
        )

    def test_noop_without_secrets(self) -> None:
        message = "connection refused"
        assert util.redact_connection_secrets(message) == message


class TestLooksLikeAuthError:
    @pytest.mark.parametrize(
        "message",
        [
            "Authentication failed",
            "Invalid user or password",
            "access denied for user",
            "insufficient privilege",
        ],
    )
    def test_positive(self, message: str) -> None:
        assert util.looks_like_auth_error(message) is True

    @pytest.mark.parametrize(
        "message",
        [None, "", "Connection timed out", "SDR repository empty"],
    )
    def test_negative(self, message: str | None) -> None:
        assert util.looks_like_auth_error(message) is False


class TestValidateKgKey:
    def test_empty(self) -> None:
        assert util.validate_kg_key("") == ""
        assert util.validate_kg_key("   ") == ""
        assert util.validate_kg_key(None) == ""

    def test_normalizes_hex(self) -> None:
        assert util.validate_kg_key("aabb") == "AABB"

    def test_odd_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="even number"):
            util.validate_kg_key("abc")

    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="at most 40"):
            util.validate_kg_key("A" * 42)

    def test_non_hex_rejected(self) -> None:
        with pytest.raises(ValueError, match="hexadecimal"):
            util.validate_kg_key("GG")


class TestCategorizeRmcpSensor:
    def test_temperature_type(self) -> None:
        assert util.categorize_rmcp_sensor(0x01, None) == "temperature"

    def test_voltage_type(self) -> None:
        assert util.categorize_rmcp_sensor(0x02, None) == "voltage"

    def test_current_type(self) -> None:
        assert util.categorize_rmcp_sensor(0x03, None) == "current"

    def test_fan_type(self) -> None:
        assert util.categorize_rmcp_sensor(0x04, None) == "fan"

    def test_power_via_units(self) -> None:
        assert util.categorize_rmcp_sensor(None, 0x06) == "power"

    def test_time_via_units(self) -> None:
        assert util.categorize_rmcp_sensor(None, 0x15) == "time"

    def test_type_wins_over_units(self) -> None:
        assert util.categorize_rmcp_sensor(0x01, 0x06) == "temperature"

    def test_unknown(self) -> None:
        assert util.categorize_rmcp_sensor(0x99, 0x99) is None


class TestAddonActionSucceeded:
    def test_true(self) -> None:
        assert util.addon_action_succeeded({"success": True}) is True

    def test_false_payload(self) -> None:
        assert util.addon_action_succeeded({"success": False}) is False

    def test_none(self) -> None:
        assert util.addon_action_succeeded(None) is False


class TestIpmiServerLogic:
    """Lightweight tests for server helpers without a live BMC / Home Assistant."""

    @pytest.fixture(autouse=True)
    def _stub_deps(self):
        pytest.importorskip("pyipmi")
        import types

        # Minimal Home Assistant stubs so const/server import without HA installed.
        if "homeassistant.const" not in sys.modules:
            ha = types.ModuleType("homeassistant")
            ha_const = types.ModuleType("homeassistant.const")
            ha_const.Platform = types.SimpleNamespace(
                SENSOR="sensor",
                SWITCH="switch",
                BINARY_SENSOR="binary_sensor",
                BUTTON="button",
            )
            ha_const.ATTR_MANUFACTURER = "manufacturer"
            ha_const.ATTR_MODEL = "model"
            ha_const.ATTR_SW_VERSION = "sw_version"
            ha_core = types.ModuleType("homeassistant.core")
            ha_core.HomeAssistant = object
            ha_helpers = types.ModuleType("homeassistant.helpers")
            ha_dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
            ha_dispatcher.dispatcher_send = lambda *args, **kwargs: None
            sys.modules["homeassistant"] = ha
            sys.modules["homeassistant.const"] = ha_const
            sys.modules["homeassistant.core"] = ha_core
            sys.modules["homeassistant.helpers"] = ha_helpers
            sys.modules["homeassistant.helpers.dispatcher"] = ha_dispatcher

        # Import as package so relative imports in server.py resolve.
        import importlib

        pkg_name = "ipmi_under_test"
        # Always reload server so source edits are picked up during local runs.
        for key in list(sys.modules):
            if key == pkg_name or key.startswith(f"{pkg_name}."):
                del sys.modules[key]

        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(IPMI_DIR)]
        sys.modules[pkg_name] = pkg
        sys.modules[f"{pkg_name}.const"] = importlib.import_module("const")
        # Fresh util from disk (already on sys.path as top-level "util")
        if "util" in sys.modules:
            importlib.reload(sys.modules["util"])
        sys.modules[f"{pkg_name}.util"] = sys.modules["util"]
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.server",
            IPMI_DIR / "server.py",
            submodule_search_locations=[str(IPMI_DIR)],
        )
        server_mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.server"] = server_mod
        assert spec.loader is not None
        spec.loader.exec_module(server_mod)

        self._server_mod = server_mod

    def _make_server(self, **overrides):
        connection = {
            "host": "192.0.2.1",
            "port": 623,
            "alias": "lab",
            "username": "admin",
            "password": "secret",
            "kg_key": "",
            "privilege_level": "ADMINISTRATOR",
            "ipmi_server_host": "http://127.0.0.1",
            "addon_port": 9595,
            "addon_interface": "auto",
            "addon_extra_params": None,
            "ignore_checksum_errors": False,
            "backend_preference": "auto",
            "sensor_types": [],
        }
        connection.update(overrides)
        return self._server_mod.IpmiServer(MagicMock(), "entry1", connection)

    def test_rmcp_preference_skips_addon(self) -> None:
        srv = self._make_server(backend_preference="rmcp")
        assert srv._should_try_addon() is False
        assert srv._should_try_rmcp() is True
        assert srv.get_from_addon(None) is None

    def test_addon_preference_skips_rmcp(self) -> None:
        srv = self._make_server(backend_preference="addon")
        assert srv._should_try_addon() is True
        assert srv._should_try_rmcp() is False

    def test_chassis_falls_back_when_addon_reports_failure(self) -> None:
        srv = self._make_server(backend_preference="auto")
        with (
            patch.object(
                srv, "get_from_addon", return_value={"success": False, "message": "busy"}
            ),
            patch.object(srv, "run_rmcp_command") as rmcp,
        ):
            srv.power_on()
            rmcp.assert_called_once()

    def test_chassis_raises_when_addon_only_and_addon_fails(self) -> None:
        chassis_error = self._server_mod.util.IpmiChassisCommandError
        srv = self._make_server(backend_preference="addon")
        with patch.object(
            srv, "get_from_addon", return_value={"success": False, "message": "busy"}
        ):
            with pytest.raises(chassis_error, match="RMCP is disabled"):
                srv.soft_shutdown()

    def test_chassis_rmcp_failure_raises(self) -> None:
        chassis_error = self._server_mod.util.IpmiChassisCommandError
        srv = self._make_server(backend_preference="rmcp")
        with patch.object(
            srv,
            "run_rmcp_command",
            side_effect=chassis_error("RMCP failed"),
        ):
            with pytest.raises(chassis_error, match="RMCP failed"):
                srv.power_on()

    def test_run_rmcp_command_raises_on_connection_error(self) -> None:
        chassis_error = self._server_mod.util.IpmiChassisCommandError
        srv = self._make_server()
        with patch.object(
            srv, "_connect_unlocked", side_effect=OSError("connection refused")
        ):
            with pytest.raises(chassis_error, match="connection refused"):
                srv.run_rmcp_command(0)

    def test_chassis_does_not_rmcp_when_addon_succeeds(self) -> None:
        srv = self._make_server(backend_preference="auto")
        with (
            patch.object(srv, "get_from_addon", return_value={"success": True}),
            patch.object(srv, "run_rmcp_command") as rmcp,
        ):
            srv.power_on()
            rmcp.assert_not_called()

    def test_send_command_clear_error_without_addon(self) -> None:
        srv = self._make_server(backend_preference="rmcp")
        with pytest.raises(RuntimeError, match="requires the ipmi-server addon"):
            srv.send_command("bmc info", ignore_errors=False)

    def test_send_command_ignore_errors_returns_empty(self) -> None:
        srv = self._make_server(backend_preference="rmcp")
        assert srv.send_command("bmc info", ignore_errors=True) == ""

    def test_known_sensors_use_set(self) -> None:
        srv = self._make_server()
        assert isinstance(srv._known_sensors, set)
        srv.add_known_sensor("cpu_temp")
        assert srv.is_known_sensor("cpu_temp")
        srv.add_known_sensor("cpu_temp")
        assert len(srv._known_sensors) == 1

    def test_update_discovers_sensors_without_readings(self) -> None:
        """Metadata-only sensors (e.g. failed fan in SDR) should still trigger discovery."""
        srv = self._make_server()
        dispatched: list[str] = []

        def _capture(hass, signal):
            dispatched.append(signal)

        with patch.object(self._server_mod, "dispatcher_send", side_effect=_capture):
            srv._device_info = self._server_mod.IpmiDeviceInfo(
                sensors={"fan": {"fan3b": "Fan3B"}},
                states={},
                statuses={"fan3b": "cr"},
            )
            srv.update = lambda: None  # prevent re-fetch
            # Simulate the tail of update() when addon/json already populated device_info
            info = srv._device_info
            sensor_ids = util.iter_discovered_sensor_ids(info.sensors, info.states)
            new_sensors = [
                sensor_id
                for sensor_id in sensor_ids
                if sensor_id not in srv._known_sensors
            ]
            assert new_sensors == ["fan3b"]

    def test_addon_uses_get_by_default(self) -> None:
        srv = self._make_server()
        get_resp = MagicMock()
        get_resp.raise_for_status = MagicMock()
        get_resp.json.return_value = {"success": True, "power_on": True}

        with patch.object(
            self._server_mod.requests, "post"
        ) as post, patch.object(
            self._server_mod.requests, "get", return_value=get_resp
        ) as get:
            result = srv.get_from_addon(None)
            assert result == {"success": True, "power_on": True}
            post.assert_not_called()
            get.assert_called_once()

    def test_addon_post_false_success_falls_back_to_get(self) -> None:
        """POST 200 + success:false must not block GET (current addon behavior)."""
        srv = self._make_server()
        srv._addon_use_post = True
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"success": False, "message": "missing host"}
        get_resp = MagicMock()
        get_resp.raise_for_status = MagicMock()
        get_resp.json.return_value = {"success": True, "power_on": True}

        with patch.object(
            self._server_mod.requests, "post", return_value=post_resp
        ) as post, patch.object(
            self._server_mod.requests, "get", return_value=get_resp
        ) as get:
            result = srv.get_from_addon(None)
            assert result == {"success": True, "power_on": True}
            post.assert_called_once()
            get.assert_called_once()
            assert srv._addon_use_post is False

    def test_addon_skip_after_failures(self) -> None:
        srv = self._make_server(backend_preference="auto")
        threshold = self._server_mod.ADDON_FAILURE_SKIP_THRESHOLD
        for _ in range(threshold):
            srv._record_addon_transport_failure()
        assert srv._should_try_addon() is False

    def test_ingest_addon_capabilities(self) -> None:
        srv = self._make_server()
        srv._ingest_addon_capabilities(
            {
                "api_version": 1,
                "addon_version": "2.6.0",
                "capabilities": ["sensor_types_filter"],
            }
        )
        assert srv.addon_version == "2.6.0"
        assert srv.addon_capabilities == {"sensor_types_filter"}

    def test_bc_method_aliases(self) -> None:
        cls = self._server_mod.IpmiServer
        assert cls.getFromAddon is cls.get_from_addon
        assert cls.getFromRmcp is cls.get_from_rmcp
        assert cls.runRmcpCommand is cls.run_rmcp_command

    def test_power_only_polls_addon_first(self) -> None:
        srv = self._make_server(sensor_types=[])
        power_payload = {
            "device": {"product_name": "None"},
            "sensors": {t: {} for t in self._server_mod.SENSOR_TYPES},
            "states": {},
            "power_on": True,
            "success": True,
        }
        with (
            patch.object(srv, "get_from_addon", return_value=power_payload) as addon,
            patch.object(srv, "get_from_rmcp") as rmcp,
        ):
            srv.update()
            addon.assert_called_once()
            rmcp.assert_not_called()
            assert srv.last_backend == self._server_mod.BACKEND_ADDON
            assert srv.device_info is not None
            assert srv.device_info.power_on is True

    def test_power_only_passes_sensor_types_param(self) -> None:
        srv = self._make_server(sensor_types=[])
        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.json.return_value = {
            "success": True,
            "power_on": True,
            "device": {},
            "sensors": {t: {} for t in self._server_mod.SENSOR_TYPES},
            "states": {},
        }
        with patch.object(self._server_mod.requests, "get", return_value=get_resp) as get:
            srv.get_from_addon(None)
            params = get.call_args.kwargs["params"]
            assert params["sensor_types"] == ""

    def test_power_only_rmcp_skips_fru(self) -> None:
        srv = self._make_server(sensor_types=[])
        mock_ipmi = MagicMock()
        mock_ipmi.get_device_id.return_value.fw_revision.version_to_string.return_value = (
            "1.0"
        )
        mock_ipmi.get_device_id.return_value.product_id = 42
        mock_ipmi.get_chassis_status.return_value.power_on = False

        with patch.object(srv, "_connect_unlocked", return_value=mock_ipmi):
            result = srv.get_from_rmcp()

        assert result is not None
        assert result["power_on"] is False
        mock_ipmi.get_fru_inventory.assert_not_called()

    # --- known-sensor tracking across polls -------------------------------

    def _addon_payload(self, sensors: dict, states: dict) -> dict:
        return {
            "success": True,
            "power_on": bool(states),
            "device": {},
            "sensors": sensors,
            "states": states,
            "statuses": {},
        }

    def _poll(self, srv, payload: dict, announce: MagicMock) -> None:
        with (
            patch.object(srv, "_probe_addon_meta", return_value=None),
            patch.object(srv, "get_from_addon", return_value=payload),
            patch.object(self._server_mod, "dispatcher_send", announce),
        ):
            srv.update()

    def test_known_sensors_survive_empty_poll(self) -> None:
        """A poll with no readings (host powered off) must not forget sensors.

        Entities are never removed at runtime, so announcing an already
        created sensor as "new" again makes the sensor platform re-create
        an entity with an existing unique_id.
        """
        srv = self._make_server(backend_preference="addon")
        announce = MagicMock()
        full = self._addon_payload(
            {"temperature": {"temp_cpu": "CPU Temp"}}, {"temp_cpu": "41"}
        )
        empty = self._addon_payload({}, {})

        self._poll(srv, full, announce)
        assert announce.call_count == 1
        # The sensor platform reacts to the signal and creates the entity.
        srv.add_known_sensor("temp_cpu")

        self._poll(srv, empty, announce)
        assert srv.is_known_sensor("temp_cpu")

        self._poll(srv, full, announce)
        assert srv.is_known_sensor("temp_cpu")
        assert announce.call_count == 1

    def test_known_sensors_survive_partial_poll(self) -> None:
        """A sensor missing from one poll is still known when it returns."""
        srv = self._make_server(backend_preference="addon")
        announce = MagicMock()
        both = self._addon_payload(
            {"temperature": {"temp_cpu": "CPU Temp"}, "fan": {"fan1": "FAN1"}},
            {"temp_cpu": "41", "fan1": "900"},
        )
        only_fan = self._addon_payload({"fan": {"fan1": "FAN1"}}, {"fan1": "900"})

        self._poll(srv, both, announce)
        assert announce.call_count == 1
        srv.add_known_sensor("temp_cpu")
        srv.add_known_sensor("fan1")

        self._poll(srv, only_fan, announce)
        self._poll(srv, both, announce)
        assert srv.is_known_sensor("temp_cpu")
        assert announce.call_count == 1

    def test_genuinely_new_sensor_is_announced(self) -> None:
        """Discovery of a sensor never seen before still fires the signal."""
        srv = self._make_server(backend_preference="addon")
        announce = MagicMock()
        one = self._addon_payload(
            {"temperature": {"temp_cpu": "CPU Temp"}}, {"temp_cpu": "41"}
        )
        two = self._addon_payload(
            {"temperature": {"temp_cpu": "CPU Temp", "temp_mb": "MB Temp"}},
            {"temp_cpu": "41", "temp_mb": "35"},
        )

        self._poll(srv, one, announce)
        srv.add_known_sensor("temp_cpu")
        self._poll(srv, two, announce)
        assert announce.call_count == 2
