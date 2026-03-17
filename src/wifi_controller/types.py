"""Data types for the wifi_controller package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SSIDInfo:
    """Information about a discovered Wi-Fi network."""

    ssid: str
    bssid: str
    rssi: int
    channel: int


class WiFiConnectionError(Exception):
    """Raised when a Wi-Fi connect operation fails."""
