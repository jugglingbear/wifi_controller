"""Unit tests for WiFiController provider resolution, registration, and orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wifi_controller import WiFiConnectionError, WiFiController, macos_major
from wifi_controller.types import SSIDInfo

from _fakes import FakeConnect, FakeCurrentSSID, FakeDisconnect, FakeScan


# ---------------------------------------------------------------------------
# Registration & resolution
# ---------------------------------------------------------------------------


class TestRegistration:
    """Provider registration and basic resolution."""

    def test_register_and_resolve_current(self, ctrl: WiFiController) -> None:
        provider = FakeCurrentSSID("MyNet")
        ctrl.register_current_ssid_provider(provider, priority=0)
        assert ctrl.get_current_ssid() == "MyNet"

    def test_register_and_resolve_scan(self, ctrl: WiFiController) -> None:
        networks = [SSIDInfo("Net1", "00:11:22:33:44:55", -42, 6)]
        provider = FakeScan(networks)
        ctrl.register_scan_provider(provider, priority=0)
        result = ctrl.scan()
        assert len(result) == 1
        assert result[0].ssid == "Net1"

    def test_register_and_resolve_connect(self, ctrl: WiFiController) -> None:
        provider = FakeConnect()
        ctrl.register_connect_provider(provider, priority=0)
        ctrl.connect("TestNet", "password123")
        assert provider.last_ssid == "TestNet"

    def test_register_and_resolve_disconnect(self, ctrl: WiFiController) -> None:
        provider = FakeDisconnect()
        ctrl.register_disconnect_provider(provider, priority=0)
        ctrl.disconnect()
        assert provider.called

    def test_register_clears_cached_resolution(self, ctrl: WiFiController) -> None:
        """Registering a new provider resets the resolved-instance cache."""
        first = FakeCurrentSSID("First")
        ctrl.register_current_ssid_provider(first, priority=0)
        assert ctrl.get_current_ssid() == "First"

        # Clear the internal name cache so priority-based discovery runs fresh.
        ctrl._cache.clear()
        second = FakeCurrentSSID("Second")
        ctrl.register_current_ssid_provider(second, priority=10)
        assert ctrl.get_current_ssid() == "Second"


# ---------------------------------------------------------------------------
# Priority resolution
# ---------------------------------------------------------------------------


class TestPriorityResolution:
    """Providers are resolved in descending priority order."""

    def test_higher_priority_wins(self, ctrl: WiFiController) -> None:
        low = FakeCurrentSSID("LowPriority")
        high = FakeCurrentSSID("HighPriority")
        ctrl.register_current_ssid_provider(low, priority=0)
        ctrl.register_current_ssid_provider(high, priority=10)
        assert ctrl.get_current_ssid() == "HighPriority"

    def test_unavailable_provider_skipped(self, ctrl: WiFiController) -> None:
        unavailable = FakeCurrentSSID("Unavailable", available=False)
        available = FakeCurrentSSID("Available")
        ctrl.register_current_ssid_provider(unavailable, priority=10)
        ctrl.register_current_ssid_provider(available, priority=0)
        assert ctrl.get_current_ssid() == "Available"

    def test_all_unavailable_returns_none(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID(available=False), priority=10)
        ctrl.register_current_ssid_provider(FakeCurrentSSID(available=False), priority=0)
        assert ctrl.get_current_ssid() is None

    def test_scan_priority(self, ctrl: WiFiController) -> None:
        low = FakeScan([SSIDInfo("Low", "", 0, 0)])
        high = FakeScan([SSIDInfo("High", "", 0, 0)])
        ctrl.register_scan_provider(low, priority=0)
        ctrl.register_scan_provider(high, priority=10)
        result = ctrl.scan()
        assert result[0].ssid == "High"


# ---------------------------------------------------------------------------
# No-provider fallback behavior
# ---------------------------------------------------------------------------


class TestNoProviders:
    """Behavior when no providers are registered for an operation."""

    def test_get_current_ssid_returns_none(self, ctrl: WiFiController) -> None:
        assert ctrl.get_current_ssid() is None

    def test_scan_returns_empty(self, ctrl: WiFiController) -> None:
        assert ctrl.scan() == []

    def test_connect_raises(self, ctrl: WiFiController) -> None:
        with pytest.raises(WiFiConnectionError, match="No connect provider"):
            ctrl.connect("Test", "pass")

    def test_disconnect_no_error(self, ctrl: WiFiController) -> None:
        """Disconnect with no provider logs a warning but does not raise."""
        ctrl.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# Already-connected guard
# ---------------------------------------------------------------------------


class TestAlreadyConnectedGuard:
    """WiFiController.connect() skips the underlying provider when already on target SSID."""

    def test_skips_connect_when_already_connected(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID("TestAP 5678"))
        connect_provider = FakeConnect()
        ctrl.register_connect_provider(connect_provider, priority=0)

        ctrl.connect("TestAP 5678", "password")
        assert connect_provider.call_count == 0

    def test_proceeds_when_different_ssid(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID("OtherNetwork"))
        connect_provider = FakeConnect()
        ctrl.register_connect_provider(connect_provider, priority=0)

        ctrl.connect("TestAP 5678", "password")
        assert connect_provider.call_count == 1
        assert connect_provider.last_ssid == "TestAP 5678"

    def test_proceeds_when_not_connected(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID(None))
        connect_provider = FakeConnect()
        ctrl.register_connect_provider(connect_provider, priority=0)

        ctrl.connect("TestAP 5678", "password")
        assert connect_provider.call_count == 1


# ---------------------------------------------------------------------------
# Convenience methods
# ---------------------------------------------------------------------------


class TestConvenienceMethods:
    """High-level convenience methods: is_connected, scan_for_ssid, etc."""

    def test_is_connected_true(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID("Net"))
        assert ctrl.is_connected() is True

    def test_is_connected_false(self, ctrl: WiFiController) -> None:
        ctrl.register_current_ssid_provider(FakeCurrentSSID(None))
        assert ctrl.is_connected() is False

    def test_connect_error_propagates(self, ctrl: WiFiController) -> None:
        ctrl.register_connect_provider(FakeConnect(fail=True))
        with pytest.raises(WiFiConnectionError, match="Fake failure"):
            ctrl.connect("BadNet", "pass")


class TestScanForSSID:
    """WiFiController.scan_for_ssid() polling behavior."""

    def test_found_immediately(self, ctrl: WiFiController) -> None:
        networks = [SSIDInfo("TestAP 5678", "", -40, 6)]
        ctrl.register_scan_provider(FakeScan(networks))
        with patch("wifi_controller.time.sleep"), \
             patch("wifi_controller.logger"):
            assert ctrl.scan_for_ssid("TestAP 5678", timeout_sec=1.0) is True

    def test_not_found_returns_false(self, ctrl: WiFiController) -> None:
        ctrl.register_scan_provider(FakeScan([]))
        with patch("wifi_controller.time.sleep"), \
             patch("wifi_controller.time.perf_counter", side_effect=[0.0, 0.0, 2.0]), \
             patch("wifi_controller.logger"):
            assert ctrl.scan_for_ssid("TestAP 5678", timeout_sec=1.0) is False

    def test_invert_not_found_returns_true(self, ctrl: WiFiController) -> None:
        """With invert=True, return True when SSID is absent."""
        ctrl.register_scan_provider(FakeScan([]))
        with patch("wifi_controller.time.sleep"), \
             patch("wifi_controller.logger"):
            assert ctrl.scan_for_ssid("TestAP 5678", timeout_sec=1.0, invert=True) is True

    def test_invert_found_returns_invert_on_timeout(self, ctrl: WiFiController) -> None:
        """With invert=True and SSID always present, returns invert (True) on timeout."""
        networks = [SSIDInfo("TestAP 5678", "", -40, 6)]
        ctrl.register_scan_provider(FakeScan(networks))
        # The SSID is always found, so the early-return (`not found and invert`) never fires.
        # On timeout exhaustion, `return invert` → True.
        with patch("wifi_controller.time.sleep"), \
             patch("wifi_controller.time.perf_counter", side_effect=[0.0, 0.5, 2.0]), \
             patch("wifi_controller.logger"):
            assert ctrl.scan_for_ssid("TestAP 5678", timeout_sec=1.0, invert=True) is True


# ---------------------------------------------------------------------------
# is_wifi_enabled
# ---------------------------------------------------------------------------


class TestIsWifiEnabled:
    """WiFiController.is_wifi_enabled() across platforms."""

    def testmacos_wifi_on(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Darwin"
        with patch("wifi_controller.subprocess.check_output", return_value="Wi-Fi Power (en0): On"):
            assert ctrl.is_wifi_enabled() is True

    def testmacos_wifi_off(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Darwin"
        with patch("wifi_controller.subprocess.check_output", return_value="Wi-Fi Power (en0): Off"):
            assert ctrl.is_wifi_enabled() is False

    def testmacos_command_fails_assumes_on(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Darwin"
        with patch("wifi_controller.subprocess.check_output", side_effect=OSError("not found")):
            assert ctrl.is_wifi_enabled() is True

    def testlinux_wifi_enabled(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Linux"
        with patch("wifi_controller.subprocess.check_output", return_value="enabled\n"):
            assert ctrl.is_wifi_enabled() is True

    def testlinux_wifi_disabled(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Linux"
        with patch("wifi_controller.subprocess.check_output", return_value="disabled\n"):
            assert ctrl.is_wifi_enabled() is False

    def test_unknown_platform_assumes_on(self, ctrl: WiFiController) -> None:
        ctrl._os_name = "Windows"
        assert ctrl.is_wifi_enabled() is True


# ---------------------------------------------------------------------------
# Interface detection
# ---------------------------------------------------------------------------


class TestDetectInterface:
    """WiFiController._detect_interface() per-platform defaults."""

    def test_darwin_returns_en0(self) -> None:
        assert WiFiController._detect_interface("Darwin") == "en0"

    def testlinux_fallback_wlan0(self) -> None:
        with patch("wifi_controller.Path") as mock_path:
            mock_path.return_value.iterdir.side_effect = OSError("no sysfs")
            assert WiFiController._detect_interface("Linux") == "wlan0"

    def test_windows_returns_wifi(self) -> None:
        assert WiFiController._detect_interface("Windows") == "Wi-Fi"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """WiFiController read-only properties."""

    def test_interface_name(self, ctrl: WiFiController) -> None:
        assert ctrl.interface_name == "test0"

    def test_platform_info_unknown(self, ctrl: WiFiController) -> None:
        """Non-macOS platform returns system + release string."""
        with patch("wifi_controller.platform.mac_ver", return_value=("", ("", "", ""), "")), \
             patch("wifi_controller.platform.system", return_value="TestOS"), \
             patch("wifi_controller.platform.release", return_value="1.0"):
            info = ctrl.platform_info
        assert "TestOS" in info

    def test_platform_infomacos(self) -> None:
        with patch("wifi_controller.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.mac_ver.return_value = ("15.5", ("", "", ""), "")
            mock_platform.release.return_value = "24.5.0"
            wc = WiFiController(interface="en0")
            assert "macOS 15.5" in wc.platform_info


# ---------------------------------------------------------------------------
# Provider cache (disk persistence)
# ---------------------------------------------------------------------------


class TestProviderCache:
    """Disk-based provider cache persistence."""

    def test_cache_written_on_resolve(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "cache.json"
        with patch("wifi_controller.platform") as mock_platform:
            mock_platform.system.return_value = "TestOS"
            mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
            mock_platform.release.return_value = "1.0"
            wc = WiFiController(interface="test0", cache_path=cache_file)

        wc.register_current_ssid_provider(FakeCurrentSSID("CachedNet"))
        wc.get_current_ssid()

        assert cache_file.exists()
        cached = json.loads(cache_file.read_text())
        assert cached["current"] == "fake_current"

    def test_cache_restored_on_init(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps({"current": "fake_current"}))

        with patch("wifi_controller.platform") as mock_platform:
            mock_platform.system.return_value = "TestOS"
            mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
            mock_platform.release.return_value = "1.0"
            wc = WiFiController(interface="test0", cache_path=cache_file)

        provider = FakeCurrentSSID("CachedNet")
        wc.register_current_ssid_provider(provider)
        assert wc.get_current_ssid() == "CachedNet"

    def test_corrupt_cache_ignored(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("NOT VALID JSON {{{")

        with patch("wifi_controller.platform") as mock_platform:
            mock_platform.system.return_value = "TestOS"
            mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
            mock_platform.release.return_value = "1.0"
            wc = WiFiController(interface="test0", cache_path=cache_file)

        # Should still work — corrupt cache is discarded
        wc.register_current_ssid_provider(FakeCurrentSSID("OK"))
        assert wc.get_current_ssid() == "OK"

    def test_no_cache_path_no_file(self, ctrl: WiFiController) -> None:
        """With no cache_path, no cache file is written."""
        ctrl.register_current_ssid_provider(FakeCurrentSSID("Net"))
        ctrl.get_current_ssid()
        assert ctrl._cache_path is None


# ---------------------------------------------------------------------------
# Built-in provider setup
# ---------------------------------------------------------------------------


class TestSetupBuiltinProviders:
    """_setup_builtin_providers installs platform-appropriate providers."""

    def testmacos_14_registers_networksetup(self) -> None:
        with patch("wifi_controller.platform") as mock_platform, \
             patch("wifi_controller.macos_major", return_value=14):
            mock_platform.system.return_value = "Darwin"
            mock_platform.mac_ver.return_value = ("14.5", ("", "", ""), "")
            mock_platform.release.return_value = "23.5.0"
            wc = WiFiController(interface="en0")

        assert len(wc._current_providers) > 0
        assert any(p.provider.name == "networksetup" for p in wc._current_providers)
        assert any(p.provider.name == "system_profiler" for p in wc._scan_providers)

    def testmacos_15_registers_ipconfig(self) -> None:
        with patch("wifi_controller.platform") as mock_platform, \
             patch("wifi_controller.macos_major", return_value=15):
            mock_platform.system.return_value = "Darwin"
            mock_platform.mac_ver.return_value = ("15.5", ("", "", ""), "")
            mock_platform.release.return_value = "24.5.0"
            wc = WiFiController(interface="en0")

        assert any(p.provider.name == "ipconfig" for p in wc._current_providers)
        # No scan provider on macOS 15+ (SSIDs redacted)
        assert len(wc._scan_providers) == 0

    def testlinux_with_nmcli(self) -> None:
        with patch("wifi_controller.platform") as mock_platform, \
             patch("wifi_controller.linux.shutil.which", return_value="/usr/bin/nmcli"):
            mock_platform.system.return_value = "Linux"
            mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
            mock_platform.release.return_value = "6.1.0"
            wc = WiFiController(interface="wlan0")

        assert any(p.provider.name == "nmcli" for p in wc._current_providers)
        assert any(p.provider.name == "nmcli" for p in wc._scan_providers)

    def test_unsupported_platform_no_providers(self, ctrl: WiFiController) -> None:
        """TestOS results in no built-in providers."""
        assert len(ctrl._current_providers) == 0
        assert len(ctrl._scan_providers) == 0
        assert len(ctrl._connect_providers) == 0
        assert len(ctrl._disconnect_providers) == 0


# ---------------------------------------------------------------------------
# macos_major helper
# ---------------------------------------------------------------------------


class TestMacosMajor:
    """Module-level macos_major() helper."""

    def test_parses_15_5(self) -> None:
        with patch("wifi_controller.platform.mac_ver", return_value=("15.5", ("", "", ""), "")):
            assert macos_major() == 15

    def test_parses_14_0(self) -> None:
        with patch("wifi_controller.platform.mac_ver", return_value=("14.0", ("", "", ""), "")):
            assert macos_major() == 14

    def test_parses_13_7_2(self) -> None:
        with patch("wifi_controller.platform.mac_ver", return_value=("13.7.2", ("", "", ""), "")):
            assert macos_major() == 13

    def test_empty_version_returns_zero(self) -> None:
        with patch("wifi_controller.platform.mac_ver", return_value=("", ("", "", ""), "")):
            assert macos_major() == 0

    def testlinux_returns_zero(self) -> None:
        """Non-macOS returns empty mac_ver → 0."""
        with patch("wifi_controller.platform.mac_ver", return_value=("", ("", "", ""), "")):
            assert macos_major() == 0
