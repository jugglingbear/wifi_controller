"""Built-in Linux Wi-Fi providers (nmcli, iwgetid)."""

from __future__ import annotations

import contextlib
import shutil
import subprocess

from wifi_controller.abc import (
    CurrentSSIDProvider,
    SSIDConnectProvider,
    SSIDDisconnectProvider,
    SSIDScanProvider,
)
from wifi_controller.types import SSIDInfo, WiFiConnectionError


def _has_nmcli() -> bool:
    return shutil.which("nmcli") is not None


def _has_iwgetid() -> bool:
    return shutil.which("iwgetid") is not None


class NmcliCurrentSSID(CurrentSSIDProvider):
    """``nmcli`` -- active SSID on Linux with NetworkManager."""

    @property
    def name(self) -> str:
        return "nmcli"

    def is_available(self) -> bool:
        return _has_nmcli()

    def get_current_ssid(self, interface: str) -> str | None:
        try:
            output = subprocess.check_output(
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        for line in output.splitlines():
            if line.startswith("yes:"):
                ssid = line.split(":", 1)[1]
                return ssid if ssid else None
        return None


class NmcliScan(SSIDScanProvider):
    """``nmcli dev wifi list`` -- scan nearby networks on Linux."""

    @property
    def name(self) -> str:
        return "nmcli"

    def is_available(self) -> bool:
        return _has_nmcli()

    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]:
        try:
            # Trigger a fresh scan
            subprocess.run(
                ["nmcli", "dev", "wifi", "rescan", "ifname", interface],
                capture_output=True,
                timeout=timeout,
            )
            output = subprocess.check_output(
                ["nmcli", "-t", "-f", "ssid,bssid,signal,freq", "dev", "wifi", "list", "ifname", interface],
                text=True,
                timeout=timeout,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return []

        results: list[SSIDInfo] = []
        seen: set[str] = set()
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            ssid = parts[0]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            bssid = ":".join(parts[1:7]) if len(parts) >= 7 else parts[1]
            try:
                signal = int(parts[-2]) if len(parts) >= 4 else 0
                freq = int(parts[-1]) if len(parts) >= 4 else 0
            except ValueError:
                signal, freq = 0, 0
            # nmcli reports signal as 0-100%; approximate dBm
            rssi = signal - 100 if signal else 0
            channel = _freq_to_channel(freq)
            results.append(SSIDInfo(ssid=ssid, bssid=bssid, rssi=rssi, channel=channel))
        return results


class NmcliConnect(SSIDConnectProvider):
    """``nmcli dev wifi connect`` -- connect on Linux with NetworkManager."""

    @property
    def name(self) -> str:
        return "nmcli"

    def is_available(self) -> bool:
        return _has_nmcli()

    def connect(self, ssid: str, password: str, interface: str, timeout: int = 15) -> None:
        try:
            result = subprocess.run(
                ["nmcli", "dev", "wifi", "connect", ssid, "password", password, "ifname", interface],
                capture_output=True,
                text=True,
                timeout=timeout + 15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            raise WiFiConnectionError(f"nmcli failed for '{ssid}': {exc}") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise WiFiConnectionError(f"nmcli failed for '{ssid}': {stderr}")


class NmcliDisconnect(SSIDDisconnectProvider):
    """``nmcli dev disconnect`` -- disconnect on Linux."""

    @property
    def name(self) -> str:
        return "nmcli"

    def is_available(self) -> bool:
        return _has_nmcli()

    def disconnect(self, interface: str) -> None:
        with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
            subprocess.run(
                ["nmcli", "dev", "disconnect", interface],
                capture_output=True,
                timeout=10,
            )


class IwgetidCurrentSSID(CurrentSSIDProvider):
    """``iwgetid -r`` -- get current SSID on Linux without NetworkManager."""

    @property
    def name(self) -> str:
        return "iwgetid"

    def is_available(self) -> bool:
        return _has_iwgetid()

    def get_current_ssid(self, interface: str) -> str | None:
        try:
            output = subprocess.check_output(["iwgetid", "-r", interface], text=True).strip()
            return output if output else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None


def _freq_to_channel(freq_mhz: int) -> int:
    """Convert Wi-Fi frequency in MHz to channel number."""
    if 2412 <= freq_mhz <= 2484:
        if freq_mhz == 2484:
            return 14
        return (freq_mhz - 2412) // 5 + 1
    if 5170 <= freq_mhz <= 5825:
        return (freq_mhz - 5170) // 5 + 34
    return 0
