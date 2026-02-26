"""
Shared pytest configuration for TitanFlow integration tests.

Adds each service root to sys.path so tests can import service modules
directly, mirroring the production import style without installation.
"""
import sys
import os

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
