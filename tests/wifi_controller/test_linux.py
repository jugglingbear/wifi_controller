"""Unit tests for the Linux Wi-Fi providers (wifi_controller.linux)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from wifi_controller.linux import (
    IwgetidCurrentSSID,
    NmcliConnect,
    NmcliCurrentSSID,
    NmcliDisconnect,
    NmcliScan,
    _freq_to_channel,
)
from wifi_controller.types import WiFiConnectionError


# ---------------------------------------------------------------------------
# _freq_to_channel
# ---------------------------------------------------------------------------


class TestFreqToChannel:
    """Convert Wi-Fi frequency in MHz to channel number."""

    def test_2_4ghz_channel_1(self) -> None:
        assert _freq_to_channel(2412) == 1

    def test_2_4ghz_channel_6(self) -> None:
        assert _freq_to_channel(2437) == 6

    def test_2_4ghz_channel_11(self) -> None:
        assert _freq_to_channel(2462) == 11

    def test_2_4ghz_channel_14(self) -> None:
        assert _freq_to_channel(2484) == 14

    def test_5ghz_channel_36(self) -> None:
        assert _freq_to_channel(5180) == 36

    def test_5ghz_channel_44(self) -> None:
        assert _freq_to_channel(5220) == 44

    def test_5ghz_channel_165(self) -> None:
        assert _freq_to_channel(5825) == 165

    def test_unknown_frequency(self) -> None:
        assert _freq_to_channel(0) == 0

    def test_out_of_range(self) -> None:
        assert _freq_to_channel(9999) == 0

    def test_between_bands(self) -> None:
        assert _freq_to_channel(3000) == 0


# ---------------------------------------------------------------------------
# NmcliCurrentSSID
# ---------------------------------------------------------------------------


class TestNmcliCurrentSSID:
    """nmcli current SSID provider."""

    def test_name(self) -> None:
        assert NmcliCurrentSSID().name == "nmcli"

    def test_available_when_nmcli_exists(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value="/usr/bin/nmcli"):
            assert NmcliCurrentSSID().is_available() is True

    def test_unavailable_when_nmcli_missing(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value=None):
            assert NmcliCurrentSSID().is_available() is False

    def test_parses_active_ssid(self) -> None:
        output = "yes:TestAP 5678\nno:HomeNet\n"
        with patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            assert NmcliCurrentSSID().get_current_ssid("wlan0") == "TestAP 5678"

    def test_no_active_ssid(self) -> None:
        output = "no:HomeNet\nno:WorkNet\n"
        with patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            assert NmcliCurrentSSID().get_current_ssid("wlan0") is None

    def test_empty_active_ssid(self) -> None:
        output = "yes:\nno:HomeNet\n"
        with patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            assert NmcliCurrentSSID().get_current_ssid("wlan0") is None

    def test_command_fails(self) -> None:
        with patch(
            "wifi_controller.linux.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "nmcli"),
        ):
            assert NmcliCurrentSSID().get_current_ssid("wlan0") is None

    def test_binary_not_found(self) -> None:
        with patch("wifi_controller.linux.subprocess.check_output", side_effect=FileNotFoundError):
            assert NmcliCurrentSSID().get_current_ssid("wlan0") is None


# ---------------------------------------------------------------------------
# NmcliScan
# ---------------------------------------------------------------------------


class TestNmcliScan:
    """nmcli scan provider."""

    def test_name(self) -> None:
        assert NmcliScan().name == "nmcli"

    def test_available_when_nmcli_exists(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value="/usr/bin/nmcli"):
            assert NmcliScan().is_available() is True

    def test_parses_scan_output(self) -> None:
        # nmcli -t format: ssid:bssid_parts:signal:freq
        output = "TestAP 5678:AA:BB:CC:DD:EE:FF:75:2437\nHomeNet:11:22:33:44:55:66:50:5180\n"
        with patch("wifi_controller.linux.subprocess.run"), \
             patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            results = NmcliScan().scan_ssids("wlan0")
        assert len(results) == 2
        assert results[0].ssid == "TestAP 5678"
        assert results[0].channel == 6  # 2437 MHz = channel 6
        assert results[1].ssid == "HomeNet"

    def test_deduplicates_ssids(self) -> None:
        output = "DupeNet:AA:BB:CC:DD:EE:FF:75:2437\nDupeNet:11:22:33:44:55:66:50:2437\n"
        with patch("wifi_controller.linux.subprocess.run"), \
             patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            results = NmcliScan().scan_ssids("wlan0")
        assert len(results) == 1

    def test_empty_ssid_skipped(self) -> None:
        output = ":AA:BB:CC:DD:EE:FF:75:2437\nRealNet:11:22:33:44:55:66:50:2437\n"
        with patch("wifi_controller.linux.subprocess.run"), \
             patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            results = NmcliScan().scan_ssids("wlan0")
        assert len(results) == 1
        assert results[0].ssid == "RealNet"

    def test_command_fails(self) -> None:
        with patch("wifi_controller.linux.subprocess.run"), \
             patch(
                 "wifi_controller.linux.subprocess.check_output",
                 side_effect=subprocess.CalledProcessError(1, "nmcli"),
             ):
            assert NmcliScan().scan_ssids("wlan0") == []

    def test_short_lines_skipped(self) -> None:
        output = "too:few:parts\nTestAP 5678:AA:BB:CC:DD:EE:FF:75:2437\n"
        with patch("wifi_controller.linux.subprocess.run"), \
             patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            results = NmcliScan().scan_ssids("wlan0")
        assert len(results) == 1
        assert results[0].ssid == "TestAP 5678"

    def test_invalid_signal_defaults_to_zero(self) -> None:
        output = "Net:AA:BB:CC:DD:EE:FF:bad:bad\n"
        with patch("wifi_controller.linux.subprocess.run"), \
             patch("wifi_controller.linux.subprocess.check_output", return_value=output):
            results = NmcliScan().scan_ssids("wlan0")
        assert len(results) == 1
        assert results[0].rssi == 0
        assert results[0].channel == 0


# ---------------------------------------------------------------------------
# NmcliConnect
# ---------------------------------------------------------------------------


class TestNmcliConnect:
    """nmcli connect provider."""

    def test_name(self) -> None:
        assert NmcliConnect().name == "nmcli"

    def test_available_when_nmcli_exists(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value="/usr/bin/nmcli"):
            assert NmcliConnect().is_available() is True

    def test_successful_connect(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("wifi_controller.linux.subprocess.run", return_value=mock_result):
            NmcliConnect().connect("TestAP 5678", "password", "wlan0")

    def test_nonzero_exit_raises(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No suitable network found"
        mock_result.stdout = ""
        with patch("wifi_controller.linux.subprocess.run", return_value=mock_result):
            with pytest.raises(WiFiConnectionError, match="No suitable network"):
                NmcliConnect().connect("BadNet", "password", "wlan0")

    def test_timeout_raises(self) -> None:
        with patch(
            "wifi_controller.linux.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="nmcli", timeout=30),
        ):
            with pytest.raises(WiFiConnectionError, match="nmcli failed"):
                NmcliConnect().connect("Net", "pass", "wlan0")

    def test_binary_not_found_raises(self) -> None:
        with patch("wifi_controller.linux.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(WiFiConnectionError, match="nmcli failed"):
                NmcliConnect().connect("Net", "pass", "wlan0")

    def test_fallback_to_stdout_on_empty_stderr(self) -> None:
        """If stderr is empty, the error message comes from stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        mock_result.stdout = "Error from stdout"
        with patch("wifi_controller.linux.subprocess.run", return_value=mock_result):
            with pytest.raises(WiFiConnectionError, match="Error from stdout"):
                NmcliConnect().connect("Net", "pass", "wlan0")


# ---------------------------------------------------------------------------
# NmcliDisconnect
# ---------------------------------------------------------------------------


class TestNmcliDisconnect:
    """nmcli disconnect provider."""

    def test_name(self) -> None:
        assert NmcliDisconnect().name == "nmcli"

    def test_available_when_nmcli_exists(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value="/usr/bin/nmcli"):
            assert NmcliDisconnect().is_available() is True

    def test_successful_disconnect(self) -> None:
        with patch("wifi_controller.linux.subprocess.run") as mock_run:
            NmcliDisconnect().disconnect("wlan0")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["nmcli", "dev", "disconnect", "wlan0"]

    def test_timeout_swallowed(self) -> None:
        with patch(
            "wifi_controller.linux.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="nmcli", timeout=10),
        ):
            NmcliDisconnect().disconnect("wlan0")  # should not raise

    def test_file_not_found_swallowed(self) -> None:
        with patch("wifi_controller.linux.subprocess.run", side_effect=FileNotFoundError):
            NmcliDisconnect().disconnect("wlan0")  # should not raise


# ---------------------------------------------------------------------------
# IwgetidCurrentSSID
# ---------------------------------------------------------------------------


class TestIwgetidCurrentSSID:
    """iwgetid -r current SSID provider."""

    def test_name(self) -> None:
        assert IwgetidCurrentSSID().name == "iwgetid"

    def test_available_when_iwgetid_exists(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value="/sbin/iwgetid"):
            assert IwgetidCurrentSSID().is_available() is True

    def test_unavailable_when_iwgetid_missing(self) -> None:
        with patch("wifi_controller.linux.shutil.which", return_value=None):
            assert IwgetidCurrentSSID().is_available() is False

    def test_parses_ssid(self) -> None:
        with patch("wifi_controller.linux.subprocess.check_output", return_value="TestAP 5678\n"):
            assert IwgetidCurrentSSID().get_current_ssid("wlan0") == "TestAP 5678"

    def test_empty_returns_none(self) -> None:
        with patch("wifi_controller.linux.subprocess.check_output", return_value=""):
            assert IwgetidCurrentSSID().get_current_ssid("wlan0") is None

    def test_whitespace_only_returns_none(self) -> None:
        with patch("wifi_controller.linux.subprocess.check_output", return_value="  \n"):
            assert IwgetidCurrentSSID().get_current_ssid("wlan0") is None

    def test_command_fails(self) -> None:
        with patch(
            "wifi_controller.linux.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(1, "iwgetid"),
        ):
            assert IwgetidCurrentSSID().get_current_ssid("wlan0") is None

    def test_binary_not_found(self) -> None:
        with patch("wifi_controller.linux.subprocess.check_output", side_effect=FileNotFoundError):
            assert IwgetidCurrentSSID().get_current_ssid("wlan0") is None
