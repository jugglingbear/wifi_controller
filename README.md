# wifi-controller

A cross-platform Wi-Fi controller for Python with pluggable provider architecture.
Supports macOS and Linux out of the box, with an optional Swift-based scanner for
macOS 15+ where Apple redacts SSIDs without Location Services authorization.

## Features

- **Cross-platform** -- built-in providers for macOS (`networksetup`, `ipconfig`,
  `system_profiler`) and Linux (`nmcli`, `iwgetid`)
- **Pluggable providers** -- register your own scan/connect/disconnect implementations
  with priority-based resolution
- **macOS SSID redaction workaround** -- optional Swift scanner (`extras/ssid_scanner/`)
  uses CoreWLAN + CoreLocation to return real SSIDs on macOS 15+
- **Zero dependencies** -- pure Python, stdlib only

## Installation

```bash
pip install wifi-controller
```

Or with Poetry:

```bash
poetry add wifi-controller
```

## Quick Start

```python
from wifi_controller import WiFiController

wifi = WiFiController()

# Get current network
ssid = wifi.get_current_ssid()
print(f"Connected to: {ssid}")

# Scan nearby networks
networks = wifi.scan()
for net in networks:
    print(f"  {net.ssid} (RSSI={net.rssi}, CH={net.channel})")

# Connect to a network
wifi.connect("MyNetwork", "hunter2")

# Poll for a specific SSID
found = wifi.scan_for_ssid("MyNetwork", timeout_sec=30)

# Disconnect
wifi.disconnect()
```

## macOS 15+ SSID Redaction

Starting with macOS 15 (Sequoia), Apple redacts SSID information from
`system_profiler`, `CoreWLAN`, and other system APIs unless the calling process
has Location Services authorization via a signed app bundle.

The built-in Python providers **cannot** work around this limitation. To get
real SSIDs on macOS 15+, build the Swift scanner from `extras/ssid_scanner/`:

```bash
# Prerequisites: Xcode Command Line Tools + Apple Development certificate
make -C extras/ssid_scanner check   # verify prerequisites
make -C extras/ssid_scanner all     # build and sign
```

Then register the Swift providers:

```python
from wifi_controller import WiFiController
from wifi_controller._swift import (
    SwiftSsidScannerCurrentSSID,
    SwiftSsidScannerScan,
    SwiftSsidScannerConnect,
    SwiftSsidScannerDisconnect,
)

wifi = WiFiController()
binary = "extras/ssid_scanner/ssid_scanner"  # path to built binary

wifi.register_scan_provider(SwiftSsidScannerScan(binary), priority=10)
wifi.register_current_ssid_provider(SwiftSsidScannerCurrentSSID(binary), priority=10)
wifi.register_connect_provider(SwiftSsidScannerConnect(binary), priority=10)
wifi.register_disconnect_provider(SwiftSsidScannerDisconnect(binary), priority=10)

# Now scan() returns real SSIDs on macOS 15+
networks = wifi.scan()
```

## Custom Providers

Implement any of the four provider ABCs to add support for additional tools:

```python
from wifi_controller import WiFiController, SSIDScanProvider, SSIDInfo

class MyCustomScanner(SSIDScanProvider):
    @property
    def name(self) -> str:
        return "my_scanner"

    def is_available(self) -> bool:
        return True  # check if your tool is installed

    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]:
        # ... your implementation ...
        return [SSIDInfo(ssid="Example", bssid="00:11:22:33:44:55", rssi=-42, channel=6)]

wifi = WiFiController()
wifi.register_scan_provider(MyCustomScanner(), priority=20)
```

Provider ABCs:

| ABC | Operation |
|-----|-----------|
| `CurrentSSIDProvider` | Get the currently-connected SSID |
| `SSIDScanProvider` | Scan for nearby networks |
| `SSIDConnectProvider` | Connect to a network (SSID + password) |
| `SSIDDisconnectProvider` | Disconnect from the current network |

Higher priority providers are tried first. The first provider whose
`is_available()` returns `True` is used and cached for subsequent calls.

## Project Layout

```
wifi_controller/
├── src/wifi_controller/       # Python package (ships on PyPI)
│   ├── __init__.py            # WiFiController orchestrator
│   ├── _types.py              # SSIDInfo, WiFiConnectionError
│   ├── _abc.py                # Four provider ABCs
│   ├── _macos.py              # Built-in macOS providers
│   ├── _linux.py              # Built-in Linux providers
│   └── _swift.py              # Python wrappers for Swift binary
├── extras/ssid_scanner/       # Swift source (not on PyPI, clone to use)
│   ├── scan.swift             # CoreWLAN + CoreLocation scanner
│   ├── Makefile               # Build, sign, test
│   └── *.plist                # App bundle configuration
├── docs/                      # Architecture diagrams (PlantUML)
└── tests/                     # Unit tests
```

## Architecture

See [docs/](docs/) for PlantUML diagrams covering:

- **Class diagram** -- provider ABCs, WiFiController, built-in implementations
- **Sequence diagram** -- provider resolution and operation flow
- **Component diagram** -- package structure and platform boundaries

## Development

```bash
# Install dev dependencies
poetry install

# Run tests
poetry run pytest

# Lint
poetry run ruff check src/ tests/

# Format
poetry run ruff format src/ tests/
```

## License

MIT -- see [LICENSE](LICENSE).

