"""
Unit tests for services/signal/explainability.py

XAIEngine wraps SHAP DeepExplainer for per-prediction feature attribution.
Because DeepExplainer requires a trained model + background data, tests
focus on the deterministic logic paths:
  - get_top_features ranking by absolute SHAP magnitude
  - guard rails (None / empty shap_values)
  - explain_prediction short-circuits when explainer is absent
"""
import numpy as np
import pytest
from explainability import XAIEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FEATURE_NAMES = ["rsi", "macd", "atr", "bb_upper", "sma"]


def make_engine_no_explainer() -> XAIEngine:
    """Build an XAIEngine with explainer=None (SHAP unavailable / not init'd)."""
    engine = XAIEngine.__new__(XAIEngine)
    engine.model = None
    engine.explainer = None
    return engine


def shap_values_1d(values: list) -> list:
    """Wrap a flat list as shap_values[class_idx] with shape (1, 1, N)."""
    return [np.array([[values]])]


# ---------------------------------------------------------------------------
# explain_prediction — no explainer guard
# ---------------------------------------------------------------------------

class TestExplainPrediction:
    def test_returns_none_when_no_explainer(self):
        engine = make_engine_no_explainer()
        import torch
        result = engine.explain_prediction(torch.randn(1, 10, 5))
        assert result is None


# ---------------------------------------------------------------------------
# get_top_features — guard rails
# ---------------------------------------------------------------------------

class TestGetTopFeaturesGuards:
    def test_returns_empty_list_for_none_shap_values(self):
        engine = make_engine_no_explainer()
        assert engine.get_top_features(None, FEATURE_NAMES) == []

    def test_returns_empty_list_for_empty_shap_values(self):
        engine = make_engine_no_explainer()
        assert engine.get_top_features([], FEATURE_NAMES) == []


# ---------------------------------------------------------------------------
# get_top_features — ranking logic
# ---------------------------------------------------------------------------

class TestGetTopFeaturesRanking:
    def test_returns_requested_number_of_features(self):
        engine = make_engine_no_explainer()
        sv = shap_values_1d([0.1, 0.5, 0.3, 0.05, 0.2])
        result = engine.get_top_features(sv, FEATURE_NAMES, top_k=3)
        assert len(result) == 3

    def test_highest_absolute_value_ranked_first(self):
        engine = make_engine_no_explainer()
        # macd (index 1) has the highest absolute value (-0.9)
        sv = shap_values_1d([0.1, -0.9, 0.3, 0.05, 0.2])
        result = engine.get_top_features(sv, FEATURE_NAMES, top_k=1)
        assert result[0]["feature"] == "macd"

    def test_negative_impact_still_ranks_high(self):
        engine = make_engine_no_explainer()
        # atr (index 2) magnitude 0.8 > rsi (index 0) magnitude 0.1
        sv = shap_values_1d([0.1, 0.0, -0.8, 0.0, 0.0])
        result = engine.get_top_features(sv, FEATURE_NAMES, top_k=1)
        assert result[0]["feature"] == "atr"
        assert result[0]["impact"] == pytest.approx(-0.8)

    def test_result_contains_feature_and_impact_keys(self):
        engine = make_engine_no_explainer()
        sv = shap_values_1d([0.1, 0.5, 0.3, 0.05, 0.2])
        result = engine.get_top_features(sv, FEATURE_NAMES, top_k=1)
        assert "feature" in result[0]
        assert "impact" in result[0]

    def test_out_of_bounds_index_uses_feat_label(self):
        engine = make_engine_no_explainer()
        # Provide only 1 feature name but 5 SHAP values
        sv = shap_values_1d([0.1, 0.5, 0.3, 0.8, 0.2])
        result = engine.get_top_features(sv, ["rsi"], top_k=2)
        labels = [r["feature"] for r in result]
        # At least one label must be a fallback "Feat_N" since names run out
        assert any(lbl.startswith("Feat_") for lbl in labels)

    def test_top_k_capped_by_available_features(self):
        engine = make_engine_no_explainer()
        sv = shap_values_1d([0.1, 0.5])
        result = engine.get_top_features(sv, ["a", "b"], top_k=10)
        assert len(result) == 2  # only 2 features exist
