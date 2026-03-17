# wifi-controller

A cross-platform Wi-Fi controller for Python with a pluggable provider architecture.

Supports macOS and Linux out of the box, with an optional Swift-based scanner for macOS 15+ where Apple redacts SSIDs without Location Services authorization.

---

## Why wifi-controller?

Most existing Wi-Fi libraries:

- Are OS-specific or inconsistent across platforms
- Depend heavily on fragile system tools
- Are difficult to extend or test

**wifi-controller provides:**

- A unified API across platforms
- A pluggable provider system
- Clean abstractions suitable for automation and QA workflows

---

## Platform Support

| Platform | Status        | Notes |
|----------|--------------|------|
| macOS    | ✅ Supported  | Full support; SSID redaction workaround available |
| Linux    | ⚠️ Partial    | Requires `nmcli` or `iwgetid` |
| Windows  | ❌ Not yet implemented |

---

## Features

- Cross-platform — built-in providers for macOS (`networksetup`, `ipconfig`, `system_profiler`) and Linux (`nmcli`, `iwgetid`)
- Pluggable providers — register your own scan/connect/disconnect implementations with priority-based resolution
- macOS SSID redaction workaround — optional Swift scanner (see below)
- Zero Python dependencies — uses only the standard library (relies on native system tools where applicable)

---

## Installation

```bash
pip install wifi-controller
```

Or with Poetry:

```bash
poetry add wifi-controller
```

---

## ⚠️ macOS 15+ (Sequoia) Users

Apple redacts SSID information unless the process has Location Services authorization.

👉 This means **default Python providers will return redacted SSIDs**.

See **macOS 15+ SSID Redaction** below for the workaround.

---

## Quick Start

### Get current network

```python
from wifi_controller import WiFiController

wifi = WiFiController()

ssid = wifi.get_current_ssid()
print(f"Connected to: {ssid}")
```

---

### Scan nearby networks

```python
networks = wifi.scan()

for net in networks:
    print(f"{net.ssid} (RSSI={net.rssi}, CH={net.channel})")
```

---

### Connect to a network

```python
wifi.connect("MyNetwork", "hunter2")
```

---

### Wait for a network to appear

```python
found = wifi.scan_for_ssid("MyNetwork", timeout_sec=30)
```

---

### Disconnect

```python
wifi.disconnect()
```

---

### Specify interface (optional)

```python
wifi = WiFiController(interface="wlan0")
```

---

### Handling connection errors

```python
from wifi_controller import WiFiController, WiFiConnectionError

wifi = WiFiController()

try:
    wifi.connect("MyNetwork", "wrong-password")
except WiFiConnectionError as e:
    print(f"Failed to connect: {e}")
```

---

## Use Cases

- Automated Wi-Fi testing
- Embedded device validation
- Network orchestration in CI pipelines

---

## macOS 15+ SSID Redaction

Starting with macOS 15 (Sequoia), Apple redacts SSID information from system APIs unless the calling process has Location Services authorization via a signed app bundle.

The built-in Python providers cannot work around this limitation.

### Workaround: Swift Scanner

Build the Swift scanner from `extras/ssid_scanner/`:

```bash
# Prerequisites: Xcode Command Line Tools + Apple Development certificate
make -C extras/ssid_scanner check
make -C extras/ssid_scanner all
```

Then register the Swift providers:

```python
from wifi_controller import WiFiController
from wifi_controller.swift import (
    SwiftSsidScannerCurrentSSID,
    SwiftSsidScannerScan,
    SwiftSsidScannerConnect,
    SwiftSsidScannerDisconnect,
)

wifi = WiFiController()
binary = "extras/ssid_scanner/ssid_scanner"

wifi.register_scan_provider(SwiftSsidScannerScan(binary), priority=10)
wifi.register_current_ssid_provider(SwiftSsidScannerCurrentSSID(binary), priority=10)
wifi.register_connect_provider(SwiftSsidScannerConnect(binary), priority=10)
wifi.register_disconnect_provider(SwiftSsidScannerDisconnect(binary), priority=10)

networks = wifi.scan()
```

---

## Custom Providers

Providers are resolved by priority. The first available provider is selected and cached for reuse.

Implement any of the provider ABCs:

```python
from wifi_controller import WiFiController, SSIDScanProvider, SSIDInfo

class MyCustomScanner(SSIDScanProvider):
    @property
    def name(self) -> str:
        return "my_scanner"

    def is_available(self) -> bool:
        return True

    def scan_ssids(self, interface: str, timeout: int = 15) -> list[SSIDInfo]:
        return [
            SSIDInfo(
                ssid="Example",
                bssid="00:11:22:33:44:55",
                rssi=-42,
                channel=6,
            )
        ]

wifi = WiFiController()
wifi.register_scan_provider(MyCustomScanner(), priority=20)
```

### Provider Types

| ABC | Operation |
|-----|----------|
| `CurrentSSIDProvider` | Get current SSID |
| `SSIDScanProvider` | Scan networks |
| `SSIDConnectProvider` | Connect |
| `SSIDDisconnectProvider` | Disconnect |

---

## Caveats

- macOS 15+ requires Location Services authorization for real SSIDs
- Linux requires `nmcli` or `iwgetid`
- Interface names may vary (`en0`, `wlan0`, etc.)
- Behavior depends on underlying OS capabilities and drivers

---

## Architecture

See `docs/` for PlantUML diagrams:

- Class diagram — provider abstractions
- Sequence diagram — resolution flow
- Component diagram — platform boundaries

---

## Development

```bash
poetry install
poetry run pytest
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/
```

---

## Status

Early development (v0.x).  
APIs may change between releases.

---

## License

MIT — see `LICENSE`.
