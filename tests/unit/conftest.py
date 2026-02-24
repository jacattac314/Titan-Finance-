"""
Shared pytest configuration for Titan Finance unit tests.

Adds each service root to sys.path so tests can import service modules
without installing them as packages.
"""
import sys
import os

# Services that have unit tests
_SERVICE_ROOTS = [
    "services/risk",
    "services/execution",
    "services/signal",
    "services/gateway",
]

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

for _rel in _SERVICE_ROOTS:
    _abs = os.path.join(_REPO_ROOT, _rel)
    if _abs not in sys.path:
        sys.path.insert(0, _abs)
