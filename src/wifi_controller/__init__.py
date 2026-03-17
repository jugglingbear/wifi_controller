"""Cross-platform Wi-Fi controller with pluggable providers.

Detects the current OS and registers known-good providers automatically.
External code can register additional providers (e.g., a Swift-based scanner
for macOS SSID redaction workarounds).

Usage::

    from wifi_controller import WiFiController

    wifi = WiFiController()
    ssid = wifi.get_current_ssid()
    networks = wifi.scan()
    wifi.connect("MyNetwork", "hunter2")
    wifi.disconnect()

    # Poll for a specific SSID
    found = wifi.scan_for_ssid("TestAP 5678", timeout_sec=30)
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from bear_tools.lumberjack import Logger

from wifi_controller.abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller.linux import (
    IwgetidCurrentSSID,
    NmcliConnect,
    NmcliCurrentSSID,
    NmcliDisconnect,
    NmcliScan,
)
from wifi_controller.macos import (
    IpconfigCurrentSSID,
    NetworkSetupConnect,
    NetworkSetupCurrentSSID,
    NetworkSetupDisconnect,
    SystemProfilerScan,
)
from wifi_controller.types import SSIDInfo, WiFiConnectionError

logger = Logger()

__all__ = [
    "WiFiController",
    "SSIDInfo",
    "WiFiConnectionError",
    "CurrentSSIDProvider",
    "SSIDScanProvider",
    "SSIDConnectProvider",
    "SSIDDisconnectProvider",
]


@dataclass
class _RegisteredProvider:
    provider: CurrentSSIDProvider | SSIDScanProvider | SSIDConnectProvider | SSIDDisconnectProvider
    priority: int


class WiFiController:
    """Orchestrates Wi-Fi operations across pluggable, per-operation providers.

    On construction, detects the OS and registers built-in providers that are
    known to work on that platform/version.  If no provider is available for a
    given operation, a warning is logged so the caller knows to register their
    own.

    :param interface: Network interface name.  Auto-detected if ``None``.
    :param cache_path: Optional JSON file to persist provider selections across runs.
    """

    def __init__(
        self,
        interface: str | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._current_providers: list[_RegisteredProvider] = []
        self._scan_providers: list[_RegisteredProvider] = []
        self._connect_providers: list[_RegisteredProvider] = []
        self._disconnect_providers: list[_RegisteredProvider] = []

        self._resolved_current: CurrentSSIDProvider | None = None
        self._resolved_scan: SSIDScanProvider | None = None
        self._resolved_connect: SSIDConnectProvider | None = None
        self._resolved_disconnect: SSIDDisconnectProvider | None = None

        self._cache_path = cache_path.expanduser() if cache_path else None
        self._cache: dict[str, str] = {}
        if self._cache_path and self._cache_path.exists():
            try:
                self._cache = json.loads(self._cache_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._cache = {}

        os_name = platform.system()
        self._interface = interface or self._detect_interface(os_name)
        self._os_name = os_name

        self._setup_builtin_providers(os_name)

    # -- Public properties --------------------------------------------------

    @property
    def platform_info(self) -> str:
        """Human-readable OS + version string."""
        ver = platform.mac_ver()[0]
        if ver:
            return f"macOS {ver} (Darwin)"
        return f"{platform.system()} {platform.release()}"

    @property
    def interface_name(self) -> str:
        """The network interface being used (e.g., ``en0``, ``wlan0``)."""
        return self._interface

    # -- Registration -------------------------------------------------------

    def register_current_ssid_provider(self, provider: CurrentSSIDProvider, priority: int = 0) -> None:
        self._current_providers.append(_RegisteredProvider(provider, priority))
        self._resolved_current = None

    def register_scan_provider(self, provider: SSIDScanProvider, priority: int = 0) -> None:
        self._scan_providers.append(_RegisteredProvider(provider, priority))
        self._resolved_scan = None

    def register_connect_provider(self, provider: SSIDConnectProvider, priority: int = 0) -> None:
        self._connect_providers.append(_RegisteredProvider(provider, priority))
        self._resolved_connect = None

    def register_disconnect_provider(self, provider: SSIDDisconnectProvider, priority: int = 0) -> None:
        self._disconnect_providers.append(_RegisteredProvider(provider, priority))
        self._resolved_disconnect = None

    # -- Core operations ----------------------------------------------------

    def get_current_ssid(self) -> str | None:
        """Return the SSID of the currently-connected network, or ``None``."""
        provider = self._resolve("current", self._current_providers, self._resolved_current)
        self._resolved_current = provider  # type: ignore[assignment]
        if provider is None:
            logger.warning("No current-SSID provider registered. Call register_current_ssid_provider() first.")
            return None
        return provider.get_current_ssid(self._interface)  # type: ignore[union-attr]

    def scan(self, timeout: int = 15) -> list[SSIDInfo]:
        """Scan for nearby Wi-Fi networks."""
        provider = self._resolve("scan", self._scan_providers, self._resolved_scan)
        self._resolved_scan = provider  # type: ignore[assignment]
        if provider is None:
            logger.warning("No scan provider registered. Call register_scan_provider() first.")
            return []
        return provider.scan_ssids(self._interface, timeout)  # type: ignore[union-attr]

    def connect(self, ssid: str, password: str, timeout: int = 15) -> None:
        """Connect to a Wi-Fi network.

        :raises WiFiConnectionError: on failure
        """
        # ── Already-connected guard ──────────────────────────────────────
        # On macOS, calling CoreWLAN's CWInterface.associate(to:password:)
        # when the adapter is *already* associated with the target SSID
        # results in Apple80211 error -3925 ("tmpErr").  The error itself
        # is harmless, but the failed associate causes macOS to briefly
        # drop the WiFi link.  When a second network interface is active
        # (e.g. Ethernet on en7, VPN on utun1), macOS re-evaluates its
        # routing table during the dropout and may permanently re-route
        # the camera's subnet (10.5.5.0/24) through the other interface.
        # After that, Python's `requests` library (which uses BSD sockets
        # and relies on the kernel routing table) gets [Errno 65] EHOSTUNREACH,
        # while Apple's `curl` (which uses Network.framework with scoped
        # routing and per-interface DNS) continues to work — leading to
        # a confusing state where `is_reachable()` passes but every HTTP
        # call from `requests` fails.
        #
        # The same issue applies to `networksetup -setairportnetwork`:
        # re-running it on an already-connected SSID forces a full
        # reassociation with the access point (~9 seconds), during which
        # routing can shift to another interface.
        #
        # Fix: skip the connect entirely if we're already on the target.
        # ────────────────────────────────────────────────────────────────
        current = self.get_current_ssid()
        if current == ssid:
            logger.info(f"Already connected to '{ssid}', skipping connect")
            return

        provider = self._resolve("connect", self._connect_providers, self._resolved_connect)
        self._resolved_connect = provider  # type: ignore[assignment]
        if provider is None:
            raise WiFiConnectionError("No connect provider registered")
        provider.connect(ssid, password, self._interface, timeout)  # type: ignore[union-attr]

    def disconnect(self) -> None:
        """Disconnect from the current Wi-Fi network."""
        provider = self._resolve("disconnect", self._disconnect_providers, self._resolved_disconnect)
        self._resolved_disconnect = provider  # type: ignore[assignment]
        if provider is None:
            logger.warning("No disconnect provider registered.")
            return
        provider.disconnect(self._interface)  # type: ignore[union-attr]

    # -- Convenience methods ------------------------------------------------

    def scan_for_ssid(self, ssid: str, timeout_sec: float = 20.0, invert: bool = False) -> bool:
        """Poll ``scan()`` until *ssid* is found (or confirmed absent if *invert* is True).

        :param ssid: The SSID to look for.
        :param timeout_sec: Total time to keep trying (seconds).
        :param invert: If True, return True only if the SSID is **not** found after the timeout.
        :return: True if the SSID was found (or not found when *invert* is True).
        """
        logger.info(f'Scanning for SSID: "{ssid}" (timeout: {timeout_sec:.2f} seconds)')
        start = time.perf_counter()
        while time.perf_counter() - start <= timeout_sec:
            networks = self.scan(timeout=5)
            found = any(n.ssid == ssid for n in networks)
            if found and not invert:
                return True
            if not found and invert:
                return True
            time.sleep(1.0)
        return invert

    def is_connected(self) -> bool:
        """Return True if connected to any Wi-Fi network."""
        return self.get_current_ssid() is not None

    def is_wifi_enabled(self) -> bool:
        """Check whether the system's Wi-Fi adapter is powered on."""
        if self._os_name == "Darwin":
            try:
                out = subprocess.check_output(
                    ["networksetup", "-getairportpower", self._interface],
                    text=True,
                    timeout=5,
                )
                return "On" in out
            except (OSError, subprocess.SubprocessError):
                return True  # assume on if we can't check
        if self._os_name == "Linux":
            try:
                out = subprocess.check_output(["nmcli", "radio", "wifi"], text=True, timeout=5)
                return "enabled" in out.lower()
            except (OSError, subprocess.SubprocessError):
                return True
        return True  # unknown platform -- assume on

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _detect_interface(os_name: str) -> str:
        if os_name == "Darwin":
            return "en0"
        if os_name == "Linux":
            try:
                for p in sorted(Path("/sys/class/net").iterdir()):
                    if (p / "wireless").exists():
                        return p.name
            except OSError:
                pass
            return "wlan0"
        return "Wi-Fi"  # Windows default

    def _setup_builtin_providers(self, os_name: str) -> None:
        if os_name == "Darwin":
            self._setupmacos()
        elif os_name == "Linux":
            self._setuplinux()
        else:
            logger.warning(f"Unsupported platform: {os_name}. No Wi-Fi providers registered.")

    def _setupmacos(self) -> None:
        major = macos_major()

        if major <= 14:
            self.register_current_ssid_provider(NetworkSetupCurrentSSID(), priority=0)
            self.register_scan_provider(SystemProfilerScan(), priority=0)
        else:
            self.register_current_ssid_provider(IpconfigCurrentSSID(), priority=0)
            logger.warning(
                f"No built-in SSID scan provider for macOS {platform.mac_ver()[0]}. "
                "SSIDs are redacted by the OS. Register a scan provider "
                "(e.g., SwiftSsidScanner from extras/) to enable scanning."
            )

        self.register_connect_provider(NetworkSetupConnect(), priority=0)
        self.register_disconnect_provider(NetworkSetupDisconnect(), priority=0)

    def _setuplinux(self) -> None:
        has_nmcli = NmcliCurrentSSID().is_available()
        has_iwgetid = IwgetidCurrentSSID().is_available()

        if has_nmcli:
            self.register_current_ssid_provider(NmcliCurrentSSID(), priority=10)
            self.register_scan_provider(NmcliScan(), priority=0)
            self.register_connect_provider(NmcliConnect(), priority=0)
            self.register_disconnect_provider(NmcliDisconnect(), priority=0)
        if has_iwgetid:
            self.register_current_ssid_provider(IwgetidCurrentSSID(), priority=0)

        if not has_nmcli and not has_iwgetid:
            logger.warning(
                "No supported WiFi manager found on Linux. "
                "Install NetworkManager (nmcli) or wireless-tools (iwgetid)."
            )

    def _resolve(
        self,
        operation: str,
        registry: list[_RegisteredProvider],
        cached_instance: CurrentSSIDProvider | SSIDScanProvider | SSIDConnectProvider | SSIDDisconnectProvider | None,
    ) -> CurrentSSIDProvider | SSIDScanProvider | SSIDConnectProvider | SSIDDisconnectProvider | None:
        if cached_instance is not None:
            return cached_instance

        # Try to restore from disk cache
        cached_name = self._cache.get(operation)
        if cached_name:
            for entry in registry:
                if entry.provider.name == cached_name:
                    return entry.provider

        # Discovery: try providers in descending priority order
        for entry in sorted(registry, key=lambda e: e.priority, reverse=True):
            if entry.provider.is_available():
                self._cache[operation] = entry.provider.name
                self._write_cache()
                return entry.provider

        return None

    def _write_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, indent=2) + "\n")
        except OSError:
            pass


def macos_major() -> int:
    ver = platform.mac_ver()[0]
    return int(ver.split(".")[0]) if ver else 0
