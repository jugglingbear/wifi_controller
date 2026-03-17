"""Built-in macOS Wi-Fi providers."""

from __future__ import annotations

import platform
import re
import subprocess

from bear_tools.lumberjack import Logger

from wifi_controller._abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller._types import SSIDInfo, WiFiConnectionError

logger = Logger()


def _macos_major_version() -> int:
    ver = platform.mac_ver()[0]
    return int(ver.split(".")[0]) if ver else 0


class NetworkSetupCurrentSSID(CurrentSSIDProvider):
    """``networksetup -getairportnetwork`` -- works on macOS <= 14."""

    @property
    def name(self) -> str:
        return "networksetup"

    def is_available(self) -> bool:
        return _macos_major_version() <= 14

    def get_current_ssid(self, interface: str) -> str | None:
        try:
            output = subprocess.check_output(
                ["networksetup", "-getairportnetwork", interface],
            ).decode()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        prefix = "Current Wi-Fi Network: "
        if prefix in output:
            return output.replace(prefix, "").strip()
        return None


class IpconfigCurrentSSID(CurrentSSIDProvider):
    """``ipconfig getsummary`` -- works on macOS 15+ (requires ``sudo ipconfig setverbose 1`` once)."""

    @property
    def name(self) -> str:
        return "ipconfig"

    def is_available(self) -> bool:
        return _macos_major_version() >= 15

    def get_current_ssid(self, interface: str) -> str | None:
        try:
            output = subprocess.check_output(["ipconfig", "getsummary", interface]).decode()
            regex = r"\n\s+SSID : ([\x20-\x7E]{1,32})(?=\n)"
            match = re.search(regex, output)
            return match.group(1) if match else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None


class SystemProfilerScan(SSIDScanProvider):
    """``system_profiler SPAirPortDataType`` -- works on macOS <= 14 (SSIDs redacted on 15+)."""

    @property
    def name(self) -> str:
        return "system_profiler"

    def is_available(self) -> bool:
        return _macos_major_version() <= 14

    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]:
        try:
            output = subprocess.check_output(["/usr/sbin/system_profiler", "SPAirPortDataType"]).decode()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        regex = re.compile(r"\n\s+([\x20-\x7E]{1,32}):\n\s+PHY Mode:")
        return [
            SSIDInfo(ssid=ssid, bssid="", rssi=0, channel=0)
            for ssid in sorted(set(regex.findall(output)))
        ]


class NetworkSetupConnect(SSIDConnectProvider):
    """``networksetup -setairportnetwork`` -- works on all macOS versions with explicit password."""

    @property
    def name(self) -> str:
        return "networksetup"

    def is_available(self) -> bool:
        return platform.system() == "Darwin"

    def connect(self, ssid: str, password: str, interface: str, timeout: int = 15) -> None:
        # ── Already-connected guard ──────────────────────────────────
        # `networksetup -setairportnetwork` forces a full 802.11
        # reassociation even when already on the target SSID (~9 sec).
        # During reassociation, macOS may re-route the camera's
        # 10.5.5.0/24 subnet through Ethernet/VPN if a second
        # interface is active, breaking Python BSD-socket traffic.
        # See WiFiController.connect() for the full explanation.
        # ─────────────────────────────────────────────────────────────
        current = self._get_current_ssid(interface)
        if current == ssid:
            logger.info(f"Already connected to '{ssid}', skipping networksetup")
            return

        try:
            result = subprocess.run(
                ["networksetup", "-setairportnetwork", interface, ssid, password],
                capture_output=True,
                text=True,
                timeout=timeout + 15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise WiFiConnectionError(f"networksetup failed for '{ssid}': {exc}") from exc
        if result.stdout.strip():
            raise WiFiConnectionError(f"networksetup failed for '{ssid}': {result.stdout.strip()}")

    @staticmethod
    def _get_current_ssid(interface: str) -> str | None:
        """Quick SSID check via ipconfig (works on macOS 15+)."""
        try:
            output = subprocess.check_output(
                ["ipconfig", "getsummary", interface], text=True, timeout=5,
            )
            match = re.search(r"\n\s+SSID : ([\x20-\x7E]{1,32})(?=\n)", output)
            return match.group(1) if match else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None


class NetworkSetupDisconnect(SSIDDisconnectProvider):
    """``networksetup -setairportpower`` off/on to disconnect."""

    @property
    def name(self) -> str:
        return "networksetup"

    def is_available(self) -> bool:
        return platform.system() == "Darwin"

    def disconnect(self, interface: str) -> None:
        try:
            subprocess.run(
                ["networksetup", "-setairportpower", interface, "off"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["networksetup", "-setairportpower", interface, "on"],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
