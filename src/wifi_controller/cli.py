from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from wifi_controller import WiFiController, WiFiConnectionError


def _cmd_scan(wifi: WiFiController, args: argparse.Namespace) -> None:
    networks = wifi.scan()
    for net in networks:
        print(f"{net.ssid}\tRSSI={net.rssi}\tCH={net.channel}")


def _cmd_current(wifi: WiFiController, args: argparse.Namespace) -> None:
    ssid = wifi.get_current_ssid()
    print(ssid or "<not connected>")


def _cmd_connect(wifi: WiFiController, args: argparse.Namespace) -> None:
    try:
        wifi.connect(args.ssid, args.password)
        print(f"Connected to {args.ssid}")
    except WiFiConnectionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_disconnect(wifi: WiFiController, args: argparse.Namespace) -> None:
    wifi.disconnect()
    print("Disconnected")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wifi-controller")
    parser.add_argument("--interface", help="Wi-Fi interface (e.g., wlan0, en0)")

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan for Wi-Fi networks")
    scan.set_defaults(func=_cmd_scan)

    current = sub.add_parser("current", help="Show current SSID")
    current.set_defaults(func=_cmd_current)

    connect = sub.add_parser("connect", help="Connect to a network")
    connect.add_argument("ssid")
    connect.add_argument("password")
    connect.set_defaults(func=_cmd_connect)

    disconnect = sub.add_parser("disconnect", help="Disconnect from current network")
    disconnect.set_defaults(func=_cmd_disconnect)

    return parser


def main() -> NoReturn:
    parser = build_parser()
    args = parser.parse_args()

    wifi = WiFiController(interface=args.interface)

    args.func(wifi, args)
    sys.exit(0)


if __name__ == "__main__":
    main()
