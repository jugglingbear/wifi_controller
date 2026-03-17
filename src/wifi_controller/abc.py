"""Abstract base classes for Wi-Fi provider plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod

from wifi_controller.types import SSIDInfo


class CurrentSSIDProvider(ABC):
    """Can retrieve the SSID of the currently-connected network."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def get_current_ssid(self, interface: str) -> str | None: ...


class SSIDScanProvider(ABC):
    """Can scan for nearby Wi-Fi networks and return real (non-redacted) SSIDs."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]: ...


class SSIDConnectProvider(ABC):
    """Can connect to a Wi-Fi network given SSID and password.

    :raises WiFiConnectionError: on failure
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def connect(self, ssid: str, password: str, interface: str, timeout: int = 15) -> None: ...


class SSIDDisconnectProvider(ABC):
    """Can disconnect from the current Wi-Fi network."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def disconnect(self, interface: str) -> None: ...
