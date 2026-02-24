"""
Unit tests for services/execution/audit.py

TradeAuditLogger is the compliance backbone: every signal, order, fill,
kill-switch, and rollback event must be written to the JSONL log with the
correct schema.  A missing or malformed field would silently break the
audit trail, so each log_* method is exercised individually.
"""
import asyncio
import json
import os
import pytest
from audit import TradeAuditLogger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def audit(tmp_path):
    """Fresh TradeAuditLogger writing to a temp file for each test."""
    TradeAuditLogger._instance = None
    log_file = str(tmp_path / "test_audit.jsonl")
    os.environ["AUDIT_LOG_PATH"] = log_file
    instance = TradeAuditLogger()
    yield instance
    TradeAuditLogger._instance = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_records(path: str) -> list:
    records = []
    with open(path) as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    return records


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _build_record
# ---------------------------------------------------------------------------

class TestBuildRecord:
    def test_includes_event_type(self, audit):
        rec = audit._build_record("SIGNAL", model_id="m1")
        assert rec["event_type"] == "SIGNAL"

    def test_includes_logged_at_timestamp(self, audit):
        rec = audit._build_record("SIGNAL")
        assert "logged_at" in rec
        assert rec["logged_at"]  # non-empty

    def test_extra_kwargs_are_merged(self, audit):
        rec = audit._build_record("ORDER", symbol="SPY", qty=10, side="buy")
        assert rec["symbol"] == "SPY"
        assert rec["qty"] == 10
        assert rec["side"] == "buy"


# ---------------------------------------------------------------------------
# _write (disk)
# ---------------------------------------------------------------------------

class TestWrite:
    def test_creates_valid_jsonl_line(self, audit):
        rec = {"event_type": "TEST", "logged_at": "2024-01-01T00:00:00+00:00"}
        audit._write(rec)
        records = read_records(audit.log_path)
        assert len(records) == 1
        assert records[0]["event_type"] == "TEST"

    def test_multiple_writes_append_separate_lines(self, audit):
        audit._write({"event_type": "A"})
        audit._write({"event_type": "B"})
        records = read_records(audit.log_path)
        assert len(records) == 2
        assert records[0]["event_type"] == "A"
        assert records[1]["event_type"] == "B"


# ---------------------------------------------------------------------------
# log_signal
# ---------------------------------------------------------------------------

class TestLogSignal:
    def test_writes_signal_event_type(self, audit):
        run(audit.log_signal("lgbm", "v1", "SPY", "BUY", 0.8, 450.0))
        records = read_records(audit.log_path)
        assert records[0]["event_type"] == "SIGNAL"

    def test_all_required_fields_present(self, audit):
        run(audit.log_signal("lgbm", "v1", "SPY", "BUY", 0.8, 450.0))
        rec = read_records(audit.log_path)[0]
        assert rec["model_id"] == "lgbm"
        assert rec["model_version"] == "v1"
        assert rec["symbol"] == "SPY"
        assert rec["signal"] == "BUY"
        assert rec["price"] == 450.0

    def test_confidence_rounded_to_4dp(self, audit):
        run(audit.log_signal("m1", "v1", "SPY", "BUY", 0.123456, 100.0))
        rec = read_records(audit.log_path)[0]
        assert rec["confidence"] == pytest.approx(0.1235, abs=1e-4)

    def test_explanation_defaults_to_empty_list(self, audit):
        run(audit.log_signal("m1", "v1", "SPY", "BUY", 0.9, 100.0))
        assert read_records(audit.log_path)[0]["explanation"] == []

    def test_explanation_stored_when_provided(self, audit):
        xai = [{"feature": "rsi", "impact": 0.5}]
        run(audit.log_signal("m1", "v1", "SPY", "BUY", 0.9, 100.0, explanation=xai))
        assert read_records(audit.log_path)[0]["explanation"] == xai


# ---------------------------------------------------------------------------
# log_order
# ---------------------------------------------------------------------------

class TestLogOrder:
    def test_writes_order_event(self, audit):
        run(audit.log_order("m1", "v1", "SPY", "buy", 10, 450.0, 0.75, "ord-1", "submitted"))
        rec = read_records(audit.log_path)[0]
        assert rec["event_type"] == "ORDER"

    def test_order_fields_correct(self, audit):
        run(audit.log_order("m1", "v1", "SPY", "buy", 10, 450.0, 0.75, "ord-42", "submitted", mode="paper"))
        rec = read_records(audit.log_path)[0]
        assert rec["symbol"] == "SPY"
        assert rec["side"] == "buy"
        assert rec["qty"] == 10
        assert rec["order_id"] == "ord-42"
        assert rec["status"] == "submitted"
        assert rec["mode"] == "paper"


# ---------------------------------------------------------------------------
# log_fill
# ---------------------------------------------------------------------------

class TestLogFill:
    def test_writes_fill_event(self, audit):
        fill = {"symbol": "SPY", "side": "buy", "qty": 5, "price": 450.0, "model_id": "m1"}
        run(audit.log_fill(fill, model_version="v2"))
        rec = read_records(audit.log_path)[0]
        assert rec["event_type"] == "FILL"

    def test_fill_fields_forwarded(self, audit):
        fill = {"symbol": "AAPL", "side": "sell", "qty": 3, "price": 175.0, "model_id": "m2"}
        run(audit.log_fill(fill))
        rec = read_records(audit.log_path)[0]
        assert rec["symbol"] == "AAPL"
        assert rec["qty"] == 3
        assert rec["model_id"] == "m2"


# ---------------------------------------------------------------------------
# log_kill_switch
# ---------------------------------------------------------------------------

class TestLogKillSwitch:
    def test_writes_kill_switch_event(self, audit):
        run(audit.log_kill_switch("drawdown > 3%", -0.032, 97_000.0))
        rec = read_records(audit.log_path)[0]
        assert rec["event_type"] == "KILL_SWITCH"

    def test_kill_switch_fields_correct(self, audit):
        run(audit.log_kill_switch("drawdown > 3%", -0.032, 97_000.0,
                                   model_id="risk", model_version="v1"))
        rec = read_records(audit.log_path)[0]
        assert rec["trigger"] == "drawdown > 3%"
        assert rec["equity"] == 97_000.0
        assert rec["drawdown_pct"] == pytest.approx(-0.032, abs=1e-4)


# ---------------------------------------------------------------------------
# log_manual_approval_mode
# ---------------------------------------------------------------------------

class TestLogManualApprovalMode:
    def test_writes_manual_approval_event(self, audit):
        run(audit.log_manual_approval_mode(
            "sharpe_below_threshold", "Sharpe < 0.5",
            metric_name="sharpe", metric_value=0.4, threshold=0.5
        ))
        rec = read_records(audit.log_path)[0]
        assert rec["event_type"] == "MANUAL_APPROVAL_MODE"

    def test_manual_approval_fields_correct(self, audit):
        run(audit.log_manual_approval_mode(
            "sharpe_below_threshold", "Sharpe dropped",
            metric_name="sharpe", metric_value=0.38, threshold=0.5
        ))
        rec = read_records(audit.log_path)[0]
        assert rec["trigger"] == "sharpe_below_threshold"
        assert rec["reason"] == "Sharpe dropped"
        assert rec["metric_name"] == "sharpe"
        assert rec["metric_value"] == pytest.approx(0.38, abs=1e-4)
        assert rec["threshold"] == pytest.approx(0.5, abs=1e-4)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_instance_returns_same_object(self, tmp_path):
        TradeAuditLogger._instance = None
        os.environ["AUDIT_LOG_PATH"] = str(tmp_path / "s.jsonl")
        a = TradeAuditLogger.get_instance()
        b = TradeAuditLogger.get_instance()
        assert a is b
        TradeAuditLogger._instance = None
