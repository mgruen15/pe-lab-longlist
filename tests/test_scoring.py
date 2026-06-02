"""Unit tests for Stage 1 scoring helpers and weight validation."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.scoring.score_stage1 import _bin_score, _score_criterion
from src.utils.validate_schema import validate_score_weights
from src.utils.normalize_fields import load_config

SCORE_CFG_PATH  = ROOT / "config/scoring_stage1.yaml"
SCORE_CFG2_PATH = ROOT / "config/scoring_stage2.yaml"


def test_weights_sum_stage1():
    cfg = load_config(SCORE_CFG_PATH)
    validate_score_weights(cfg, "Stage1")  # raises if not 100


def test_weights_sum_stage2():
    cfg = load_config(SCORE_CFG2_PATH)
    validate_score_weights(cfg, "Stage2")  # raises if not 100


def test_bin_score_basic():
    bins = [[10_000_000, 3], [25_000_000, 6], [50_000_000, 8], [75_000_000, 10]]
    assert _bin_score(5_000_000, bins) == 3
    assert _bin_score(15_000_000, bins) == 6
    assert _bin_score(30_000_000, bins) == 8
    assert _bin_score(60_000_000, bins) == 10


def test_bin_score_missing():
    bins = [[10_000_000, 3]]
    assert _bin_score(None, bins) is None


def test_score_criterion_revenue_size():
    cfg = load_config(SCORE_CFG_PATH)
    row = pd.Series({"revenue_eur_latest": 30_000_000})
    score, _ = _score_criterion("revenue_size", cfg["criteria"]["revenue_size"], row)
    assert 0 <= score <= 10


def test_score_criterion_missing_revenue():
    cfg = load_config(SCORE_CFG_PATH)
    row = pd.Series({"revenue_eur_latest": None})
    score, note = _score_criterion("revenue_size", cfg["criteria"]["revenue_size"], row)
    assert "missing" in note
    assert score == 0


def test_score_criterion_nace_known():
    cfg = load_config(SCORE_CFG_PATH)
    row = pd.Series({"industry_code": "6201"})
    score, _ = _score_criterion("nace_alignment", cfg["criteria"]["nace_alignment"], row)
    assert score == 10


def test_score_criterion_nace_unknown():
    cfg = load_config(SCORE_CFG_PATH)
    row = pd.Series({"industry_code": "9999"})
    score, _ = _score_criterion("nace_alignment", cfg["criteria"]["nace_alignment"], row)
    assert score == cfg["criteria"]["nace_alignment"]["default_score"]
