# ssid_scanner

A macOS Wi-Fi scanner that returns **real SSIDs** instead of `<redacted>`.

## Why This Exists

Starting with macOS Sonoma (14) and getting stricter in Sequoia (15) and beyond, Apple redacts
Wi-Fi network names from virtually every programmatic and CLI interface. Scans still work — you
get correct RSSI, channel, and network count — but SSIDs come back as `nil`, empty strings, or
`<redacted>`. Apple considers the set of visible Wi-Fi networks to be location-identifying data,
so they gate SSID visibility behind Location Services permission.

This tool requests Location Services authorization through a signed app bundle, which is the only
way to get real SSIDs on modern macOS.

## What Broke

| What | Status |
|------|--------|
| `airport -s` | **Removed entirely** in macOS 26. The binary no longer exists. |
| `system_profiler SPAirPortDataType` | Shows `SSID: <redacted>` — even with `sudo`. |
| `sudo wdutil info` | Shows current network only; nearby networks redacted. |
| `networksetup -getairportnetwork en0` | Returns empty or redacted SSID. |
| CoreWLAN `scanForNetworks()` | Returns nil SSIDs unless the process has Location Services. |
| `ipconfig getsummary en0` | **Still works** but only shows the *currently connected* network — no scan. |

## What This Tool Does

Wraps CoreWLAN + CoreLocation in a signed `.app` bundle so macOS grants Location Services access.
On first run a system popup asks for permission; after that, scans return real SSIDs immediately.

## Usage

```bash
# Build (only needed once, or after editing scan.swift)
make all

# Default: full human-readable table
make run

# Or call the binary directly with flags
./SsidScanner.app/Contents/MacOS/ssid_scanner --help
./SsidScanner.app/Contents/MacOS/ssid_scanner --current
./SsidScanner.app/Contents/MacOS/ssid_scanner --scan
./SsidScanner.app/Contents/MacOS/ssid_scanner --scan --json
./SsidScanner.app/Contents/MacOS/ssid_scanner --scan --timeout 30
./SsidScanner.app/Contents/MacOS/ssid_scanner --connect "<SSID>" "<PASSWORD>"
./SsidScanner.app/Contents/MacOS/ssid_scanner --disconnect
```

## Important: Do Not Use Symlinks

Do **not** replace the `ssid_scanner` wrapper script with a symlink to the binary inside the app
bundle. macOS ties Location Services authorization to the process's resolved binary path. When
launched via symlink, `Bundle.main` does not resolve back to the `.app` bundle, so CoreWLAN
silently redacts all SSIDs — even though `CLLocationManager` still reports "authorized."

The `make all` target creates a small wrapper script that uses `exec` to launch the real binary.
`exec` replaces the shell process with the binary at its real path inside the bundle, which
preserves the app-bundle association that macOS requires.

**TL;DR:** Always use `./ssid_scanner` (the wrapper script) or `make run`. If you need to invoke
the binary directly, use the full bundle path:

```bash
./SsidScanner.app/Contents/MacOS/ssid_scanner --scan
```

## Requirements

- macOS 14+ (Sonoma or later)
- An Apple Developer signing identity (see below)
- Location Services enabled system-wide

### Getting a Signing Identity

The Makefile signs the app with `codesign --sign "Apple Development"`. Ad-hoc signing (`--sign -`)
won't work — macOS refuses to show the Location Services popup for ad-hoc signed apps.

Check if you already have one:

```bash
security find-identity -v -p codesigning
```

If that lists an `Apple Development: ...` certificate, you're good. If not:

1. **Get an Apple Developer account.** A free Apple ID works — you don't need the paid
   $99/year program. Sign in at [developer.apple.com](https://developer.apple.com).
2. **Open Xcode** → Settings (⌘,) → Accounts → add your Apple ID if it isn't there already.
3. **Create the certificate.** Select your Apple ID, click "Manage Certificates…", click the
   **+** button, and choose "Apple Development". Xcode generates a keypair and installs the
   certificate in your login keychain automatically.
4. **Verify** by running `security find-identity -v -p codesigning` again — you should see
   something like `Apple Development: you@example.com (TEAMID)`.

That's it. The certificate persists in your keychain until it expires (usually one year for free
accounts). When it expires, repeat step 3 in Xcode to get a new one.

## Integrating with wifi-controller

The Python package [`wifi-controller`](https://pypi.org/project/wifi-controller/) includes Swift
provider wrappers that shell out to this binary. After building, register them:

```python
from wifi_controller import WiFiController
from wifi_controller.swift import (
    SwiftSsidScannerCurrentSSID,
    SwiftSsidScannerScan,
    SwiftSsidScannerConnect,
    SwiftSsidScannerDisconnect,
)

wifi = WiFiController()
binary = "extras/ssid_scanner/ssid_scanner"  # path to the built wrapper script

wifi.register_scan_provider(SwiftSsidScannerScan(binary), priority=10)
wifi.register_current_ssid_provider(SwiftSsidScannerCurrentSSID(binary), priority=10)
wifi.register_connect_provider(SwiftSsidScannerConnect(binary), priority=10)
wifi.register_disconnect_provider(SwiftSsidScannerDisconnect(binary), priority=10)

# Now scan() returns real SSIDs on macOS 15+
networks = wifi.scan()
```
