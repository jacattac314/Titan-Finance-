"""
Unit tests for services/signal/models/tft_model.py

TFTModel is a Transformer-based time-series forecaster.
Tests verify output shape, horizon length, finiteness, and determinism.
"""
import pytest
import torch
from models.tft_model import TFTModel, PositionalEncoding


# ---------------------------------------------------------------------------
# PositionalEncoding
# ---------------------------------------------------------------------------

class TestPositionalEncoding:
    def test_output_shape_unchanged(self):
        pe = PositionalEncoding(d_model=64)
        x = torch.randn(30, 2, 64)   # [seq_len, batch, d_model]
        out = pe(x)
        assert out.shape == x.shape

    def test_pe_is_finite(self):
        pe = PositionalEncoding(d_model=32)
        x = torch.randn(10, 1, 32)
        assert torch.isfinite(pe(x)).all()


# ---------------------------------------------------------------------------
# TFTModel — shape contracts
# ---------------------------------------------------------------------------

class TestTFTModelShape:
    def make_model(self, output_horizon=5) -> TFTModel:
        return TFTModel(input_size=14, d_model=64, nhead=4,
                        num_layers=2, output_horizon=output_horizon)

    def test_output_shape_single_sample(self):
        model = self.make_model()
        x = torch.randn(1, 60, 14)
        out = model(x)
        assert out.shape == (1, 5)  # [batch, output_horizon]

    def test_output_shape_batch(self):
        model = self.make_model()
        x = torch.randn(4, 60, 14)
        out = model(x)
        assert out.shape == (4, 5)

    def test_custom_output_horizon(self):
        model = self.make_model(output_horizon=10)
        x = torch.randn(2, 30, 14)
        out = model(x)
        assert out.shape == (2, 10)

    def test_custom_input_size(self):
        model = TFTModel(input_size=8, d_model=32, nhead=4, num_layers=1, output_horizon=3)
        x = torch.randn(1, 20, 8)
        out = model(x)
        assert out.shape == (1, 3)

    def test_short_sequence(self):
        model = self.make_model()
        x = torch.randn(1, 5, 14)
        out = model(x)
        assert out.shape == (1, 5)


# ---------------------------------------------------------------------------
# TFTModel — value contracts
# ---------------------------------------------------------------------------

class TestTFTModelValues:
    def make_model(self) -> TFTModel:
        return TFTModel(input_size=14, d_model=64, nhead=4, num_layers=2, output_horizon=5)

    def test_output_is_finite(self):
        model = self.make_model()
        x = torch.randn(4, 60, 14)
        out = model(x)
        assert torch.isfinite(out).all()

    def test_eval_mode_is_deterministic(self):
        model = self.make_model()
        model.eval()
        x = torch.randn(1, 60, 14)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)

    def test_zero_input_produces_finite_output(self):
        model = self.make_model()
        x = torch.zeros(1, 60, 14)
        out = model(x)
        assert torch.isfinite(out).all()
