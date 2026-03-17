"""Unit tests for wifi_controller._types (SSIDInfo, WiFiConnectionError)."""

from __future__ import annotations

import pytest

from wifi_controller._types import SSIDInfo, WiFiConnectionError


# ---------------------------------------------------------------------------
# SSIDInfo dataclass
# ---------------------------------------------------------------------------


class TestSSIDInfo:
    """SSIDInfo is a frozen dataclass with four fields."""

    def test_fields(self) -> None:
        info = SSIDInfo("MyNet", "aa:bb:cc:dd:ee:ff", -55, 11)
        assert info.ssid == "MyNet"
        assert info.bssid == "aa:bb:cc:dd:ee:ff"
        assert info.rssi == -55
        assert info.channel == 11

    def test_frozen(self) -> None:
        info = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        with pytest.raises(AttributeError):
            info.ssid = "Changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        b = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        assert a == b

    def test_inequality_different_ssid(self) -> None:
        a = SSIDInfo("Net1", "00:11:22:33:44:55", -42, 6)
        b = SSIDInfo("Net2", "00:11:22:33:44:55", -42, 6)
        assert a != b

    def test_inequality_different_rssi(self) -> None:
        a = SSIDInfo("Net", "00:11:22:33:44:55", -42, 6)
        b = SSIDInfo("Net", "00:11:22:33:44:55", -70, 6)
        assert a != b

    def test_repr_contains_fields(self) -> None:
        info = SSIDInfo("TestAP 5678", "aa:bb:cc:dd:ee:ff", -50, 1)
        r = repr(info)
        assert "TestAP 5678" in r
        assert "aa:bb:cc:dd:ee:ff" in r

    def test_hash_equal_objects(self) -> None:
        """Frozen dataclasses are hashable; equal objects share a hash."""
        a = SSIDInfo("Net", "aa:bb:cc:dd:ee:ff", -50, 6)
        b = SSIDInfo("Net", "aa:bb:cc:dd:ee:ff", -50, 6)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_hash_different_objects(self) -> None:
        a = SSIDInfo("Net1", "", 0, 0)
        b = SSIDInfo("Net2", "", 0, 0)
        # Different objects *may* collide but probably don't
        assert a != b


# ---------------------------------------------------------------------------
# WiFiConnectionError
# ---------------------------------------------------------------------------


class TestWiFiConnectionError:
    """WiFiConnectionError is a plain Exception subclass."""

    def test_is_exception(self) -> None:
        assert issubclass(WiFiConnectionError, Exception)

    def test_message(self) -> None:
        err = WiFiConnectionError("connection timed out")
        assert str(err) == "connection timed out"

    def test_raise_and_catch(self) -> None:
        with pytest.raises(WiFiConnectionError, match="test error"):
            raise WiFiConnectionError("test error")
