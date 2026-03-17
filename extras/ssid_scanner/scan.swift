import AppKit
import CoreLocation
import CoreWLAN
import Foundation

// MARK: - CLI argument parsing

enum Command {
    case help
    case current
    case disconnect
    case scan(json: Bool, timeout: Int)
    // TODO: Support password-less connect for saved/known networks.
    // Approaches tried:
    //   - CoreWLAN associate(to:password:nil) → treats nil as "open network", error -3900 on WPA
    //   - networksetup -setairportnetwork (no password arg) → returns exit 0 but silently fails
    //   - security find-generic-password (keychain lookup) → triggers macOS GUI auth dialog,
    //     unusable for automation. Running with sudo would bypass it but is not acceptable
    //     in a corporate environment for infosec reasons.
    case connect(ssid: String, password: String, timeout: Int)
    case fullReport(timeout: Int)
}

func printHelp() {
    let help = """
    ssid_scanner — macOS Wi-Fi scanner with non-redacted SSIDs

    Requires Location Services authorization and a signed app bundle to bypass
    Apple's SSID redaction (macOS 15+). On first run, a Location Services popup
    will appear — click Allow.

    USAGE:
      ssid_scanner [command] [options]

    COMMANDS:
      (no command)              Full scan with human-readable table (default)
      --current                 Print the SSID of the currently connected network
      --scan                    Scan nearby networks, one SSID per line
      --scan --json             Scan nearby networks, output as JSON array
      --connect SSID PASSWORD    Connect to a Wi-Fi network
      --disconnect              Disconnect from the current Wi-Fi network

    OPTIONS:
      --timeout SECONDS         Scan timeout in seconds (default: 15)
      --help, -h                Show this help message

    EXAMPLES:
      ssid_scanner                              # Full table with current + nearby
      ssid_scanner --current                    # Just print "MyNetwork"
      ssid_scanner --scan                       # One SSID per line
      ssid_scanner --scan --json                # [{"ssid":"...","bssid":"...","rssi":-42,"channel":6},...]
      ssid_scanner --scan --timeout 30          # Scan with 30s timeout
      ssid_scanner --connect "<SSID>" "<PASSWORD>"
      ssid_scanner --disconnect                   # Drop current Wi-Fi association

    NOTES:
      • Location Services must be enabled system-wide and authorized for this app.
      • The app must be code-signed with a real Apple Development identity (not ad-hoc).
      • If permission was denied: System Settings → Privacy & Security → Location Services
      • Reset permissions: tccutil reset Location com.wifi-controller.ssid-scanner
    """
    print(help)
}

func parseArgs() -> Command {
    let args = Array(CommandLine.arguments.dropFirst())

    if args.isEmpty {
        return .fullReport(timeout: 15)
    }

    var i = 0
    var isScan = false
    var isCurrent = false
    var isJson = false
    var timeout = 15
    var connectSSID: String?
    var password: String?

    while i < args.count {
        switch args[i] {
        case "--help", "-h":
            return .help
        case "--current":
            isCurrent = true
        case "--scan":
            isScan = true
        case "--json":
            isJson = true
        case "--timeout":
            i += 1
            guard i < args.count, let t = Int(args[i]), t > 0 else {
                fputs("Error: --timeout requires a positive integer (seconds)\n", stderr)
                exit(2)
            }
            timeout = t
        case "--disconnect":
            return .disconnect
        case "--connect":
            i += 1
            guard i < args.count else {
                fputs("Error: --connect requires SSID and PASSWORD arguments\n", stderr)
                exit(2)
            }
            connectSSID = args[i]
            i += 1
            guard i < args.count else {
                fputs("Error: --connect requires a PASSWORD argument after SSID\n", stderr)
                fputs("  Usage: --connect '<SSID>' '<PASSWORD>'\n", stderr)
                exit(2)
            }
            password = args[i]
        default:
            fputs("Error: unknown argument '\(args[i])'\n", stderr)
            fputs("Run with --help for usage information.\n", stderr)
            exit(2)
        }
        i += 1
    }

    if isCurrent {
        return .current
    }
    if let ssid = connectSSID {
        return .connect(ssid: ssid, password: password!, timeout: timeout)
    }
    if isScan {
        return .scan(json: isJson, timeout: timeout)
    }
    return .fullReport(timeout: timeout)
}

// MARK: - Location authorization delegate

class LocationDelegate: NSObject, CLLocationManagerDelegate {
    let onAuthorized: () -> Void

    init(onAuthorized: @escaping () -> Void) {
        self.onAuthorized = onAuthorized
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        switch status {
        case .authorizedAlways:
            onAuthorized()
        case .denied, .restricted:
            fputs("Error: Location Services denied or restricted.\n", stderr)
            fputs("Grant access in: System Settings → Privacy & Security → Location Services → SsidScanner\n", stderr)
            exit(1)
        case .notDetermined:
            return
        @unknown default:
            if status.rawValue == 4 {
                onAuthorized()
            }
            return
        }
    }
}

// MARK: - WiFi scanner

class WiFiScanner {

    /// Get current network SSID/BSSID via `ipconfig getsummary` (bypasses redaction).
    func getCurrentNetworkInfo(iface interfaceName: String) -> (ssid: String?, bssid: String?) {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/sbin/ipconfig")
        proc.arguments = ["getsummary", interfaceName]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = FileHandle.nullDevice

        do {
            try proc.run()
            proc.waitUntilExit()
        } catch {
            return (nil, nil)
        }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let output = String(data: data, encoding: .utf8) else { return (nil, nil) }

        var ssid: String?
        var bssid: String?
        for line in output.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("SSID : ") {
                ssid = String(trimmed.dropFirst("SSID : ".count))
            } else if trimmed.hasPrefix("BSSID : ") {
                bssid = String(trimmed.dropFirst("BSSID : ".count))
            }
        }
        return (ssid, bssid)
    }

    /// Get the default Wi-Fi interface, or exit with an error.
    func getInterface() -> CWInterface {
        let client = CWWiFiClient.shared()
        guard let iface = client.interface() else {
            fputs("Error: No Wi-Fi interface found.\n", stderr)
            exit(1)
        }
        return iface
    }

    /// Scan for nearby networks with a configurable timeout.
    func scanNetworks(iface: CWInterface, timeout seconds: Int) -> [CWNetwork] {
        let semaphore = DispatchSemaphore(value: 0)
        var scanResult: Set<CWNetwork>?
        var scanError: Error?

        DispatchQueue.global().async {
            do {
                scanResult = try iface.scanForNetworks(withSSID: nil)
            } catch {
                scanError = error
            }
            semaphore.signal()
        }

        let result = semaphore.wait(timeout: .now() + .seconds(seconds))

        if result == .timedOut {
            fputs("Error: Scan timed out after \(seconds) seconds.\n", stderr)
            exit(1)
        }
        if let error = scanError {
            fputs("Error: Scan failed — \(error.localizedDescription)\n", stderr)
            exit(1)
        }
        guard let networks = scanResult else {
            return []
        }
        return networks.sorted { $0.rssiValue > $1.rssiValue }
    }

    /// Enrich scan results: fill in redacted SSIDs using ipconfig current-network data.
    func enrichedNetworks(
        _ networks: [CWNetwork],
        current: (ssid: String?, bssid: String?)
    ) -> [(ssid: String, bssid: String, rssi: Int, channel: Int)] {
        return networks.map { net in
            var ssid = net.ssid ?? "<hidden>"
            let bssid = net.bssid ?? "?"
            if (ssid == "<hidden>" || ssid.isEmpty),
               let curBSSID = current.bssid,
               bssid.lowercased() == curBSSID.lowercased(),
               let curSSID = current.ssid {
                ssid = curSSID
            }
            let ch = net.wlanChannel?.channelNumber ?? 0
            let rssi = net.rssiValue
            return (ssid: ssid, bssid: bssid, rssi: rssi, channel: ch)
        }
    }

    /// Check if scan results are all redacted, indicating a Location Services problem.
    func checkForRedactedResults(
        _ enriched: [(ssid: String, bssid: String, rssi: Int, channel: Int)]
    ) {
        guard !enriched.isEmpty else { return }
        let allRedacted = enriched.allSatisfy { $0.ssid == "<hidden>" && $0.bssid == "?" }
        guard allRedacted else { return }

        fputs("""

            WARNING: All SSIDs are redacted.

            CoreWLAN is returning <hidden> for every SSID, which means macOS is not
            granting this process access to Wi-Fi scan data despite Location Services
            reporting authorized status.

            This usually means the binary was not launched from inside its .app bundle.
            The wrapper script (ssid_scanner) should handle this automatically. If you
            are running the binary directly, use the full bundle path:

              ./SsidScanner.app/Contents/MacOS/ssid_scanner

            If that also fails, check Location Services:
              System Settings → Privacy & Security → Location Services → SsidScanner

            """,
            stderr
        )
        exit(1)
    }

    // MARK: Command implementations

    func runCurrent() {
        let iface = getInterface()
        let ifName = iface.interfaceName ?? "en0"
        let current = getCurrentNetworkInfo(iface: ifName)
        if let ssid = current.ssid {
            print(ssid)
        } else {
            fputs("Error: Not connected to a Wi-Fi network (or SSID unavailable).\n", stderr)
            exit(1)
        }
    }

    func runScan(json: Bool, timeout: Int) {
        let iface = getInterface()
        let ifName = iface.interfaceName ?? "en0"
        let current = getCurrentNetworkInfo(iface: ifName)
        let networks = scanNetworks(iface: iface, timeout: timeout)
        let enriched = enrichedNetworks(networks, current: current)
        checkForRedactedResults(enriched)

        if json {
            var items: [String] = []
            for net in enriched {
                let escapedSSID = net.ssid
                    .replacingOccurrences(of: "\\", with: "\\\\")
                    .replacingOccurrences(of: "\"", with: "\\\"")
                let escapedBSSID = net.bssid
                    .replacingOccurrences(of: "\\", with: "\\\\")
                    .replacingOccurrences(of: "\"", with: "\\\"")
                items.append(
                    "  {\"ssid\": \"\(escapedSSID)\", \"bssid\": \"\(escapedBSSID)\", " +
                    "\"rssi\": \(net.rssi), \"channel\": \(net.channel)}"
                )
            }
            print("[\n\(items.joined(separator: ",\n"))\n]")
        } else {
            for net in enriched {
                print(net.ssid)
            }
        }
    }

    func runFullReport(timeout: Int) {
        let iface = getInterface()
        let ifName = iface.interfaceName ?? "en0"
        let current = getCurrentNetworkInfo(iface: ifName)

        print("Interface: \(ifName)")
        print("Current network: \(current.ssid ?? "<unavailable>")")
        print("Current BSSID:   \(current.bssid ?? "<unavailable>")")
        print()
        print("Scanning for nearby networks...")
        fflush(stdout)

        let networks = scanNetworks(iface: iface, timeout: timeout)
        let enriched = enrichedNetworks(networks, current: current)
        checkForRedactedResults(enriched)

        print("SSID                              BSSID                RSSI    Channel")
        print("----                              -----                ----    -------")

        for net in enriched {
            print(
                "\(net.ssid.padding(toLength: 32, withPad: " ", startingAt: 0))  " +
                "\(net.bssid.padding(toLength: 19, withPad: " ", startingAt: 0))  " +
                "\(net.rssi) dBm  ch\(net.channel)"
            )
        }
        print("\nFound \(networks.count) networks.")
    }

    func runConnect(ssid targetSSID: String, password: String, timeout: Int) {
        let iface = getInterface()
        let ifName = iface.interfaceName ?? "en0"
        let current = getCurrentNetworkInfo(iface: ifName)

        // Scan to find the CWNetwork object for the target SSID
        let networks = scanNetworks(iface: iface, timeout: timeout)
        let enriched = enrichedNetworks(networks, current: current)

        // Match by enriched SSID name
        var targetNetwork: CWNetwork?
        for (i, net) in enriched.enumerated() {
            if net.ssid == targetSSID {
                targetNetwork = networks.sorted { $0.rssiValue > $1.rssiValue }[i]
                break
            }
        }

        guard let network = targetNetwork else {
            fputs("Error: Network '\(targetSSID)' not found in scan results.\n", stderr)
            fputs("Nearby SSIDs:\n", stderr)
            for net in enriched {
                fputs("  \(net.ssid)\n", stderr)
            }
            exit(1)
        }

        do {
            try iface.associate(to: network, password: password)
        } catch let error as NSError {
            fputs("Error: Failed to connect to '\(targetSSID)'\n", stderr)
            fputs("  Domain: \(error.domain), Code: \(error.code)\n", stderr)
            fputs("  Description: \(error.localizedDescription)\n", stderr)
            if let reason = error.localizedFailureReason {
                fputs("  Reason: \(reason)\n", stderr)
            }
            if let underlying = error.userInfo[NSUnderlyingErrorKey] as? NSError {
                fputs("  Underlying: \(underlying.domain) \(underlying.code) — \(underlying.localizedDescription)\n", stderr)
            }
            exit(1)
        }

        // associate() returns after 802.11 association but before DHCP — poll for IP.
        let pollInterval: useconds_t = 500_000  // 0.5 seconds
        let maxAttempts = timeout * 2
        var connected = false

        for attempt in 1...maxAttempts {
            let info = getConnectionStatus(iface: ifName)
            if let ssid = info.ssid, ssid == targetSSID, let ip = info.ip,
               !ip.isEmpty, ip != "0.0.0.0" {
                connected = true
                print("Connected to '\(targetSSID)' (\(ip))")
                break
            }
            if attempt < maxAttempts {
                usleep(pollInterval)
            }
        }

        if !connected {
            fputs("Error: Associated to '\(targetSSID)' but DHCP did not complete within \(timeout) seconds.\n", stderr)
            exit(1)
        }
    }

    func runDisconnect() {
        let iface = getInterface()
        let ifName = iface.interfaceName ?? "en0"
        let current = getCurrentNetworkInfo(iface: ifName)

        guard let ssid = current.ssid, !ssid.isEmpty else {
            print("Not connected to any Wi-Fi network.")
            return
        }

        iface.disassociate()
        print("Disconnected from '\(ssid)'")
    }

    /// Get current SSID and IP address for the given interface.
    func getConnectionStatus(iface interfaceName: String) -> (ssid: String?, ip: String?) {
        // Get SSID from ipconfig getsummary
        let info = getCurrentNetworkInfo(iface: interfaceName)

        // Get IP from ipconfig getifaddr (returns just the address, or exits non-zero)
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/sbin/ipconfig")
        proc.arguments = ["getifaddr", interfaceName]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = FileHandle.nullDevice

        var ip: String?
        do {
            try proc.run()
            proc.waitUntilExit()
            if proc.terminationStatus == 0 {
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                ip = String(data: data, encoding: .utf8)?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        } catch {}

        return (ssid: info.ssid, ip: ip)
    }
}

// MARK: - Main entry point

let command = parseArgs()

if case .help = command {
    printHelp()
    exit(0)
}

if case .current = command {
    // --current uses ipconfig, no Location Services or scan needed
    WiFiScanner().runCurrent()
    exit(0)
}

if case .disconnect = command {
    WiFiScanner().runDisconnect()
    exit(0)
}

// All other commands need Location Services + NSApplication for the auth popup.
let app = NSApplication.shared
app.setActivationPolicy(.regular)

let locationManager = CLLocationManager()
let scanner = WiFiScanner()

func runCommand() {
    switch command {
    case .scan(let json, let timeout):
        scanner.runScan(json: json, timeout: timeout)
    case .connect(let ssid, let password, let timeout):
        scanner.runConnect(ssid: ssid, password: password, timeout: timeout)
    case .fullReport(let timeout):
        scanner.runFullReport(timeout: timeout)
    case .help, .current, .disconnect:
        break  // Already handled above
    }
    exit(0)
}

let delegate = LocationDelegate {
    runCommand()
}
locationManager.delegate = delegate

let status = locationManager.authorizationStatus
if status == .authorizedAlways || status.rawValue == 4 {
    runCommand()
} else if status == .denied || status == .restricted {
    fputs("Error: Location Services denied or restricted.\n", stderr)
    fputs("Grant access in: System Settings → Privacy & Security → Location Services → SsidScanner\n", stderr)
    exit(1)
} else if !CLLocationManager.locationServicesEnabled() {
    fputs("Error: Location Services is disabled system-wide.\n", stderr)
    fputs("Enable in: System Settings → Privacy & Security → Location Services\n", stderr)
    exit(1)
} else {
    app.activate(ignoringOtherApps: true)
    locationManager.requestAlwaysAuthorization()
    locationManager.startUpdatingLocation()
    app.run()
}
