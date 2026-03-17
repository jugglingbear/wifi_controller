"""Unit tests for the Swift ssid_scanner providers (wifi_controller.swift)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wifi_controller.swift import (
    SwiftSsidScannerConnect,
    SwiftSsidScannerCurrentSSID,
    SwiftSsidScannerDisconnect,
    SwiftSsidScannerScan,
)
from wifi_controller.types import WiFiConnectionError


# ---------------------------------------------------------------------------
# SwiftSsidScannerCurrentSSID
# ---------------------------------------------------------------------------


class TestSwiftSsidScannerCurrentSSID:
    """ssid_scanner --current provider."""

    def test_name(self) -> None:
        assert SwiftSsidScannerCurrentSSID("/fake/ssid_scanner").name == "swift_ssid_scanner"

    def test_available_when_binary_exists(self, tmp_path: Path) -> None:
        binary = tmp_path / "ssid_scanner"
        binary.touch()
        assert SwiftSsidScannerCurrentSSID(binary).is_available() is True

    def test_unavailable_when_binary_missing(self) -> None:
        assert SwiftSsidScannerCurrentSSID("/nonexistent/ssid_scanner").is_available() is False

    def test_returns_ssid(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "TestAP 5678\n"
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            ssid = SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0")
        assert ssid == "TestAP 5678"

    def test_returns_none_on_empty_output(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            assert SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0") is None

    def test_returns_none_on_nonzero_exit(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            assert SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0") is None

    def test_returns_none_on_timeout(self) -> None:
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ssid_scanner", timeout=10),
        ):
            assert SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0") is None

    def test_returns_none_on_file_not_found(self) -> None:
        with patch("wifi_controller.swift.subprocess.run", side_effect=FileNotFoundError):
            assert SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0") is None

    def test_returns_none_on_os_error(self) -> None:
        with patch("wifi_controller.swift.subprocess.run", side_effect=OSError("permission denied")):
            assert SwiftSsidScannerCurrentSSID("/fake/bin").get_current_ssid("en0") is None


# ---------------------------------------------------------------------------
# SwiftSsidScannerScan
# ---------------------------------------------------------------------------


class TestSwiftSsidScannerScan:
    """ssid_scanner --scan --json provider."""

    def test_name(self) -> None:
        assert SwiftSsidScannerScan("/fake/bin").name == "swift_ssid_scanner"

    def test_available_when_binary_exists(self, tmp_path: Path) -> None:
        binary = tmp_path / "ssid_scanner"
        binary.touch()
        assert SwiftSsidScannerScan(binary).is_available() is True

    def test_unavailable_when_binary_missing(self) -> None:
        assert SwiftSsidScannerScan("/nonexistent/ssid_scanner").is_available() is False

    def test_parses_json_results(self) -> None:
        scan_output = json.dumps([
            {"ssid": "TestAP 5678", "bssid": "aa:bb:cc:dd:ee:ff", "rssi": -42, "channel": 6},
            {"ssid": "HomeNet", "bssid": "11:22:33:44:55:66", "rssi": -70, "channel": 36},
        ])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = scan_output
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            results = SwiftSsidScannerScan("/fake/bin").scan_ssids("en0", timeout=10)
        assert len(results) == 2
        assert results[0].ssid == "TestAP 5678"
        assert results[0].rssi == -42
        assert results[1].ssid == "HomeNet"
        assert results[1].channel == 36

    def test_empty_json_array(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            assert SwiftSsidScannerScan("/fake/bin").scan_ssids("en0") == []

    def test_invalid_json_returns_empty(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NOT JSON"
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            assert SwiftSsidScannerScan("/fake/bin").scan_ssids("en0") == []

    def test_nonzero_exit_returns_empty(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            assert SwiftSsidScannerScan("/fake/bin").scan_ssids("en0") == []

    def test_timeout_returns_empty(self) -> None:
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ssid_scanner", timeout=45),
        ):
            assert SwiftSsidScannerScan("/fake/bin").scan_ssids("en0") == []

    def test_missing_fields_use_defaults(self) -> None:
        scan_output = json.dumps([{"ssid": "Partial"}])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = scan_output
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            results = SwiftSsidScannerScan("/fake/bin").scan_ssids("en0")
        assert len(results) == 1
        assert results[0].ssid == "Partial"
        assert results[0].bssid == ""
        assert results[0].rssi == 0
        assert results[0].channel == 0


# ---------------------------------------------------------------------------
# SwiftSsidScannerConnect
# ---------------------------------------------------------------------------


class TestSwiftSsidScannerConnect:
    """ssid_scanner --connect provider."""

    def test_name(self) -> None:
        assert SwiftSsidScannerConnect("/fake/bin").name == "swift_ssid_scanner"

    def test_available_when_binary_exists(self, tmp_path: Path) -> None:
        binary = tmp_path / "ssid_scanner"
        binary.touch()
        assert SwiftSsidScannerConnect(binary).is_available() is True

    def test_unavailable_when_binary_missing(self) -> None:
        assert SwiftSsidScannerConnect("/nonexistent/ssid_scanner").is_available() is False

    def test_successful_connect(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        # _get_current_ssid returns different SSID
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = "OtherNet\n"
        with patch("wifi_controller.swift.subprocess.run", side_effect=[current_result, mock_result]):
            SwiftSsidScannerConnect("/fake/bin").connect("TestAP 5678", "password", "en0")

    def test_already_connected_skips(self) -> None:
        """Already-connected guard skips the connect call."""
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = "TestAP 5678\n"
        with patch("wifi_controller.swift.subprocess.run", return_value=current_result) as mock_run:
            SwiftSsidScannerConnect("/fake/bin").connect("TestAP 5678", "password", "en0")
        # Only one call to subprocess.run (for --current), no --connect call
        assert mock_run.call_count == 1

    def test_nonzero_exit_raises(self) -> None:
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = ""
        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stderr = "Apple80211 error -3925"
        with patch("wifi_controller.swift.subprocess.run", side_effect=[current_result, fail_result]):
            with pytest.raises(WiFiConnectionError, match="Apple80211 error"):
                SwiftSsidScannerConnect("/fake/bin").connect("TestAP 5678", "pass", "en0")

    def test_timeout_raises(self) -> None:
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = ""
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=[
                current_result,
                subprocess.TimeoutExpired(cmd="ssid_scanner", timeout=45),
            ],
        ):
            with pytest.raises(WiFiConnectionError, match="timed out"):
                SwiftSsidScannerConnect("/fake/bin").connect("Net", "pass", "en0")

    def test_file_not_found_raises(self) -> None:
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = ""
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=[current_result, FileNotFoundError],
        ):
            with pytest.raises(WiFiConnectionError, match="binary not found"):
                SwiftSsidScannerConnect("/fake/bin").connect("Net", "pass", "en0")

    def test_os_error_raises(self) -> None:
        current_result = MagicMock()
        current_result.returncode = 0
        current_result.stdout = ""
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=[current_result, OSError("permission denied")],
        ):
            with pytest.raises(WiFiConnectionError, match="binary not found"):
                SwiftSsidScannerConnect("/fake/bin").connect("Net", "pass", "en0")


# ---------------------------------------------------------------------------
# SwiftSsidScannerDisconnect
# ---------------------------------------------------------------------------


class TestSwiftSsidScannerDisconnect:
    """ssid_scanner --disconnect provider."""

    def test_name(self) -> None:
        assert SwiftSsidScannerDisconnect("/fake/bin").name == "swift_ssid_scanner"

    def test_available_when_binary_exists(self, tmp_path: Path) -> None:
        binary = tmp_path / "ssid_scanner"
        binary.touch()
        assert SwiftSsidScannerDisconnect(binary).is_available() is True

    def test_unavailable_when_binary_missing(self) -> None:
        assert SwiftSsidScannerDisconnect("/nonexistent/ssid_scanner").is_available() is False

    def test_successful_disconnect(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            SwiftSsidScannerDisconnect("/fake/bin").disconnect("en0")  # should not raise

    def test_nonzero_exit_logs_warning(self) -> None:
        """Non-zero exit code logs a warning but does not raise."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"
        with patch("wifi_controller.swift.subprocess.run", return_value=mock_result):
            SwiftSsidScannerDisconnect("/fake/bin").disconnect("en0")  # should not raise

    def test_timeout_swallowed(self) -> None:
        with patch(
            "wifi_controller.swift.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ssid_scanner", timeout=10),
        ):
            SwiftSsidScannerDisconnect("/fake/bin").disconnect("en0")  # should not raise

    def test_file_not_found_swallowed(self) -> None:
        with patch("wifi_controller.swift.subprocess.run", side_effect=FileNotFoundError):
            SwiftSsidScannerDisconnect("/fake/bin").disconnect("en0")  # should not raise

    def test_os_error_swallowed(self) -> None:
        with patch("wifi_controller.swift.subprocess.run", side_effect=OSError("permission denied")):
            SwiftSsidScannerDisconnect("/fake/bin").disconnect("en0")  # should not raise
