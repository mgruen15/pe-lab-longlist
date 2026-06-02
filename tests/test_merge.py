"""Unit tests for merge/dedup logic."""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import normalize_name
from src.merge.merge_longlist import _fuzzy_ratio, _make_id


def test_normalize_name_basic():
    assert normalize_name("ACME GmbH") == "acme gmbh"


def test_normalize_name_punctuation():
    assert normalize_name("A.B.C. Consulting, GmbH") == "a b c consulting gmbh"


def test_normalize_name_unicode():
    result = normalize_name("Müller & Co.")
    assert "muller" in result or "mller" in result  # accent stripped


def test_fuzzy_ratio_identical():
    assert _fuzzy_ratio("acme gmbh", "acme gmbh") == 1.0


def test_fuzzy_ratio_similar():
    r = _fuzzy_ratio("acme consulting gmbh", "acme consultng gmbh")
    assert r > 0.88


def test_fuzzy_ratio_different():
    r = _fuzzy_ratio("google inc", "microsoft corp")
    assert r < 0.5


def test_make_id_deterministic():
    assert _make_id("acme gmbh", "DE") == _make_id("acme gmbh", "DE")


def test_make_id_different_country():
    assert _make_id("acme gmbh", "DE") != _make_id("acme gmbh", "AT")
