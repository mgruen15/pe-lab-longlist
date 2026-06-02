"""Unit tests for hard-filter logic."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.filters.apply_hard_filters import (
    FAIL, MARGIN, PASS,
    _filter_business_model,
    _filter_numeric,
    _filter_region,
    _overall_status,
)


def test_region_target():
    cfg = {"target": ["DACH", "Benelux", "Denmark"], "adjacent": ["Adjacent"]}
    assert _filter_region("DACH", cfg) == PASS
    assert _filter_region("Benelux", cfg) == PASS
    assert _filter_region("Denmark", cfg) == PASS


def test_region_adjacent():
    cfg = {"target": ["DACH"], "adjacent": ["Adjacent"]}
    assert _filter_region("Adjacent", cfg) == MARGIN


def test_region_other():
    cfg = {"target": ["DACH"], "adjacent": ["Adjacent"]}
    assert _filter_region("Other", cfg) == FAIL


def test_revenue_pass():
    assert _filter_numeric(30_000_000, 5_000_000, 100_000_000, 0.10) == PASS


def test_revenue_margin_low():
    # Just below min but within 10% margin
    assert _filter_numeric(4_600_000, 5_000_000, 100_000_000, 0.10) == MARGIN


def test_revenue_margin_high():
    # Just above max but within 10% margin
    assert _filter_numeric(105_000_000, 5_000_000, 100_000_000, 0.10) == MARGIN


def test_revenue_fail_low():
    assert _filter_numeric(1_000_000, 5_000_000, 100_000_000, 0.10) == FAIL


def test_revenue_fail_high():
    assert _filter_numeric(200_000_000, 5_000_000, 100_000_000, 0.10) == FAIL


def test_revenue_missing():
    assert _filter_numeric(None, 5_000_000, 100_000_000, 0.10) == MARGIN


def test_business_model_pass():
    cfg = {"pass_tags": ["project_fees", "retainer"], "margin_tags": ["mixed"]}
    assert _filter_business_model("project_fees, consulting", cfg) == PASS


def test_business_model_margin_tag():
    cfg = {"pass_tags": ["project_fees"], "margin_tags": ["mixed"]}
    assert _filter_business_model("mixed", cfg) == MARGIN


def test_business_model_missing():
    cfg = {"pass_tags": ["project_fees"], "margin_tags": ["mixed"]}
    assert _filter_business_model(None, cfg) == MARGIN


def test_business_model_fail():
    cfg = {"pass_tags": ["project_fees"], "margin_tags": ["mixed"]}
    assert _filter_business_model("hardware_distribution", cfg) == FAIL


def test_overall_all_pass():
    assert _overall_status([PASS, PASS, PASS], [PASS]) == "hard_filter_pass"


def test_overall_binding_margin():
    assert _overall_status([PASS, MARGIN, PASS], [PASS]) == "hard_filter_margin"


def test_overall_soft_margin_only():
    # Business model data missing (soft MARGIN) but all binding dims pass → still margin
    assert _overall_status([PASS, PASS, PASS], [MARGIN]) == "hard_filter_margin"


def test_overall_any_fail():
    assert _overall_status([PASS, FAIL, PASS], [MARGIN]) == "hard_filter_fail"
