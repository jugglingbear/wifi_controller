APP_BUNDLE   = SsidScanner.app
BINARY       = $(APP_BUNDLE)/Contents/MacOS/ssid_scanner
SRC          = scan.swift
ENTITLEMENTS = SsidScannerEntitlements.plist
INFO_PLIST   = SsidScannerInfo.plist
FRAMEWORKS   = -framework AppKit -framework CoreWLAN -framework CoreLocation
WRAPPER      = ssid_scanner
BUNDLE_ID    = com.wifi-controller.ssid-scanner

.PHONY: help all build check sign run test clean reset-permissions

help: ## Show this help message
	@echo "\n\033[1mAvailable targets:\033[0m"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

all: build sign ## Build and sign the app bundle (default)

build: $(BINARY) ## Compile the Swift scanner into the app bundle

$(BINARY): $(SRC) $(INFO_PLIST)
	mkdir -p $(APP_BUNDLE)/Contents/MacOS
	cp $(INFO_PLIST) $(APP_BUNDLE)/Contents/Info.plist
	swiftc -o $(BINARY) $(SRC) $(FRAMEWORKS)

LSREGISTER = /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

check: ## Verify build prerequisites are installed
	@ok=true; \
	if ! command -v swiftc >/dev/null 2>&1; then \
		echo ""; \
		echo "  ✘  swiftc not found."; \
		echo ""; \
		echo "  Install Xcode Command Line Tools:"; \
		echo "    xcode-select --install"; \
		echo ""; \
		ok=false; \
	else \
		echo "✔  swiftc found: $$(swiftc --version 2>&1 | head -1)"; \
	fi; \
	if ! command -v codesign >/dev/null 2>&1; then \
		echo ""; \
		echo "  ✘  codesign not found."; \
		echo ""; \
		echo "  Install Xcode Command Line Tools:"; \
		echo "    xcode-select --install"; \
		echo ""; \
		ok=false; \
	else \
		echo "✔  codesign found"; \
	fi; \
	if security find-identity -v -p codesigning 2>/dev/null | grep -q '"Apple Development'; then \
		echo "✔  Apple Development signing identity found."; \
	else \
		echo ""; \
		echo "  ✘  No Apple Development signing identity found."; \
		echo ""; \
		echo "  Ad-hoc signing won't work — macOS requires a real Apple Development"; \
		echo "  certificate for Location Services authorization."; \
		echo ""; \
		echo "  To create one:"; \
		echo "    1. Sign in at https://developer.apple.com (free Apple ID works)"; \
		echo "    2. Open Xcode → Settings (⌘,) → Accounts → add your Apple ID"; \
		echo "    3. Select your account → Manage Certificates → + → Apple Development"; \
		echo "    4. Verify:  security find-identity -v -p codesigning"; \
		echo ""; \
		ok=false; \
	fi; \
	$$ok

sign: check $(BINARY) ## Codesign with developer identity
	codesign --force --sign "Apple Development" --entitlements $(ENTITLEMENTS) $(APP_BUNDLE)
	$(LSREGISTER) -f $(APP_BUNDLE)
	@printf '#!/bin/bash\nexec "$$(dirname "$$0")/$(BINARY)" "$$@"\n' > $(WRAPPER)
	@chmod +x $(WRAPPER)

run: ## Run the scanner (builds first if needed)
	@if [ ! -x "$(WRAPPER)" ]; then $(MAKE) all; fi
	./$(WRAPPER)

test: all ## Scan nearby SSIDs and verify results are not redacted
	@echo "Running scan..."
	@output=$$(./$(WRAPPER) --scan) || { echo "FAIL: scan exited non-zero (SSIDs may be redacted)"; exit 1; }; \
	count=$$(echo "$$output" | grep -c .); \
	if [ "$$count" -eq 0 ]; then echo "FAIL: scan returned no SSIDs"; exit 1; fi; \
	echo "PASS: found $$count SSID(s)"; \
	echo "$$output" | head -5; \
	if [ "$$count" -gt 5 ]; then echo "  ... ($$count total)"; fi

clean: ## Remove the app bundle and wrapper script
	rm -rf $(APP_BUNDLE)
	rm -f $(WRAPPER)

reset-permissions: ## Show instructions to re-authorize Location Services
	@echo ""
	@echo "  If SSIDs are all <hidden>, Location Services permission may need to be re-granted."
	@echo ""
	@echo "  To fix:"
	@echo "    1. Open System Settings → Privacy & Security → Location Services"
	@echo "    2. Find SsidScanner in the list and toggle it OFF, then back ON"
	@echo "    3. If SsidScanner is not listed, run 'make run' to trigger the authorization popup"
	@echo ""
	@open "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices" 2>/dev/null || true
