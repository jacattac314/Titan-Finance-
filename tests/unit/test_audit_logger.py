"""
Unit tests for services/execution/audit.py — TradeAuditLogger.

Each test uses the tmp_path pytest fixture to redirect the logger to a
temporary file, avoiding any coupling to the real log directory.  The
singleton is bypassed by constructing TradeAuditLogger directly so tests
remain isolated.

All public log_* methods are async; tests are marked with
@pytest.mark.asyncio and run via pytest-asyncio.
"""
import json
import pytest
import pytest_asyncio

from audit import TradeAuditLogger


# ---------------------------------------------------------------------------
# Fixture: a fresh TradeAuditLogger wired to a temp file
# ---------------------------------------------------------------------------

@pytest.fixture()
def audit_logger(tmp_path):
    """Return a TradeAuditLogger that writes to a temporary JSONL file."""
    log_file = tmp_path / "test_audit.jsonl"
    logger = TradeAuditLogger.__new__(TradeAuditLogger)
    logger.log_path = str(log_file)
    logger._redis_client = None
    return logger


def _read_lines(audit_logger):
    """Return a list of parsed JSON dicts from the log file."""
    with open(audit_logger.log_path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# log_signal
# ---------------------------------------------------------------------------

class TestLogSignal:
    @pytest.mark.asyncio
    async def test_log_signal_writes_line(self, audit_logger):
        """log_signal must append exactly one line to the JSONL file."""
        await audit_logger.log_signal(
            model_id="lgb_spy_v1",
            model_version="v1.0",
            symbol="SPY",
            signal="BUY",
            confidence=0.87,
            price=420.50,
        )
        lines = _read_lines(audit_logger)
        assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_log_signal_required_fields(self, audit_logger):
        """The SIGNAL record must contain event_type, model_id, symbol, timestamp."""
        await audit_logger.log_signal(
            model_id="lgb_spy_v1",
            model_version="v1.0",
            symbol="SPY",
            signal="BUY",
            confidence=0.75,
            price=430.00,
        )
        record = _read_lines(audit_logger)[0]
        assert record["event_type"] == "SIGNAL"
        assert record["model_id"] == "lgb_spy_v1"
        assert record["symbol"] == "SPY"
        assert "logged_at" in record  # timestamp field

    @pytest.mark.asyncio
    async def test_log_signal_line_is_valid_json(self, audit_logger):
        """Each line written by log_signal must be parseable by json.loads."""
        await audit_logger.log_signal(
            model_id="model_x",
            model_version="v2.0",
            symbol="AAPL",
            signal="SELL",
            confidence=0.65,
            price=185.25,
        )
        with open(audit_logger.log_path) as fh:
            raw_line = fh.readline().strip()
        # Must not raise
        parsed = json.loads(raw_line)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_log_signal_creates_file_if_missing(self, tmp_path):
        """The JSONL file must be created automatically when it does not exist."""
        log_file = tmp_path / "subdir" / "new_audit.jsonl"
        logger = TradeAuditLogger.__new__(TradeAuditLogger)
        logger.log_path = str(log_file)
        logger._redis_client = None
        # Ensure parent directory creation works
        import os
        os.makedirs(str(tmp_path / "subdir"), exist_ok=True)
        assert not log_file.exists()
        await logger.log_signal(
            model_id="m1",
            model_version="v1.0",
            symbol="TSLA",
            signal="HOLD",
            confidence=0.5,
            price=200.0,
        )
        assert log_file.exists()

    @pytest.mark.asyncio
    async def test_log_signal_explanation_defaults_to_empty_list(self, audit_logger):
        """When explanation is omitted, the record must contain an empty list."""
        await audit_logger.log_signal(
            model_id="m1",
            model_version="v1.0",
            symbol="NVDA",
            signal="BUY",
            confidence=0.9,
            price=800.0,
        )
        record = _read_lines(audit_logger)[0]
        assert record.get("explanation") == []


# ---------------------------------------------------------------------------
# log_fill
# ---------------------------------------------------------------------------

class TestLogFill:
    @pytest.mark.asyncio
    async def test_log_fill_writes_fill_event(self, audit_logger):
        """log_fill must write a record with event_type == 'FILL'."""
        fill_event = {
            "symbol": "SPY",
            "side": "BUY",
            "qty": 10,
            "price": 421.00,
            "model_id": "lgb_spy_v1",
            "status": "filled",
        }
        await audit_logger.log_fill(fill_event, model_version="v1.0")
        records = _read_lines(audit_logger)
        assert len(records) == 1
        assert records[0]["event_type"] == "FILL"

    @pytest.mark.asyncio
    async def test_log_fill_contains_fill_fields(self, audit_logger):
        """The FILL record must pass through all fields from fill_event."""
        fill_event = {
            "symbol": "AAPL",
            "side": "SELL",
            "qty": 5,
            "price": 190.50,
            "model_id": "aapl_model",
            "status": "filled",
        }
        await audit_logger.log_fill(fill_event, model_version="v2.0")
        record = _read_lines(audit_logger)[0]
        assert record["symbol"] == "AAPL"
        assert record["side"] == "SELL"
        assert record["qty"] == 5
        assert record["model_version"] == "v2.0"
        assert "logged_at" in record

    @pytest.mark.asyncio
    async def test_log_fill_line_is_valid_json(self, audit_logger):
        """Each FILL line must be parseable by json.loads."""
        fill_event = {
            "symbol": "MSFT",
            "side": "BUY",
            "qty": 20,
            "price": 310.00,
            "model_id": "msft_m",
            "status": "partial",
        }
        await audit_logger.log_fill(fill_event)
        with open(audit_logger.log_path) as fh:
            raw_line = fh.readline().strip()
        parsed = json.loads(raw_line)
        assert parsed["event_type"] == "FILL"


# ---------------------------------------------------------------------------
# log_risk_event  (log_kill_switch)
# ---------------------------------------------------------------------------

class TestLogRiskEvent:
    @pytest.mark.asyncio
    async def test_log_kill_switch_writes_risk_event(self, audit_logger):
        """log_kill_switch must write a KILL_SWITCH record."""
        await audit_logger.log_kill_switch(
            trigger="drawdown > 3%",
            drawdown_pct=-0.031,
            equity=96_900.0,
            model_id="system",
            model_version="v1.0",
        )
        records = _read_lines(audit_logger)
        assert len(records) == 1
        assert records[0]["event_type"] == "KILL_SWITCH"

    @pytest.mark.asyncio
    async def test_log_kill_switch_required_fields(self, audit_logger):
        """KILL_SWITCH record must contain event_type, model_id, and timestamp."""
        await audit_logger.log_kill_switch(
            trigger="consecutive_losses >= 5",
            drawdown_pct=-0.02,
            equity=98_000.0,
        )
        record = _read_lines(audit_logger)[0]
        assert record["event_type"] == "KILL_SWITCH"
        assert "model_id" in record
        assert "logged_at" in record

    @pytest.mark.asyncio
    async def test_log_kill_switch_line_is_valid_json(self, audit_logger):
        """Each KILL_SWITCH line must be parseable by json.loads."""
        await audit_logger.log_kill_switch(
            trigger="drawdown > 3%",
            drawdown_pct=-0.035,
            equity=96_500.0,
        )
        with open(audit_logger.log_path) as fh:
            raw_line = fh.readline().strip()
        parsed = json.loads(raw_line)
        assert parsed["event_type"] == "KILL_SWITCH"

    @pytest.mark.asyncio
    async def test_multiple_events_append_separate_lines(self, audit_logger):
        """Each call to a log_* method must produce its own line in the JSONL file."""
        await audit_logger.log_signal(
            model_id="m1",
            model_version="v1.0",
            symbol="SPY",
            signal="BUY",
            confidence=0.8,
            price=440.0,
        )
        fill_event = {
            "symbol": "SPY",
            "side": "BUY",
            "qty": 10,
            "price": 440.0,
            "model_id": "m1",
            "status": "filled",
        }
        await audit_logger.log_fill(fill_event)
        await audit_logger.log_kill_switch(
            trigger="drawdown > 3%",
            drawdown_pct=-0.031,
            equity=96_900.0,
        )
        lines = _read_lines(audit_logger)
        assert len(lines) == 3
        event_types = [r["event_type"] for r in lines]
        assert event_types == ["SIGNAL", "FILL", "KILL_SWITCH"]
