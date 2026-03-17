"""Shared fixtures for the wifi_controller test suite."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from wifi_controller import WiFiController


@pytest.fixture
def ctrl() -> WiFiController:
    """WiFiController with no built-in providers (mocked OS detection)."""
    with patch("wifi_controller.platform") as mock_platform:
        mock_platform.system.return_value = "TestOS"
        mock_platform.mac_ver.return_value = ("", ("", "", ""), "")
        mock_platform.release.return_value = "1.0"
        return WiFiController(interface="test0")
