"""
TitanFlow Contender Registry

Loads strategy contenders from a YAML configuration file and instantiates them.

The config file path defaults to ``contenders.yaml`` in the same directory as
this module, but can be overridden via the ``CONTENDERS_CONFIG`` environment
variable (absolute or relative path).

Usage::

    from contender_registry import load_contenders
    strategies = load_contenders()  # returns list[Strategy]
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Dict, List

import yaml

from strategies.base import Strategy

logger = logging.getLogger(__name__)

# Map class name → module path so the loader can import without guessing.
_CLASS_MODULE_MAP: Dict[str, str] = {
    "SMACrossover": "strategies.sma_crossover",
    "LightGBMStrategy": "strategies.lightgbm_strategy",
    "LSTMStrategy": "strategies.lstm_strategy",
    "TFTStrategy": "strategies.tft_strategy",
    "LogisticRegressionStrategy": "strategies.logistic_regression_strategy",
    "RandomForestStrategy": "strategies.random_forest_strategy",
}

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "contenders.yaml")


def _resolve_config_path() -> str:
    env_path = os.getenv("CONTENDERS_CONFIG", "")
    if env_path:
        return env_path if os.path.isabs(env_path) else os.path.join(os.getcwd(), env_path)
    return _DEFAULT_CONFIG


def load_contenders(config_path: str | None = None) -> List[Strategy]:
    """Load and instantiate contender strategies from a YAML config file.

    Parameters
    ----------
    config_path:
        Path to the YAML file.  Defaults to ``contenders.yaml`` next to this
        module, or the ``CONTENDERS_CONFIG`` env var if set.

    Returns
    -------
    list[Strategy]
        Instantiated, enabled strategy objects ready to be passed to the signal
        loop.  Disabled entries (``enabled: false``) are silently skipped.
    """
    path = config_path or _resolve_config_path()

    try:
        with open(path, "r") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("Contenders config not found: %s", path)
        return []
    except yaml.YAMLError as exc:
        logger.error("Failed to parse contenders config %s: %s", path, exc)
        return []

    entries = (raw or {}).get("contenders", [])
    if not isinstance(entries, list):
        logger.error("contenders.yaml must contain a top-level 'contenders' list")
        return []

    strategies: List[Strategy] = []

    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("Skipping malformed contender entry: %r", entry)
            continue

        if not entry.get("enabled", True):
            logger.info("Contender disabled — skipping: %s", entry.get("model_id", "?"))
            continue

        class_name = entry.get("class")
        if not class_name:
            logger.error("Contender entry missing 'class' field: %r", entry)
            continue

        module_path = _CLASS_MODULE_MAP.get(class_name)
        if module_path is None:
            logger.error(
                "Unknown contender class '%s'. "
                "Add it to _CLASS_MODULE_MAP in contender_registry.py.",
                class_name,
            )
            continue

        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            logger.error("Failed to import contender %s from %s: %s", class_name, module_path, exc)
            continue

        # Build config dict: everything except 'class' and 'enabled'
        config: Dict[str, Any] = {
            k: v for k, v in entry.items() if k not in ("class", "enabled")
        }

        try:
            strategy = cls(config)
            strategies.append(strategy)
            logger.info("Loaded contender: %s (model_id=%s)", class_name, config.get("model_id"))
        except Exception as exc:
            logger.error("Failed to instantiate contender %s: %s", class_name, exc)
            continue

    logger.info("Loaded %d contender(s) from %s", len(strategies), path)
    return strategies
