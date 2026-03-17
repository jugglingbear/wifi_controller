"""Wi-Fi providers backed by the Swift ``ssid_scanner`` binary.

These providers shell out to the signed macOS app bundle that uses
CoreWLAN + CoreLocation to bypass macOS SSID redaction (macOS 15+).

The Swift source lives in ``extras/ssid_scanner/`` and must be built
separately (``make -C extras/ssid_scanner``). The Python wrappers here
ship on PyPI and gracefully report ``is_available() -> False`` when the
binary is not present.

Usage::

    from wifi_controller import WiFiController
    from wifi_controller._swift import (
        SwiftSsidScannerCurrentSSID,
        SwiftSsidScannerScan,
        SwiftSsidScannerConnect,
        SwiftSsidScannerDisconnect,
    )

    ctrl = WiFiController()
    binary = "/path/to/ssid_scanner"
    ctrl.register_current_ssid_provider(SwiftSsidScannerCurrentSSID(binary), priority=10)
    ctrl.register_scan_provider(SwiftSsidScannerScan(binary), priority=10)
    ctrl.register_connect_provider(SwiftSsidScannerConnect(binary), priority=10)
    ctrl.register_disconnect_provider(SwiftSsidScannerDisconnect(binary), priority=10)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from bear_tools.lumberjack import Logger

from wifi_controller._abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller._types import SSIDInfo, WiFiConnectionError

logger = Logger()


class SwiftSsidScannerCurrentSSID(CurrentSSIDProvider):
    """Retrieve the current SSID via ``ssid_scanner --current``."""

    def __init__(self, binary: str | Path) -> None:
        self._binary = str(binary)

    @property
    def name(self) -> str:
        return "swift_ssid_scanner"

    def is_available(self) -> bool:
        return Path(self._binary).is_file()

    def get_current_ssid(self, interface: str = "en0") -> str | None:
        try:
            result = subprocess.run(
                [self._binary, "--current"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        if result.returncode != 0:
            return None
        ssid = result.stdout.strip()
        return ssid if ssid else None


class SwiftSsidScannerScan(SSIDScanProvider):
    """Scan nearby networks via ``ssid_scanner --scan --json``."""

    def __init__(self, binary: str | Path) -> None:
        self._binary = str(binary)

    @property
    def name(self) -> str:
        return "swift_ssid_scanner"

    def is_available(self) -> bool:
        return Path(self._binary).is_file()

    def scan_ssids(self, interface: str = "en0", timeout: int = 15) -> list[SSIDInfo]:
        try:
            result = subprocess.run(
                [self._binary, "--scan", "--json", "--timeout", str(timeout)],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []
        if result.returncode != 0:
            return []
        try:
            raw: list[dict[str, str | int]] = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return []
        return [
            SSIDInfo(
                ssid=str(entry.get("ssid", "")),
                bssid=str(entry.get("bssid", "")),
                rssi=int(entry.get("rssi", 0)),
                channel=int(entry.get("channel", 0)),
            )
            for entry in raw
        ]


class SwiftSsidScannerConnect(SSIDConnectProvider):
    """Connect to a network via ``ssid_scanner --connect``."""

    def __init__(self, binary: str | Path) -> None:
        self._binary = str(binary)

    @property
    def name(self) -> str:
        return "swift_ssid_scanner"

    def is_available(self) -> bool:
        return Path(self._binary).is_file()

    def connect(self, ssid: str, password: str, interface: str = "en0", timeout: int = 15) -> None:
        # ── Already-connected guard ──────────────────────────────────
        # CoreWLAN's CWInterface.associate(to:password:) fails with
        # Apple80211 error -3925 when already on the target SSID.
        # The failed associate drops the WiFi link momentarily, which
        # causes macOS to re-route the camera's 10.5.5.0/24 subnet
        # through another interface (Ethernet, VPN) if one exists.
        # Python `requests` then gets EHOSTUNREACH while `curl` still
        # works (Network.framework vs BSD sockets).  See the detailed
        # comment in WiFiController.connect() for the full explanation.
        # ─────────────────────────────────────────────────────────────
        current = self._get_current_ssid()
        if current == ssid:
            logger.info(f"Already connected to '{ssid}', skipping ssid_scanner --connect")
            return

        try:
            result = subprocess.run(
                [self._binary, "--connect", ssid, password, "--timeout", str(timeout)],
                capture_output=True,
                text=True,
                timeout=timeout + 30,
            )
        except subprocess.TimeoutExpired as exc:
            raise WiFiConnectionError(f"ssid_scanner timed out connecting to '{ssid}'") from exc
        except (FileNotFoundError, OSError) as exc:
            raise WiFiConnectionError(f"ssid_scanner binary not found: {self._binary}") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise WiFiConnectionError(f"ssid_scanner failed to connect to '{ssid}': {stderr}")

    def _get_current_ssid(self) -> str | None:
        """Quick check via ``ssid_scanner --current``."""
        try:
            result = subprocess.run(
                [self._binary, "--current"],
                capture_output=True, text=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        return result.stdout.strip() or None if result.returncode == 0 else None


class SwiftSsidScannerDisconnect(SSIDDisconnectProvider):
    """Disconnect from the current network via ``ssid_scanner --disconnect``."""

    def __init__(self, binary: str | Path) -> None:
        self._binary = str(binary)

    @property
    def name(self) -> str:
        return "swift_ssid_scanner"

    def is_available(self) -> bool:
        return Path(self._binary).is_file()

    def disconnect(self, interface: str = "en0") -> None:
        try:
            result = subprocess.run(
                [self._binary, "--disconnect"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return  # best-effort
        if result.returncode != 0:
            logger.warning(f"ssid_scanner --disconnect failed: {result.stderr.strip()}")
