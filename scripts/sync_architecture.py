#!/usr/bin/env python3
"""
sync_architecture.py
====================
Introspects the TitanFlow service code and updates the AUTO-generated sections
of docs/ARCHITECTURE.md with the current implementation state.

Run automatically by:
  - .githooks/pre-commit  (when services/**/*.py files are staged)
  - .github/workflows/docs-sync.yml  (on push to main with service changes)
  - Manually: python scripts/sync_architecture.py

Exits with code 1 if the doc was changed (useful in CI to flag drift).
Exits with code 0 if nothing changed.

AUTO sections are fenced by HTML comment markers inside ARCHITECTURE.md:
    <!-- AUTO:section-name:start -->
    ...generated content...
    <!-- AUTO:section-name:end -->
"""

import os
import re
import sys
import difflib
import datetime
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCH_DOC = REPO_ROOT / "docs" / "ARCHITECTURE.md"
SERVICES_DIR = REPO_ROOT / "services"


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

def _iter_py_files(root: Path):
    """Yield all .py files under root, skipping __pycache__."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fname in filenames:
            if fname.endswith(".py"):
                yield Path(dirpath) / fname


def collect_redis_channels() -> dict:
    """
    Return a dict mapping channel name → {"publishes": [service, ...], "subscribes": [service, ...]}.
    """
    publish_re = re.compile(r'\.publish\(\s*["\']([^"\']+)["\']')
    subscribe_re = re.compile(r'\.subscribe\(([^)]+)\)')
    channel_name_re = re.compile(r'["\']([^"\']+)["\']')

    channels: dict = defaultdict(lambda: {"publishes": [], "subscribes": []})

    for py_file in _iter_py_files(SERVICES_DIR):
        # Derive a short service name from the path
        rel = py_file.relative_to(SERVICES_DIR)
        service = rel.parts[0]  # e.g. "gateway", "signal", "risk", "execution"
        text = py_file.read_text(errors="replace")

        for match in publish_re.finditer(text):
            ch = match.group(1)
            entry = channels[ch]["publishes"]
            if service not in entry:
                entry.append(service)

        for match in subscribe_re.finditer(text):
            args_text = match.group(1)
            for ch_match in channel_name_re.finditer(args_text):
                ch = ch_match.group(1)
                entry = channels[ch]["subscribes"]
                if service not in entry:
                    entry.append(service)

    # Also scan the Next.js dashboard server (JavaScript) for subscribe calls
    # so the channel table shows "dashboard" as a subscriber where applicable.
    _js_subscribe_re = re.compile(r'\.subscribe\(\s*["\']([^"\']+)["\']')
    dashboard_server = REPO_ROOT / "dashboard" / "server.js"
    if dashboard_server.exists():
        js_text = dashboard_server.read_text(errors="replace")
        for m in _js_subscribe_re.finditer(js_text):
            ch = m.group(1)
            entry = channels[ch]["subscribes"]
            if "dashboard" not in entry:
                entry.append("dashboard")

    return dict(channels)


def collect_data_providers() -> list[dict]:
    """Return list of {class_name, file, description} for each provider."""
    providers_dir = SERVICES_DIR / "gateway" / "providers"
    if not providers_dir.exists():
        return []

    class_re = re.compile(r'^class\s+(\w+)\s*\(', re.MULTILINE)
    skip = {"DataProvider"}  # abstract base
    results = []

    for py_file in sorted(providers_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        text = py_file.read_text(errors="replace")
        for m in class_re.finditer(text):
            cls = m.group(1)
            if cls not in skip:
                rel = py_file.relative_to(REPO_ROOT)
                # Guess a description from the class name
                if "alpaca" in py_file.name.lower():
                    desc = "Primary — live IEX stream"
                elif "synthetic" in py_file.name.lower():
                    desc = "Deterministic random walk for local dev/CI"
                elif "yahoo" in py_file.name.lower():
                    desc = "Fallback — planned, not yet built"
                elif "polygon" in py_file.name.lower():
                    desc = "Planned — not yet built"
                elif "binance" in py_file.name.lower():
                    desc = "Planned — not yet built"
                else:
                    desc = ""
                results.append({"class": cls, "file": str(rel), "desc": desc})
    return results


def collect_strategies() -> list[dict]:
    """Return list of {class_name, file, model_type} for each strategy."""
    strats_dir = SERVICES_DIR / "signal" / "strategies"
    if not strats_dir.exists():
        return []

    class_re = re.compile(r'^class\s+(\w+)\s*\(', re.MULTILINE)
    # Skip files that define abstract bases, not concrete strategies
    skip_files = {"base.py", "__init__.py"}
    skip_classes = {"BaseStrategy", "Strategy"}
    results = []

    type_hints = {
        "sma": "Rule-based",
        "rsi": "Rule-based",
        "lightgbm": "Gradient boosting",
        "lstm": "Deep learning",
        "tft": "Transformer",
        "ppo": "Reinforcement learning",
    }

    for py_file in sorted(strats_dir.glob("*.py")):
        if py_file.name in skip_files:
            continue
        text = py_file.read_text(errors="replace")
        for m in class_re.finditer(text):
            cls = m.group(1)
            if cls not in skip_classes:
                rel = py_file.relative_to(REPO_ROOT)
                lower = py_file.name.lower()
                model_type = next((v for k, v in type_hints.items() if k in lower), "")
                results.append({"class": cls, "file": str(rel), "type": model_type})
    return results


def collect_models() -> list[dict]:
    """Return list of {class_name, file, architecture} for each top-level model."""
    models_dir = SERVICES_DIR / "signal" / "models"
    if not models_dir.exists():
        return []

    class_re = re.compile(r'^class\s+(\w+)\s*\(', re.MULTILINE)
    # Only include classes whose name ends with "Model" — helper building blocks
    # (AttentionBlock, PositionalEncoding, etc.) are intentionally excluded.
    results = []

    arch_hints = {
        "lstm": "LSTM with attention",
        "tft": "Temporal Fusion Transformer",
        "hybrid": "Hybrid ensemble",
    }

    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        text = py_file.read_text(errors="replace")
        for m in class_re.finditer(text):
            cls = m.group(1)
            if cls.endswith("Model"):
                rel = py_file.relative_to(REPO_ROOT)
                lower = py_file.name.lower()
                arch = next((v for k, v in arch_hints.items() if k in lower), "")
                results.append({"class": cls, "file": str(rel), "arch": arch})
    return results


# ---------------------------------------------------------------------------
# Markdown table generators
# ---------------------------------------------------------------------------

_CHANNEL_DESCRIPTIONS = {
    "market_data": "normalised tick",
    "trade_signals": "BUY/SELL + confidence + explanation",
    "execution_requests": "risk-approved order (qty, side, model_id)",
    "execution_filled": "fill event",
    "risk_commands": "LIQUIDATE_ALL / ACTIVATE_MANUAL_APPROVAL",
    "paper_portfolio_updates": "leaderboard snapshot",
    "audit_events": "audit trail record",
}


def _generate_channels_table(channels: dict) -> str:
    header = "| Channel | Publisher(s) | Subscriber(s) | Payload |\n|---|---|---|---|\n"
    rows = []
    for ch in sorted(channels):
        info = channels[ch]
        pubs = ", ".join(sorted(info["publishes"])) or "—"
        subs = ", ".join(sorted(info["subscribes"])) or "—"
        payload = _CHANNEL_DESCRIPTIONS.get(ch, "")
        rows.append(f"| `{ch}` | {pubs} | {subs} | {payload} |")
    return header + "\n".join(rows)


def _generate_providers_table(providers: list) -> str:
    header = "| Provider | File | Notes |\n|---|---|---|\n"
    rows = [f"| `{p['class']}` | `{p['file']}` | {p['desc']} |" for p in providers]
    return header + "\n".join(rows)


def _generate_strategies_table(strategies: list) -> str:
    header = "| Strategy | File | Model type |\n|---|---|---|\n"
    rows = [f"| `{s['class']}` | `{s['file']}` | {s['type']} |" for s in strategies]
    return header + "\n".join(rows)


def _generate_models_table(models: list) -> str:
    header = "| Model class | File | Architecture |\n|---|---|---|\n"
    rows = [f"| `{m['class']}` | `{m['file']}` | {m['arch']} |" for m in models]
    return header + "\n".join(rows)


# ---------------------------------------------------------------------------
# Document section updater
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    r'(<!-- AUTO:(?P<name>[^:]+):start -->)\n.*?\n(<!-- AUTO:(?P=name):end -->)',
    re.DOTALL,
)


def update_doc(doc_text: str, section_name: str, new_content: str) -> str:
    """
    Replace the content between AUTO markers for *section_name*.
    If markers are absent, the doc is returned unchanged.
    """
    pattern = re.compile(
        r'(<!-- AUTO:' + re.escape(section_name) + r':start -->)\n'
        r'(.*?)\n'
        r'(<!-- AUTO:' + re.escape(section_name) + r':end -->)',
        re.DOTALL,
    )
    replacement = r'\1\n' + new_content + r'\n\3'
    updated, count = pattern.subn(replacement, doc_text)
    if count == 0:
        print(f"  [warn] AUTO:{section_name} markers not found in doc — skipping.", file=sys.stderr)
    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> int:
    """Returns 1 if the doc was modified, 0 otherwise."""
    print(f"sync_architecture.py — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    print(f"Repo root: {REPO_ROOT}")

    # --- Introspect ---
    print("\nIntrospecting service code…")
    channels = collect_redis_channels()
    providers = collect_data_providers()
    strategies = collect_strategies()
    models = collect_models()

    print(f"  channels:   {sorted(channels)}")
    print(f"  providers:  {[p['class'] for p in providers]}")
    print(f"  strategies: {[s['class'] for s in strategies]}")
    print(f"  models:     {[m['class'] for m in models]}")

    # --- Read doc ---
    original = ARCH_DOC.read_text()
    updated = original

    # --- Update each AUTO section ---
    updated = update_doc(updated, "channels", _generate_channels_table(channels))
    updated = update_doc(updated, "providers", _generate_providers_table(providers))
    updated = update_doc(updated, "strategies", _generate_strategies_table(strategies))
    updated = update_doc(updated, "models", _generate_models_table(models))

    # --- Diff ---
    if updated == original:
        print("\nNo changes — ARCHITECTURE.md is already in sync.")
        return 0

    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile="ARCHITECTURE.md (before)",
        tofile="ARCHITECTURE.md (after)",
    ))

    print(f"\nChanges detected ({len(diff)} diff lines):")
    for line in diff[:80]:  # cap output at 80 lines
        print(line, end="")
    if len(diff) > 80:
        print(f"\n  … ({len(diff) - 80} more diff lines truncated)")

    ARCH_DOC.write_text(updated)
    print(f"\nUpdated {ARCH_DOC.relative_to(REPO_ROOT)}")
    return 1  # signal to CI/hook that the file changed


if __name__ == "__main__":
    sys.exit(run())
