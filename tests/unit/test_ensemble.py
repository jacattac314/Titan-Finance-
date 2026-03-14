"""
Unit tests for services/signal/ensemble.py

Verifies the EnsembleAggregator's weighted voting, staleness eviction,
accuracy-based weight adjustment, and consensus threshold behaviour.
"""

import sys
import os
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/signal"))
from ensemble import EnsembleAggregator  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig(model_id: str, signal: str, confidence: float = 0.8) -> dict:
    return {
        "model_id": model_id,
        "model_name": model_id,
        "symbol": "SPY",
        "signal": signal,
        "confidence": confidence,
        "price": 500.0,
        "timestamp": int(time.time() * 1000),
        "explanation": [],
        "forecast_price": 501.0,
        "forecast_timestamp": int(time.time() * 1000) + 60_000,
        "schema_version": "1.0",
    }


# ---------------------------------------------------------------------------
# Minimum model quorum
# ---------------------------------------------------------------------------

class TestQuorum:
    def test_returns_none_with_only_one_model(self):
        agg = EnsembleAggregator(min_models=2)
        result = agg.add_signal(_sig("model_a", "BUY"))
        assert result is None

    def test_returns_signal_once_quorum_reached(self):
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.5)
        agg.add_signal(_sig("model_a", "BUY", 0.9))
        result = agg.add_signal(_sig("model_b", "BUY", 0.9))
        assert result is not None

    def test_quorum_of_three_requires_three_models(self):
        agg = EnsembleAggregator(min_models=3, consensus_threshold=0.5)
        agg.add_signal(_sig("model_a", "BUY"))
        agg.add_signal(_sig("model_b", "BUY"))
        result = agg.add_signal(_sig("model_b", "BUY"))  # same model, no new vote
        assert result is None


# ---------------------------------------------------------------------------
# Consensus threshold
# ---------------------------------------------------------------------------

class TestConsensus:
    def test_mixed_signals_below_threshold_returns_none(self):
        # BUY and SELL equal weight → neither reaches 60%
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.6)
        agg.add_signal(_sig("model_a", "BUY", 0.8))
        result = agg.add_signal(_sig("model_b", "SELL", 0.8))
        assert result is None

    def test_majority_buy_triggers_buy_ensemble(self):
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.55)
        agg.add_signal(_sig("model_a", "BUY", 0.9))
        result = agg.add_signal(_sig("model_b", "BUY", 0.7))
        assert result is not None
        assert result["signal"] == "BUY"

    def test_ensemble_signal_has_correct_metadata(self):
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.5)
        agg.add_signal(_sig("model_a", "SELL", 0.9))
        result = agg.add_signal(_sig("model_b", "SELL", 0.9))
        assert result is not None
        assert result["model_id"] == "ensemble"
        assert result["model_name"] == "Ensemble"
        assert result["signal"] == "SELL"
        assert 0.0 < result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Accuracy-based weighting
# ---------------------------------------------------------------------------

class TestWeighting:
    def test_higher_accuracy_model_gets_more_weight(self):
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.0)
        # model_a: 100% accurate → weight ≈ 1.0
        for _ in range(10):
            agg.record_outcome("model_a", correct=True)
        # model_b: 0% accurate → weight = 0.1 (floor)
        for _ in range(10):
            agg.record_outcome("model_b", correct=False)

        weights = agg.model_weights()
        # model_a must be in pending to appear — add signals first
        agg.add_signal(_sig("model_a", "BUY"))
        agg.add_signal(_sig("model_b", "SELL"))
        weights = agg.model_weights()
        assert weights["model_a"] > weights["model_b"]

    def test_unknown_model_gets_default_weight_of_one(self):
        agg = EnsembleAggregator(min_models=1, consensus_threshold=0.0)
        agg.add_signal(_sig("new_model", "BUY"))
        weights = agg.model_weights()
        assert weights.get("new_model") == 1.0

    def test_fewer_than_five_outcomes_uses_default_weight(self):
        agg = EnsembleAggregator(min_models=1, consensus_threshold=0.0)
        agg.add_signal(_sig("model_x", "BUY"))
        for _ in range(4):
            agg.record_outcome("model_x", correct=False)
        # Still < 5 outcomes → default weight
        assert agg._get_weight("model_x") == 1.0


# ---------------------------------------------------------------------------
# Staleness eviction
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_stale_signals_evicted_before_vote(self):
        # TTL of 1ms — signals from the first model will be stale by the time
        # the second model's signal arrives (we sleep long enough to ensure it)
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.5, signal_ttl_ms=1)
        agg.add_signal(_sig("model_a", "BUY"))
        time.sleep(0.01)  # 10ms > 1ms TTL
        result = agg.add_signal(_sig("model_b", "BUY"))
        # model_a's signal was evicted → quorum not met
        assert result is None

    def test_fresh_signals_not_evicted(self):
        agg = EnsembleAggregator(min_models=2, consensus_threshold=0.5, signal_ttl_ms=5_000)
        agg.add_signal(_sig("model_a", "BUY", 0.9))
        result = agg.add_signal(_sig("model_b", "BUY", 0.9))
        assert result is not None
