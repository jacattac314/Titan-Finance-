"""
EnsembleAggregator — performance-weighted multi-model signal fusion.

Each strategy produces independent signals.  This aggregator:
  1. Buffers the most recent signal from every model (evicting stale ones).
  2. Weights each model's vote by its rolling accuracy (tracked via
     execution_filled feedback piped back from the risk/execution layer).
  3. Emits a combined signal when the weighted consensus reaches the
     configured threshold and at least ``min_models`` have voted.

The aggregator does NOT replace individual model signals; the caller
publishes both the individual signals and the ensemble signal so the
dashboard can display all of them.
"""

import logging
import statistics
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger("TitanEnsemble")

# Default TTL: signals older than this are ignored in the vote
_SIGNAL_TTL_MS = 30_000  # 30 seconds


class EnsembleAggregator:
    """Performance-weighted voting ensemble for trade signals."""

    def __init__(
        self,
        min_models: int = 2,
        consensus_threshold: float = 0.60,
        signal_ttl_ms: int = _SIGNAL_TTL_MS,
        accuracy_window: int = 50,
    ):
        self.min_models = min_models
        self.consensus_threshold = consensus_threshold
        self.signal_ttl_ms = signal_ttl_ms
        self.accuracy_window = accuracy_window

        # model_id -> (signal_dict, received_at_ms)
        self._pending: Dict[str, Tuple[dict, int]] = {}
        # model_id -> rolling window of 1.0 (correct) / 0.0 (wrong)
        self._accuracy: Dict[str, Deque[float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_signal(self, signal: dict) -> Optional[dict]:
        """
        Register a new signal from a strategy.

        Returns an ensemble signal dict if consensus is reached, else None.
        The returned dict has model_id="ensemble" and model_name="Ensemble".
        """
        model_id = signal.get("model_id", "unknown")
        now_ms = int(time.time() * 1000)

        self._pending[model_id] = (signal, now_ms)
        self._evict_stale(now_ms)

        if len(self._pending) < self.min_models:
            return None

        votes: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0}
        total_weight = 0.0

        for mid, (sig, _) in self._pending.items():
            direction = sig.get("signal")
            if direction not in votes:
                continue
            w = self._get_weight(mid)
            votes[direction] += w * float(sig.get("confidence", 0.5))
            total_weight += w

        if total_weight == 0:
            return None

        best = max(votes, key=lambda k: votes[k])
        ratio = votes[best] / total_weight

        if ratio < self.consensus_threshold:
            return None

        explanation = [
            f"{mid}: {s['signal']} conf={s.get('confidence', 0):.2f} w={self._get_weight(mid):.2f}"
            for mid, (s, _) in self._pending.items()
        ]

        logger.info(
            "Ensemble consensus=%s ratio=%.2f models=%d | %s",
            best, ratio, len(self._pending),
            ", ".join(explanation),
        )

        return {
            **signal,
            "model_id": "ensemble",
            "model_name": "Ensemble",
            "signal": best,
            "confidence": round(ratio, 3),
            "explanation": explanation,
        }

    def record_outcome(self, model_id: str, correct: bool) -> None:
        """
        Feed back whether a model's last signal was directionally correct.
        Called when execution_filled events arrive.
        """
        if model_id not in self._accuracy:
            self._accuracy[model_id] = deque(maxlen=self.accuracy_window)
        self._accuracy[model_id].append(1.0 if correct else 0.0)

    def model_weights(self) -> Dict[str, float]:
        """Return current weight for each model (useful for logging/dashboard)."""
        return {mid: self._get_weight(mid) for mid in self._pending}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evict_stale(self, now_ms: int) -> None:
        self._pending = {
            mid: (sig, ts)
            for mid, (sig, ts) in self._pending.items()
            if now_ms - ts <= self.signal_ttl_ms
        }

    def _get_weight(self, model_id: str) -> float:
        """
        Return the model's accuracy-based weight.
        Defaults to 1.0 (equal weight) until at least 5 outcomes are recorded.
        Floor of 0.1 prevents a bad model from being completely ignored.
        """
        acc = self._accuracy.get(model_id)
        if not acc or len(acc) < 5:
            return 1.0
        return max(0.1, statistics.mean(acc))
