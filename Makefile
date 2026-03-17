# ── WiFi Controller ───────────────────────────────────────
# Cross-platform Wi-Fi controller with pluggable providers.
# Type "make help" to see available targets.
# ──────────────────────────────────────────────────────────

PYTHON   ?= python3
POETRY   ?= poetry
SRC_DIR  := src
TEST_DIR := tests

# ── Help (default target) ────────────────────────────────

.PHONY: help
help:  ## Show this help message
	@echo "\n\033[1mAvailable targets:\033[0m"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Environment ──────────────────────────────────────────

.PHONY: check
check:  ## Verify that required development tools are installed
	@echo "\n\033[1mChecking development environment...\033[0m"
	@ok=true; \
	command -v $(PYTHON) >/dev/null 2>&1 \
		&& echo "  ✅ python3       $$($(PYTHON) --version 2>&1 | awk '{print $$2}')" \
		|| { echo "  ❌ python3       not found"; ok=false; }; \
	command -v $(POETRY) >/dev/null 2>&1 \
		&& echo "  ✅ poetry        $$($(POETRY) --version 2>&1 | sed 's/[^0-9.]//g')" \
		|| { echo "  ❌ poetry        not found — install from https://python-poetry.org"; ok=false; }; \
	if command -v $(PYTHON) >/dev/null 2>&1; then \
		py_ver=$$($(PYTHON) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"); \
		py_maj=$$(echo "$$py_ver" | cut -d. -f1); \
		py_min=$$(echo "$$py_ver" | cut -d. -f2); \
		if [ "$$py_maj" -gt 3 ] || { [ "$$py_maj" -eq 3 ] && [ "$$py_min" -ge 10 ]; }; then \
			echo "  ✅ python >=3.10  $$py_ver"; \
		else \
			echo "  ❌ python >=3.10  found $$py_ver (need 3.10+)"; ok=false; \
		fi; \
	fi; \
	if [ -d .venv ]; then \
		echo "  ✅ .venv         exists"; \
	else \
		echo "  ⚠️  .venv         not found — run 'make install'"; \
	fi; \
	if $(POETRY) run $(PYTHON) -c "import bear_tools" 2>/dev/null; then \
		bt_ver=$$($(POETRY) run $(PYTHON) -c "import bear_tools; print(bear_tools.__version__)" 2>/dev/null || echo "unknown"); \
		echo "  ✅ bear_tools    $$bt_ver"; \
	else \
		echo "  ❌ bear_tools    not found — pip install bear_tools"; ok=false; \
	fi; \
	$$ok || { echo "\n\033[31mEnvironment check failed.\033[0m\n"; exit 1; }; \
	echo "\n\033[32mAll checks passed.\033[0m\n"

.PHONY: install
install:  ## Install project dependencies via Poetry
	@echo "📦 Installing dependencies"
	$(POETRY) install

# ── Testing ──────────────────────────────────────────────

.PHONY: test
test:  install  ## Run unit tests
	@echo "🧪 Running unit tests"
	$(POETRY) run pytest -v $(TEST_DIR)

.PHONY: coverage
coverage:  ## Run tests with coverage report
	@echo "🎯 Analyzing test coverage"
	$(POETRY) run pytest --cov=$(SRC_DIR) --cov-report=term-missing $(TEST_DIR)

# ── Code Quality ─────────────────────────────────────────

.PHONY: lint
lint:  ## Run ruff linter on source code
	@echo "🧹 Running linters"
	$(POETRY) run ruff check $(SRC_DIR)

.PHONY: format
format:  ## Auto-format source code with ruff
	@echo "🧹 Formatting code"
	$(POETRY) run ruff check --fix $(SRC_DIR)
	$(POETRY) run ruff format $(SRC_DIR)

# ── Documentation ─────────────────────────────────────────

PLANTUML ?= plantuml
DOCS_DIR := docs

.PHONY: docs
docs:  ## 📐 Render PlantUML diagrams to SVG
	@echo "📐 Rendering PlantUML diagrams"
	$(PLANTUML) -tsvg $(DOCS_DIR)/*.puml

# ── Packaging / Distribution ─────────────────────────────

.PHONY: publish
publish:  ## 📦 Build and publish package to PyPI
	@echo "📦 Building release package for PyPI"
	$(POETRY) build
	$(POETRY) publish

# ── Extras (opt-in) ───────────────────────────────────────

.PHONY: ssid-scanner
ssid-scanner:  ## 🍎 Build + sign the macOS SSID scanner (extras/)
	$(MAKE) -C extras/ssid_scanner all

.PHONY: ssid-scanner-clean
ssid-scanner-clean:  ## 🍎 Remove SSID scanner build artifacts
	$(MAKE) -C extras/ssid_scanner clean

# ── Cleanup ──────────────────────────────────────────────

.PHONY: clean
clean:  ## Remove build artifacts and caches
	@echo "🧼 Cleaning up"
	rm -rf dist .pytest_cache .ruff_cache .mypy_cache
	rm -f $(DOCS_DIR)/*.svg
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.PHONY: reinstall
reinstall: clean  ## Delete .venv and reinstall from scratch
	@echo "🔄 Rebuilding virtual environment"
	rm -rf .venv
	$(POETRY) install
