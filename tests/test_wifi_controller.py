"""Unit tests for WiFiController provider resolution and registration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wifi_controller import WiFiConnectionError, WiFiController
from wifi_controller.abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller.types import SSIDInfo

# -- Fake providers for testing ---------------------------------------------

class FakeCurrentSSID(CurrentSSIDProvider):
    def __init__(self, ssid: str | None = "TestNet", available: bool = True) -> None:
        self._ssid = ssid
        self._available = available

    @property
    def name(self) -> str:
        return "fake_current"

    def is_available(self) -> bool:
        return self._available

    def get_current_ssid(self, interface: str) -> str | None:
        return self._ssid


class FakeScan(SSIDScanProvider):
    def __init__(self, networks: list[SSIDInfo] | None = None, available: bool = True) -> None:
        self._networks = networks or []
        self._available = available

    @property
    def name(self) -> str:
        return "fake_scan"

    def is_available(self) -> bool:
        return self._available

    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]:
        return self._networks


class FakeConnect(SSIDConnectProvider):
    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self._available = available
        self._fail = fail
        self.last_ssid: str | None = None

    @property
    def name(self) -> str:
        return "fake_connect"

    def is_available(self) -> bool:
        return self._available

    def connect(self, ssid: str, password: str, interface: str, timeout: int = 15) -> None:
        self.last_ssid = ssid
        if self._fail:
            raise WiFiConnectionError(f"Fake failure for '{ssid}'")


class FakeDisconnect(SSIDDisconnectProvider):
    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.called = False

    @property
    def name(self) -> str:
        return "fake_disconnect"

    def is_available(self) -> bool:
        return self._available

    def disconnect(self, interface: str) -> None:
        self.called = True


# -- Fixtures ---------------------------------------------------------------

@pytest.fixture
def ctrl() -> WiFiController:
    """WiFiController with no built-in providers (mocked OS detection)."""
    with patch("wifi_controller.platform") as mock_platform:
        mock_platform.system.return_value = "TestOS"
        mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
        mock_platform.release.return_value = "1.0"
        return WiFiController(interface="test0")


# -- Tests ------------------------------------------------------------------

class TestRegistration:
    def test_register_and_resolve_current(self, ctrl: WiFiController) -> None:
        provider = FakeCurrentSSID("MyNet")
        ctrl.register_current_ssid_provider(provider, priority=0)
        assert ctrl.get_current_ssid() == "MyNet"

    def test_register_and_resolve_scan(self, ctrl: WiFiController) -> None:
        networks = [SSIDInfo("Net1", "00:11:22:33:44:55", -42, 6)]
        provider = FakeScan(networks)
        ctrl.register_scan_provider(provider, priority=0)
        result = ctrl.scan()
        assert len(result) == 1
        assert result[0].ssid == "Net1"

    def test_register_and_resolve_connect(self, ctrl: WiFiController) -> None:
        provider = FakeConnect()
        ctrl.register_connect_provider(provider, priority=0)
        ctrl.connect("TestNet", "password123")
        assert provider.last_ssid == "TestNet"

    def test_register_and_resolve_disconnect(self, ctrl: WiFiController) -> None:
        provider = FakeDisconnect()
        ctrl.register_disconnect_provider(provider, priority=0)
        ctrl.disconnect()
        assert provider.called


class TestPriorityResolution:
    def test_higher_priority_wins(self, ctrl: WiFiController) -> None:
        low = FakeCurrentSSID("LowPriority")
        high = FakeCurrentSSID("HighPriority")
        ctrl.register_current_ssid_provider(low, priority=0)
        ctrl.register_current_ssid_provider(high, priority=10)
        assert ctrl.get_current_ssid() == "HighPriority"

    def test_unavailable_provider_skipped(self, ctrl: WiFiController) -> None:
        unavailable = FakeCurrentSSID("Unavailable", available=False)
        available = FakeCurrentSSID("Available")
        ctrl.register_current_ssid_provider(unavailable, priority=10)
        ctrl.register_current_ssid_provider(available, priority=0)
        assert ctrl.get_current_ssid() == "Available"


class TestNoProviders:
    def test_get_current_ssid_returns_none(self, ctrl: WiFiController) -> None:
        assert ctrl.get_current_ssid() is None

    def test_scan_returns_empty(self, ctrl: WiFiController) -> None:
        assert ctrl.scan() == []

    def test_connect_raises(self, ctrl: WiFiController) -> None:
        with pytest.raises(WiFiConnectionError, match="No connect provider"):
            ctrl.connect("Test", "pass")


class TestConvenienceMethods:
    def test_is_connected_true(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID("Net"))
        assert ctrl.is_connected() is True

    def test_is_connected_false(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID(None))
        assert ctrl.is_connected() is False

    def test_connect_error_propagates(self, ctrl: WiFiController) -> None:
        ctrl.register_connect_provider(FakeConnect(fail=True))
        with pytest.raises(WiFiConnectionError, match="Fake failure"):
            ctrl.connect("BadNet", "pass")


class TestSSIDInfo:
    def test_frozen(self) -> None:
        info = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        with pytest.raises(AttributeError):
            info.ssid = "Changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        b = SSIDInfo("Test", "00:11:22:33:44:55", -42, 6)
        assert a == b

    def test_fields(self) -> None:
        info = SSIDInfo("MyNet", "aa:bb:cc:dd:ee:ff", -55, 11)
        assert info.ssid == "MyNet"
        assert info.bssid == "aa:bb:cc:dd:ee:ff"
        assert info.rssi == -55
        assert info.channel == 11
