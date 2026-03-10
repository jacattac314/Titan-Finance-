"""
Titan Finance — Multi-Agent Audit System
=========================================
Deploys a team of four specialist AI agents coordinated by an orchestrator to
conduct a comprehensive audit of the Titan Finance algorithmic trading platform.

Agent roster
------------
  orchestrator   — coordinates the team, compiles and writes the final report
  trade-auditor  — analyses JSONL audit logs for anomalies and compliance gaps
  risk-analyst   — reviews risk controls, circuit-breaker logic, thresholds
  signal-analyst — evaluates signal quality, ML hygiene, and feature engineering
  code-inspector — scans for security vulnerabilities and code quality issues

Usage
-----
    pip install -r agents/requirements.txt
    python agents/audit_team.py

The final Markdown report is written to ./logs/audit_report.md.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anyio
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())
REPORT_OUTPUT = os.path.join(PROJECT_ROOT, "logs", "audit_report.md")

# ── Specialist agent definitions ───────────────────────────────────────────────

AGENTS: dict[str, AgentDefinition] = {
    # ------------------------------------------------------------------
    # 1. Trade Auditor — compliance and log-integrity review
    # ------------------------------------------------------------------
    "trade-auditor": AgentDefinition(
        description=(
            "Financial compliance specialist that analyses JSONL trade audit "
            "logs produced by Titan Finance's TradeAuditLogger. Identifies "
            "anomalies, missing fills, duplicate events, low-confidence signal "
            "execution, kill-switch activations, and data-integrity issues."
        ),
        prompt=(
            "You are a financial compliance auditor for an institutional algorithmic "
            "trading platform.\n\n"
            "TASK: Conduct a thorough audit of the trade audit trail.\n\n"
            "Steps:\n"
            "1. Read services/execution/audit.py to understand the event schema "
            "   (SIGNAL, ORDER, FILL, KILL_SWITCH, MANUAL_APPROVAL_MODE).\n"
            "2. Search for JSONL log files under ./logs/ (use Glob and Bash).\n"
            "3. If log files exist, analyse them for:\n"
            "   a) Event-type distribution (counts per type).\n"
            "   b) ORDER events without a subsequent FILL — potential orphaned orders.\n"
            "   c) SIGNAL events with confidence < 0.5 that were still executed.\n"
            "   d) KILL_SWITCH events: triggers, drawdown values, frequency.\n"
            "   e) MANUAL_APPROVAL_MODE events and their causes.\n"
            "   f) Timestamp gaps > 10 minutes that might indicate service outages.\n"
            "   g) Duplicate event IDs or identical consecutive records.\n"
            "4. If no logs exist yet, document the absence and note what data would "
            "   be expected in a live deployment.\n"
            "5. Assess the overall integrity of the audit schema design.\n\n"
            "Output a structured findings section with specific counts and examples."
        ),
        tools=["Read", "Glob", "Grep", "Bash"],
    ),

    # ------------------------------------------------------------------
    # 2. Risk Analyst — risk controls and circuit-breaker review
    # ------------------------------------------------------------------
    "risk-analyst": AgentDefinition(
        description=(
            "Quantitative risk analyst that reviews Titan Finance's risk "
            "management engine, kill-switch logic, position-sizing formulas, "
            "model-performance rollback thresholds, and configuration parameters."
        ),
        prompt=(
            "You are a senior quantitative risk analyst auditing an algorithmic "
            "trading platform's risk governance layer.\n\n"
            "TASK: Assess correctness, completeness, and adequacy of all risk controls.\n\n"
            "Files to review:\n"
            "  • services/risk/risk_engine.py\n"
            "  • services/execution/risk/validator.py\n"
            "  • .env.example  (configuration defaults)\n"
            "  • services/execution/main.py  (how risk is integrated)\n\n"
            "Assess:\n"
            "1. Kill-switch / circuit-breaker logic:\n"
            "   - Is drawdown_pct calculated correctly relative to start-of-day equity?\n"
            "   - What happens when starting_equity == 0 (edge case)?\n"
            "   - Is the consecutive-loss counter reset correctly after a win?\n"
            "2. Position sizing:\n"
            "   - Fixed-fractional formula correctness.\n"
            "   - Edge case: stop_loss == entry_price (division by zero guard).\n"
            "   - Is max_position_size enforced anywhere?\n"
            "3. Model-performance rollback:\n"
            "   - Rolling window size (20 trades) — is this adequate for Sharpe estimation?\n"
            "   - Minimum 5 observations before computing metrics — risk of premature rollback?\n"
            "   - Is there a mechanism to automatically exit manual-approval mode?\n"
            "4. Configuration gaps:\n"
            "   - Are all env vars validated at startup?\n"
            "   - What are the risks of the default thresholds (3% daily loss, 5 losses)?\n"
            "5. Integration:\n"
            "   - Does the execution service actually call risk validation before every order?\n\n"
            "Use CRITICAL / HIGH / MEDIUM / LOW severity. Cite file:line for each finding."
        ),
        tools=["Read", "Glob", "Grep"],
    ),

    # ------------------------------------------------------------------
    # 3. Signal Analyst — ML signal pipeline review
    # ------------------------------------------------------------------
    "signal-analyst": AgentDefinition(
        description=(
            "Quantitative researcher that evaluates Titan Finance's ML signal "
            "generation pipeline, covering strategy implementations, feature "
            "engineering, model confidence calibration, SHAP explainability, "
            "and look-ahead bias risks."
        ),
        prompt=(
            "You are a quantitative researcher auditing the signal generation "
            "pipeline of an algorithmic trading platform.\n\n"
            "TASK: Identify weaknesses, logic errors, and ML hygiene issues.\n\n"
            "Files to review:\n"
            "  • services/signal/strategies.py (base strategies + RSI/SMA)\n"
            "  • services/signal/strategies/  (all strategy files)\n"
            "  • services/signal/feature_engineering.py\n"
            "  • services/signal/model.py\n"
            "  • services/signal/explainability.py\n"
            "  • services/signal/main.py\n\n"
            "Assess:\n"
            "1. Strategy logic correctness:\n"
            "   - SMA crossover: is the look-back window adequate? min_spread_pct guard?\n"
            "   - RSI mean reversion: boundary conditions at RSI=0 or RSI=100?\n"
            "   - LightGBM / LSTM / TFT strategies: how is missing model file handled?\n"
            "2. Feature engineering:\n"
            "   - Any features that use future data (look-ahead bias)?\n"
            "   - Are NaN values handled before model inference?\n"
            "   - Is feature scaling consistent between training and inference?\n"
            "3. Confidence calibration:\n"
            "   - Are confidence scores clipped to [0, 1]?\n"
            "   - SMA confidence formula: `min(abs(spread_pct)/0.02, 1.0)` — "
            "     is the 0.02 denominator justified?\n"
            "4. SHAP explainability:\n"
            "   - Is SHAP computed correctly for non-tree models?\n"
            "   - Are explanation lists formatted correctly for the audit schema?\n"
            "5. Signal ensemble / voting:\n"
            "   - How are conflicting signals from multiple strategies resolved?\n"
            "   - Is there a risk of signal amplification or cancellation?\n"
            "6. Overfitting / data leakage:\n"
            "   - Are train/test splits handled in the strategy files or upstream?\n\n"
            "Cite file:line for every finding. Use HIGH / MEDIUM / LOW severity."
        ),
        tools=["Read", "Glob", "Grep"],
    ),

    # ------------------------------------------------------------------
    # 4. Code Inspector — security and code quality review
    # ------------------------------------------------------------------
    "code-inspector": AgentDefinition(
        description=(
            "Security engineer that scans the Titan Finance microservices for "
            "hardcoded secrets, injection vulnerabilities, insecure error handling, "
            "missing input validation, dependency risks, and Python anti-patterns."
        ),
        prompt=(
            "You are a security engineer conducting a full code audit of a Python "
            "microservices-based algorithmic trading platform.\n\n"
            "TASK: Identify security vulnerabilities and critical code-quality issues.\n\n"
            "Directories to scan:\n"
            "  • services/  (all sub-services)\n"
            "  • scripts/\n"
            "  • dashboard/  (Next.js — spot-check for secrets)\n\n"
            "Report findings in these categories:\n"
            "1. SECRETS & CREDENTIALS\n"
            "   - Grep for hardcoded API keys, passwords, tokens, connection strings.\n"
            "   - Check that all secrets come from env vars, not defaults with real values.\n"
            "2. INJECTION RISKS\n"
            "   - SQL injection: f-strings or .format() in SQL queries.\n"
            "   - Shell injection: subprocess calls with user-controlled input.\n"
            "   - Redis key injection from untrusted input.\n"
            "3. ERROR HANDLING\n"
            "   - Bare `except:` or `except Exception:` that silence all errors.\n"
            "   - Missing error handling on network calls, DB writes, file I/O.\n"
            "   - Audit logger failures that could cause silent data loss.\n"
            "4. INPUT VALIDATION\n"
            "   - Are signal dict fields validated before use (type, range)?\n"
            "   - Are Alpaca API responses validated before trusting order IDs?\n"
            "5. SERVICE AUTHENTICATION\n"
            "   - Is Redis access authenticated (password/TLS)?\n"
            "   - Are inter-service calls validated (no open WebSocket endpoints)?\n"
            "6. DEPENDENCIES\n"
            "   - Check requirements.txt files for pinned versions.\n"
            "   - Flag any packages with known CVEs (based on your knowledge).\n"
            "   - Note any unpinned (`>=`) dependencies that could break on update.\n"
            "7. CODE QUALITY\n"
            "   - Singleton patterns used correctly (TradeAuditLogger)?\n"
            "   - Thread/async safety issues in shared state?\n"
            "   - Dead code, unused imports, or commented-out credentials.\n\n"
            "Use CRITICAL / HIGH / MEDIUM / LOW severity. Cite file:line for each finding."
        ),
        tools=["Read", "Glob", "Grep", "Bash"],
    ),
}

# ── Orchestrator prompt ────────────────────────────────────────────────────────

_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

ORCHESTRATOR_PROMPT = f"""
You are the Lead Audit Director for Titan Finance, an institutional-grade
algorithmic trading platform built on Python microservices, Redis pub/sub,
QuestDB, and PostgreSQL.

Your task is to coordinate four specialist agents to audit the platform end-to-end,
then compile and persist a professional Markdown audit report.

Working directory : {PROJECT_ROOT}
Report output path: {REPORT_OUTPUT}
Audit date        : {_TODAY}

═══════════════════════════════════════════════════
STEP 1 — DELEGATE TO SPECIALIST AGENTS (in order)
═══════════════════════════════════════════════════

Run each agent and record all findings:

  1. trade-auditor   → Trade log compliance and audit-trail integrity
  2. risk-analyst    → Risk controls, kill-switch logic, position sizing
  3. signal-analyst  → ML signal pipeline quality and correctness
  4. code-inspector  → Security vulnerabilities and code quality

═══════════════════════════════════════════════════
STEP 2 — COMPILE THE FINAL REPORT
═══════════════════════════════════════════════════

After all agents have reported, write the following Markdown document to:
  {REPORT_OUTPUT}

Use this exact structure (fill in all sections with real findings):

---
# Titan Finance — Comprehensive Audit Report

**Date:** {_TODAY}
**Auditor:** Titan Multi-Agent Audit Team (claude-opus-4-6)
**Scope:** Trade logs · Risk controls · Signal pipeline · Codebase security
**Project root:** {PROJECT_ROOT}

---

## Executive Summary

> _(3–6 bullet points covering the most critical findings across all domains)_

---

## 1. Trade Log & Audit Trail

_(Full findings from trade-auditor: event counts, anomalies, integrity assessment)_

---

## 2. Risk Management Review

_(Full findings from risk-analyst: severity-rated issues with file:line references)_

---

## 3. Signal Quality Assessment

_(Full findings from signal-analyst: strategy correctness, ML hygiene issues)_

---

## 4. Security & Code Quality

_(Full findings from code-inspector: vulnerabilities, dependency risks, patterns)_

---

## 5. Prioritised Recommendations

| Priority | Finding | Recommended Action |
|----------|---------|-------------------|
| CRITICAL | ... | ... |
| HIGH     | ... | ... |
| MEDIUM   | ... | ... |
| LOW      | ... | ... |

---

## 6. Audit Conclusion

**Overall Platform Health:** PASS / CONDITIONAL PASS / FAIL

_(2–3 sentence justification)_

---
*Report generated by the Titan Finance Multi-Agent Audit System.*
---

Write the completed report to {REPORT_OUTPUT} using the Write tool.
After writing, confirm the file path and summarise the verdict.
"""

# ── Entry point ────────────────────────────────────────────────────────────────


async def run_audit() -> int:
    """Run the full multi-agent audit and return exit code (0=success, 1=error)."""
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)

    print("╔══════════════════════════════════════════════════════════╗")
    print("║       TITAN FINANCE — MULTI-AGENT AUDIT SYSTEM          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Project root : {PROJECT_ROOT}")
    print(f"  Report output: {REPORT_OUTPUT}")
    print(f"  Date         : {_TODAY}")
    print()
    print("  Agents:")
    for name, agent in AGENTS.items():
        print(f"    • {name}")
    print()
    print("  Starting audit…")
    print()

    result_text: str | None = None
    session_id: str | None = None

    try:
        async for message in query(
            prompt=ORCHESTRATOR_PROMPT,
            options=ClaudeAgentOptions(
                cwd=PROJECT_ROOT,
                allowed_tools=["Read", "Glob", "Grep", "Bash", "Write", "Agent"],
                permission_mode="acceptEdits",
                model="claude-opus-4-6",
                max_turns=120,
                agents=AGENTS,
                system_prompt=(
                    "You are the Lead Audit Director. Always delegate to the specialist "
                    "agents before compiling the report. Use the Write tool to persist "
                    "the completed Markdown report to disk."
                ),
            ),
        ):
            if isinstance(message, SystemMessage) and message.subtype == "init":
                session_id = message.session_id
                print(f"[Session ID: {session_id}]")
                print()
            elif isinstance(message, ResultMessage):
                result_text = message.result

    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERROR] Audit failed: {exc}", file=sys.stderr)
        return 1

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                    AUDIT COMPLETE                       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if result_text:
        print(result_text)

    report_path = Path(REPORT_OUTPUT)
    if report_path.exists():
        size_kb = report_path.stat().st_size / 1024
        print(f"\n  Report written → {REPORT_OUTPUT}  ({size_kb:.1f} KB)")
    else:
        print(
            "\n  [Warning] Report file was not created. "
            "Check the orchestrator output above.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(run_audit))
