from __future__ import annotations

import json
import sys
from typing import Optional

import click

from wifi_controller import WiFiController, WiFiConnectionError, __version__


@click.group()
@click.option("--interface", help="Wi-Fi interface (e.g., wlan0, en0)")
@click.pass_context
def cli(ctx: click.Context, interface: Optional[str]) -> None:
    """Cross-platform Wi-Fi controller."""
    ctx.obj = WiFiController(interface=interface)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
@click.pass_obj
def scan(wifi: WiFiController, as_json: bool) -> None:
    """Scan for Wi-Fi networks."""
    networks = wifi.scan()

    if as_json:
        print(json.dumps([vars(n) for n in networks]))
        return

    for net in networks:
        print(f"{net.ssid}\tRSSI={net.rssi}\tCH={net.channel}")


@cli.command()
@click.pass_obj
def current(wifi: WiFiController) -> None:
    """Show current SSID."""
    ssid = wifi.get_current_ssid()
    print(ssid or "<not connected>")


@cli.command()
@click.argument("ssid")
@click.argument("password")
@click.pass_obj
def connect(wifi: WiFiController, ssid: str, password: str) -> None:
    """Connect to a network."""
    try:
        wifi.connect(ssid, password)
        print(f"Connected to {ssid}")
    except WiFiConnectionError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_obj
def disconnect(wifi: WiFiController) -> None:
    """Disconnect from current network."""
    wifi.disconnect()
    print("Disconnected")


@cli.command()
def version() -> None:
    """Show version."""
    print(__version__)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
