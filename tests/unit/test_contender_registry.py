"""
Unit tests for contender_registry.py

Verifies that load_contenders():
- Returns a list of strategy instances from a valid YAML file.
- Skips disabled entries.
- Skips entries with unknown class names (and logs an error).
- Returns [] for a missing file.
- Returns [] for a malformed YAML file.
- Respects the CONTENDERS_CONFIG environment variable.
"""
import os
import textwrap
import pathlib
import sys
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(tmp_path: pathlib.Path, content: str) -> str:
    p = tmp_path / "contenders.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadContenders:
    def test_loads_sma_contender(self, tmp_path):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: SMACrossover
                symbol: SPY
                model_id: sma_test
                enabled: true
                fast_period: 5
                slow_period: 10
        """)
        result = load_contenders(config_path=cfg)
        assert len(result) == 1
        from strategies.sma_crossover import SMACrossover
        assert isinstance(result[0], SMACrossover)
        assert result[0].model_id == "sma_test"
        assert result[0].symbol == "SPY"

    def test_disabled_entries_are_skipped(self, tmp_path):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: SMACrossover
                symbol: SPY
                model_id: sma_active
                enabled: true
                fast_period: 5
                slow_period: 10
              - class: SMACrossover
                symbol: SPY
                model_id: sma_disabled
                enabled: false
                fast_period: 5
                slow_period: 10
        """)
        result = load_contenders(config_path=cfg)
        assert len(result) == 1
        assert result[0].model_id == "sma_active"

    def test_unknown_class_is_skipped(self, tmp_path):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: NoSuchStrategy
                symbol: SPY
                model_id: bad_one
                enabled: true
        """)
        result = load_contenders(config_path=cfg)
        assert result == []

    def test_missing_file_returns_empty_list(self, tmp_path):
        from contender_registry import load_contenders

        result = load_contenders(config_path=str(tmp_path / "does_not_exist.yaml"))
        assert result == []

    def test_malformed_yaml_returns_empty_list(self, tmp_path):
        from contender_registry import load_contenders

        p = tmp_path / "bad.yaml"
        p.write_text("contenders: [this: is: not: valid")
        result = load_contenders(config_path=str(p))
        assert result == []

    def test_enabled_defaults_to_true_when_absent(self, tmp_path):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: SMACrossover
                symbol: SPY
                model_id: sma_no_enabled_key
                fast_period: 5
                slow_period: 10
        """)
        result = load_contenders(config_path=cfg)
        assert len(result) == 1

    def test_contenders_config_env_var(self, tmp_path, monkeypatch):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: SMACrossover
                symbol: SPY
                model_id: sma_from_env
                enabled: true
                fast_period: 5
                slow_period: 10
        """)
        monkeypatch.setenv("CONTENDERS_CONFIG", cfg)
        result = load_contenders()  # no explicit path — reads from env
        assert len(result) == 1
        assert result[0].model_id == "sma_from_env"

    def test_multiple_same_class_contenders(self, tmp_path):
        from contender_registry import load_contenders

        cfg = _write_yaml(tmp_path, """
            contenders:
              - class: SMACrossover
                symbol: SPY
                model_id: sma_fast
                enabled: true
                fast_period: 5
                slow_period: 10
              - class: SMACrossover
                symbol: QQQ
                model_id: sma_slow
                enabled: true
                fast_period: 20
                slow_period: 50
        """)
        result = load_contenders(config_path=cfg)
        assert len(result) == 2
        symbols = {s.symbol for s in result}
        assert symbols == {"SPY", "QQQ"}
