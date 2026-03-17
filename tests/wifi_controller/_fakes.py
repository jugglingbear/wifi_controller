"""Fake/stub providers for wifi_controller unit tests."""

from __future__ import annotations

from wifi_controller import WiFiConnectionError
from wifi_controller._abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller._types import SSIDInfo


class FakeCurrentSSID(CurrentSSIDProvider):
    """Stub current-SSID provider returning a configurable value."""

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
    """Stub scan provider returning a configurable network list."""

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
    """Stub connect provider that optionally raises WiFiConnectionError."""

    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self._available = available
        self._fail = fail
        self.last_ssid: str | None = None
        self.last_password: str | None = None
        self.call_count: int = 0

    @property
    def name(self) -> str:
        return "fake_connect"

    def is_available(self) -> bool:
        return self._available

    def connect(self, ssid: str, password: str, interface: str, timeout: int = 15) -> None:
        self.last_ssid = ssid
        self.last_password = password
        self.call_count += 1
        if self._fail:
            raise WiFiConnectionError(f"Fake failure for '{ssid}'")


class FakeDisconnect(SSIDDisconnectProvider):
    """Stub disconnect provider tracking invocations."""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.called = False
        self.call_count: int = 0

    @property
    def name(self) -> str:
        return "fake_disconnect"

    def is_available(self) -> bool:
        return self._available

    def disconnect(self, interface: str) -> None:
        self.called = True
        self.call_count += 1
