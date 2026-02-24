"""
Unit tests for services/signal/models/lstm_model.py

Verifies the architectural contracts of LSTMModel + AttentionBlock:
  - Output shape is always [batch, 1]
  - Output values are always in [0, 1] (Sigmoid activated)
  - eval() mode is deterministic
  - AttentionBlock reduces [batch, seq, hidden] → [batch, hidden]
"""
import pytest
import torch
from models.lstm_model import LSTMModel, AttentionBlock


# ---------------------------------------------------------------------------
# AttentionBlock
# ---------------------------------------------------------------------------

class TestAttentionBlock:
    def test_output_shape_reduces_seq_dim(self):
        attn = AttentionBlock(hidden_size=64)
        x = torch.randn(2, 30, 64)   # [batch, seq_len, hidden]
        out = attn(x)
        assert out.shape == (2, 64)  # seq_len collapsed

    def test_single_sample_output_shape(self):
        attn = AttentionBlock(hidden_size=32)
        x = torch.randn(1, 10, 32)
        out = attn(x)
        assert out.shape == (1, 32)

    def test_output_is_finite(self):
        attn = AttentionBlock(hidden_size=16)
        x = torch.randn(4, 20, 16)
        out = attn(x)
        assert torch.isfinite(out).all()


# ---------------------------------------------------------------------------
# LSTMModel — shape contracts
# ---------------------------------------------------------------------------

class TestLSTMModelShape:
    def make_model(self, input_size=14) -> LSTMModel:
        return LSTMModel(input_size=input_size, hidden_size=64, num_layers=2)

    def test_output_shape_single_sample(self):
        model = self.make_model()
        x = torch.randn(1, 60, 14)
        out = model(x)
        assert out.shape == (1, 1)

    def test_output_shape_batch_of_8(self):
        model = self.make_model()
        x = torch.randn(8, 60, 14)
        out = model(x)
        assert out.shape == (8, 1)

    def test_short_sequence_works(self):
        model = self.make_model()
        x = torch.randn(1, 5, 14)
        out = model(x)
        assert out.shape == (1, 1)

    def test_custom_input_size(self):
        model = LSTMModel(input_size=8, hidden_size=32, num_layers=1)
        x = torch.randn(2, 20, 8)
        out = model(x)
        assert out.shape == (2, 1)


# ---------------------------------------------------------------------------
# LSTMModel — value contracts
# ---------------------------------------------------------------------------

class TestLSTMModelValues:
    def make_model(self) -> LSTMModel:
        return LSTMModel(input_size=14, hidden_size=64, num_layers=2)

    def test_output_in_zero_one_range(self):
        model = self.make_model()
        x = torch.randn(4, 60, 14)
        out = model(x)
        assert (out >= 0.0).all(), "Output below 0"
        assert (out <= 1.0).all(), "Output above 1"

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

    def test_extreme_input_stays_in_range(self):
        model = self.make_model()
        x = torch.full((1, 60, 14), fill_value=1e6)
        out = model(x)
        assert (out >= 0.0).all() and (out <= 1.0).all()

    def test_zero_input_produces_valid_output(self):
        model = self.make_model()
        x = torch.zeros(1, 60, 14)
        out = model(x)
        assert 0.0 <= out.item() <= 1.0
