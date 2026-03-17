"""Root conftest for wifi_controller tests.

Adds the tests/wifi_controller directory to sys.path so that shared
test helpers (e.g., _fakes.py) are importable from any test module.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "wifi_controller"))
