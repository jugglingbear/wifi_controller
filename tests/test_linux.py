"""Unit tests for the Linux Wi-Fi providers."""

from __future__ import annotations

from wifi_controller.linux import _freq_to_channel


class TestFreqToChannel:
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

    def test_unknown_frequency(self) -> None:
        assert _freq_to_channel(0) == 0

    def test_out_of_range(self) -> None:
        assert _freq_to_channel(9999) == 0
