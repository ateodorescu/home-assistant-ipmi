"""Unit tests for IPMI pure helpers (no Home Assistant install required)."""

from __future__ import annotations

import sys
from pathlib import Path

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


class TestGenerateSensorId:
    def test_spaces_and_case(self) -> None:
        assert util.generate_sensor_id("CPU Temp") == "cpu_temp"

    def test_strips_special_chars(self) -> None:
        assert util.generate_sensor_id("Fan #1 (Front)") == "fan_1_front"

    def test_keeps_underscores_and_digits(self) -> None:
        assert util.generate_sensor_id("PSU_1_VIN") == "psu_1_vin"


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
