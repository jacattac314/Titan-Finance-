"""
Shared pytest configuration for Titan Finance unit tests.

Adds each service root and the shared/ directory to sys.path so tests can
import service modules and shared utilities without installing them as packages.
"""
import sys
import os

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# shared/ must be on the path first so service modules can resolve
# `from schemas import ...` and `from health import ...`
_SHARED_ROOT = os.path.join(_REPO_ROOT, "shared")
if _SHARED_ROOT not in sys.path:
    sys.path.insert(0, _SHARED_ROOT)

# Services that have unit tests
_SERVICE_ROOTS = [
    "services/risk",
    "services/execution",
    "services/signal",
    "services/gateway",
]

for _rel in _SERVICE_ROOTS:
    _abs = os.path.join(_REPO_ROOT, _rel)
    if _abs not in sys.path:
        sys.path.insert(0, _abs)
