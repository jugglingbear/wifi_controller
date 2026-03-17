"""Unit tests for the macOS Wi-Fi providers (wifi_controller._macos)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from wifi_controller._macos import (
    IpconfigCurrentSSID,
    NetworkSetupConnect,
    NetworkSetupCurrentSSID,
    NetworkSetupDisconnect,
    SystemProfilerScan,
    _macos_major_version,
)
from wifi_controller._types import WiFiConnectionError


# ---------------------------------------------------------------------------
# _macos_major_version helper
# ---------------------------------------------------------------------------


class TestMacosMajorVersion:
    """_macos_major_version() parses platform.mac_ver()[0]."""

    def test_macos_15(self) -> None:
        with patch("wifi_controller._macos.platform.mac_ver", return_value=("15.5", ("", "", ""), "")):
            assert _macos_major_version() == 15

    def test_macos_14(self) -> None:
        with patch("wifi_controller._macos.platform.mac_ver", return_value=("14.3.1", ("", "", ""), "")):
            assert _macos_major_version() == 14

    def test_macos_13(self) -> None:
        with patch("wifi_controller._macos.platform.mac_ver", return_value=("13.7", ("", "", ""), "")):
            assert _macos_major_version() == 13

    def test_empty_returns_zero(self) -> None:
        with patch("wifi_controller._macos.platform.mac_ver", return_value=("", ("", "", ""), "")):
            assert _macos_major_version() == 0


# ---------------------------------------------------------------------------
# NetworkSetupCurrentSSID
# ---------------------------------------------------------------------------


class TestNetworkSetupCurrentSSID:
    """networksetup -getairportnetwork provider (macOS <= 14)."""

    def test_name(self) -> None:
        assert NetworkSetupCurrentSSID().name == "networksetup"

    def test_available_on_macos_14(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=14):
            assert NetworkSetupCurrentSSID().is_available() is True

    def test_unavailable_on_macos_15(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=15):
            assert NetworkSetupCurrentSSID().is_available() is False

    def test_parses_ssid(self) -> None:
        output = b"Current Wi-Fi Network: TestAP 5678\n"
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            assert NetworkSetupCurrentSSID().get_current_ssid("en0") == "TestAP 5678"

    def test_not_connected(self) -> None:
        output = b"You are not associated with an AirPort network.\n"
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            assert NetworkSetupCurrentSSID().get_current_ssid("en0") is None

    def test_command_fails(self) -> None:
        with patch(
            "wifi_controller._macos.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "networksetup"),
        ):
            assert NetworkSetupCurrentSSID().get_current_ssid("en0") is None

    def test_binary_not_found(self) -> None:
        with patch("wifi_controller._macos.subprocess.check_output", side_effect=FileNotFoundError):
            assert NetworkSetupCurrentSSID().get_current_ssid("en0") is None


# ---------------------------------------------------------------------------
# IpconfigCurrentSSID
# ---------------------------------------------------------------------------


class TestIpconfigCurrentSSID:
    """ipconfig getsummary provider (macOS 15+)."""

    def test_name(self) -> None:
        assert IpconfigCurrentSSID().name == "ipconfig"

    def test_available_on_macos_15(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=15):
            assert IpconfigCurrentSSID().is_available() is True

    def test_unavailable_on_macos_14(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=14):
            assert IpconfigCurrentSSID().is_available() is False

    def test_parses_ssid_from_getsummary(self) -> None:
        output = (
            b"<dictionary> {\n"
            b"  IPv4 : <array> {\n"
            b"  }\n"
            b"\n"
            b"  SSID : TestAP 5678\n"
            b"  BSSID : aa:bb:cc:dd:ee:ff\n"
            b"}\n"
        )
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            assert IpconfigCurrentSSID().get_current_ssid("en0") == "TestAP 5678"

    def test_no_ssid_in_output(self) -> None:
        output = b"<dictionary> {\n  IPv4 : <array> {\n  }\n}\n"
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            assert IpconfigCurrentSSID().get_current_ssid("en0") is None

    def test_command_fails(self) -> None:
        with patch(
            "wifi_controller._macos.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "ipconfig"),
        ):
            assert IpconfigCurrentSSID().get_current_ssid("en0") is None

    def test_binary_not_found(self) -> None:
        with patch("wifi_controller._macos.subprocess.check_output", side_effect=FileNotFoundError):
            assert IpconfigCurrentSSID().get_current_ssid("en0") is None


# ---------------------------------------------------------------------------
# SystemProfilerScan
# ---------------------------------------------------------------------------


class TestSystemProfilerScan:
    """system_profiler SPAirPortDataType scan provider (macOS <= 14)."""

    def test_name(self) -> None:
        assert SystemProfilerScan().name == "system_profiler"

    def test_available_on_macos_14(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=14):
            assert SystemProfilerScan().is_available() is True

    def test_unavailable_on_macos_15(self) -> None:
        with patch("wifi_controller._macos._macos_major_version", return_value=15):
            assert SystemProfilerScan().is_available() is False

    def test_parses_networks(self) -> None:
        output = (
            b"Wi-Fi:\n"
            b"\n"
            b"  Other Local Wi-Fi Networks:\n"
            b"\n"
            b"    TestAP 5678:\n"
            b"      PHY Mode: 802.11ac\n"
            b"      Channel: 6\n"
            b"\n"
            b"    HomeNet:\n"
            b"      PHY Mode: 802.11ax\n"
            b"      Channel: 36\n"
        )
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            results = SystemProfilerScan().scan_ssids("en0")
        ssids = [r.ssid for r in results]
        assert "TestAP 5678" in ssids
        assert "HomeNet" in ssids

    def test_deduplicates(self) -> None:
        output = (
            b"\n"
            b"    DupeNet:\n"
            b"      PHY Mode: 802.11ac\n"
            b"\n"
            b"    DupeNet:\n"
            b"      PHY Mode: 802.11ac\n"
        )
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            results = SystemProfilerScan().scan_ssids("en0")
        assert len(results) == 1
        assert results[0].ssid == "DupeNet"

    def test_empty_output(self) -> None:
        with patch("wifi_controller._macos.subprocess.check_output", return_value=b""):
            assert SystemProfilerScan().scan_ssids("en0") == []

    def test_command_fails(self) -> None:
        with patch(
            "wifi_controller._macos.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "system_profiler"),
        ):
            assert SystemProfilerScan().scan_ssids("en0") == []

    def test_results_sorted(self) -> None:
        output = (
            b"\n"
            b"    Zebra:\n"
            b"      PHY Mode: 802.11ac\n"
            b"\n"
            b"    Alpha:\n"
            b"      PHY Mode: 802.11ac\n"
        )
        with patch("wifi_controller._macos.subprocess.check_output", return_value=output):
            results = SystemProfilerScan().scan_ssids("en0")
        assert results[0].ssid == "Alpha"
        assert results[1].ssid == "Zebra"


# ---------------------------------------------------------------------------
# NetworkSetupConnect
# ---------------------------------------------------------------------------


class TestNetworkSetupConnect:
    """networksetup -setairportnetwork connect provider."""

    def test_name(self) -> None:
        assert NetworkSetupConnect().name == "networksetup"

    def test_available_on_darwin(self) -> None:
        with patch("wifi_controller._macos.platform.system", return_value="Darwin"):
            assert NetworkSetupConnect().is_available() is True

    def test_unavailable_on_linux(self) -> None:
        with patch("wifi_controller._macos.platform.system", return_value="Linux"):
            assert NetworkSetupConnect().is_available() is False

    def test_successful_connect(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("wifi_controller._macos.subprocess.run", return_value=mock_result), \
             patch("wifi_controller._macos.subprocess.check_output", return_value="no SSID"):
            NetworkSetupConnect().connect("TestAP 5678", "password", "en0")

    def test_already_connected_skips(self) -> None:
        """Already-connected guard: if current SSID matches, skip the connect."""
        ipconfig_output = "\n  SSID : TestAP 5678\n  BSSID : aa:bb:cc:dd:ee:ff\n"
        with patch("wifi_controller._macos.subprocess.check_output", return_value=ipconfig_output) as mock_check, \
             patch("wifi_controller._macos.subprocess.run") as mock_run:
            NetworkSetupConnect().connect("TestAP 5678", "password", "en0")
        # subprocess.run (networksetup -setairportnetwork) should NOT be called
        mock_run.assert_not_called()

    def test_error_in_stdout_raises(self) -> None:
        mock_result = MagicMock()
        mock_result.stdout = "Could not find network 'BadNet'."
        with patch("wifi_controller._macos.subprocess.run", return_value=mock_result), \
             patch("wifi_controller._macos.subprocess.check_output", return_value="no SSID"):
            with pytest.raises(WiFiConnectionError, match="BadNet"):
                NetworkSetupConnect().connect("BadNet", "password", "en0")

    def test_timeout_raises(self) -> None:
        with patch("wifi_controller._macos.subprocess.check_output", return_value="no SSID"), \
             patch(
                 "wifi_controller._macos.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd="networksetup", timeout=30),
             ):
            with pytest.raises(WiFiConnectionError, match="networksetup failed"):
                NetworkSetupConnect().connect("Net", "pass", "en0")

    def test_binary_not_found_raises(self) -> None:
        with patch("wifi_controller._macos.subprocess.check_output", return_value="no SSID"), \
             patch("wifi_controller._macos.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(WiFiConnectionError, match="networksetup failed"):
                NetworkSetupConnect().connect("Net", "pass", "en0")


# ---------------------------------------------------------------------------
# NetworkSetupDisconnect
# ---------------------------------------------------------------------------


class TestNetworkSetupDisconnect:
    """networksetup -setairportpower off/on disconnect provider."""

    def test_name(self) -> None:
        assert NetworkSetupDisconnect().name == "networksetup"

    def test_available_on_darwin(self) -> None:
        with patch("wifi_controller._macos.platform.system", return_value="Darwin"):
            assert NetworkSetupDisconnect().is_available() is True

    def test_unavailable_on_linux(self) -> None:
        with patch("wifi_controller._macos.platform.system", return_value="Linux"):
            assert NetworkSetupDisconnect().is_available() is False

    def test_calls_power_off_then_on(self) -> None:
        with patch("wifi_controller._macos.subprocess.run") as mock_run:
            NetworkSetupDisconnect().disconnect("en0")
        assert mock_run.call_count == 2
        # First call: power off
        first_args = mock_run.call_args_list[0][0][0]
        assert first_args == ["networksetup", "-setairportpower", "en0", "off"]
        # Second call: power on
        second_args = mock_run.call_args_list[1][0][0]
        assert second_args == ["networksetup", "-setairportpower", "en0", "on"]

    def test_timeout_swallowed(self) -> None:
        """Disconnect is best-effort — timeouts are silently ignored."""
        with patch(
            "wifi_controller._macos.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="networksetup", timeout=10),
        ):
            NetworkSetupDisconnect().disconnect("en0")  # should not raise

    def test_file_not_found_swallowed(self) -> None:
        with patch("wifi_controller._macos.subprocess.run", side_effect=FileNotFoundError):
            NetworkSetupDisconnect().disconnect("en0")  # should not raise
