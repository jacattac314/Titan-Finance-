"""
Root conftest for the TitanFlow test suite.

Torch-dependent tests (LSTM, TFT, hybrid model, XAI) are excluded when
PyTorch is not installed.  This is the case in CI (torch is too large) and
on most dev machines that haven't installed ML deps.  The tests still run
correctly in environments where torch is available.
"""

collect_ignore_glob: list[str] = []

try:
    import torch  # noqa: F401
except ImportError:
    collect_ignore_glob = [
        "unit/test_hybrid_model.py",
        "unit/test_lstm_model.py",
        "unit/test_lstm_strategy.py",
        "unit/test_tft_model.py",
        "unit/test_tft_strategy.py",
        "unit/test_xai_engine.py",
    ]
