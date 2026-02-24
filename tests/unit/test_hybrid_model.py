"""
Unit tests for services/signal/model.py

HybridModel fuses LSTM, CNN, and Transformer branches for 3-class
(BUY / HOLD / SELL) classification.  Tests verify shape contracts,
Softmax probability invariants, eval determinism, and the load_model
factory helper.
"""
import pytest
import torch
from model import HybridModel, load_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model(input_dim=14, num_classes=3) -> HybridModel:
    return HybridModel(input_dim=input_dim, hidden_dim=64,
                       num_layers=2, num_classes=num_classes)


# ---------------------------------------------------------------------------
# Shape contracts
# ---------------------------------------------------------------------------

class TestHybridModelShape:
    def test_output_shape_single_sample(self):
        model = make_model()
        x = torch.randn(1, 60, 14)
        out = model(x)
        assert out.shape == (1, 3)

    def test_output_shape_batch(self):
        model = make_model()
        x = torch.randn(8, 60, 14)
        out = model(x)
        assert out.shape == (8, 3)

    def test_custom_num_classes(self):
        model = make_model(num_classes=2)
        x = torch.randn(2, 30, 14)
        out = model(x)
        assert out.shape == (2, 2)

    def test_custom_input_dim(self):
        model = make_model(input_dim=8)
        x = torch.randn(1, 20, 8)
        out = model(x)
        assert out.shape == (1, 3)


# ---------------------------------------------------------------------------
# Value contracts (Softmax invariants)
# ---------------------------------------------------------------------------

class TestHybridModelValues:
    def test_output_is_finite(self):
        model = make_model()
        x = torch.randn(2, 60, 14)
        out = model(x)
        assert torch.isfinite(out).all()

    def test_probabilities_sum_to_one(self):
        model = make_model()
        x = torch.randn(4, 60, 14)
        out = model(x)
        sums = out.sum(dim=1)
        assert torch.allclose(sums, torch.ones(4), atol=1e-5)

    def test_probabilities_non_negative(self):
        model = make_model()
        x = torch.randn(4, 60, 14)
        out = model(x)
        assert (out >= 0).all()

    def test_eval_mode_is_deterministic(self):
        model = make_model()
        model.eval()
        x = torch.randn(1, 60, 14)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)


# ---------------------------------------------------------------------------
# load_model factory
# ---------------------------------------------------------------------------

class TestLoadModel:
    def test_returns_model_instance(self):
        m = load_model(input_dim=8)
        assert isinstance(m, HybridModel)

    def test_model_is_in_eval_mode(self):
        m = load_model(input_dim=8)
        assert not m.training

    def test_forward_pass_after_load(self):
        m = load_model(input_dim=8)
        x = torch.randn(1, 20, 8)
        out = m(x)
        assert out.shape == (1, 3)

    def test_invalid_path_falls_back_to_random_weights(self):
        # Should not raise — just log an error and continue
        m = load_model(path="/nonexistent/weights.pth", input_dim=8)
        assert isinstance(m, HybridModel)
