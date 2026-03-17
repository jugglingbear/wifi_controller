from __future__ import annotations

import sys
from io import StringIO
from typing import Callable, Tuple

import pytest

from wifi_controller import WiFiConnectionError, WiFiController
from wifi_controller.cli import main


def _run_cli(args: list[str]) -> Tuple[int, str]:
    old_argv: list[str] = sys.argv.copy()
    old_stdout = sys.stdout

    try:
        sys.argv = ["wifi-controller", *args]
        sys.stdout = StringIO()

        try:
            main()
            returncode: int = 0
        except SystemExit as e:
            returncode = int(e.code) if isinstance(e.code, int) else 1

        output: str = sys.stdout.getvalue()
        return returncode, output

    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout


def test_cli_help() -> None:
    returncode, stdout = _run_cli(["--help"])
    assert returncode == 0
    assert "usage" in stdout.lower()


def test_cli_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeNet:
        ssid: str = "TestNet"
        rssi: int = -40
        channel: int = 6

    def fake_scan(self: WiFiController) -> list[FakeNet]:
        return [FakeNet()]

    monkeypatch.setattr(WiFiController, "scan", fake_scan)

    returncode, stdout = _run_cli(["scan"])
    assert returncode == 0
    assert "TestNet" in stdout


def test_cli_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(self: WiFiController, ssid: str, password: str | None = None) -> None:
        raise WiFiConnectionError("boom")

    monkeypatch.setattr(WiFiController, "connect", fake_connect)

    returncode, _ = _run_cli(["connect", "MySSID"])
    assert returncode != 0
