"""Shared field-normalization helpers used across ingestion and merge stages."""

import re
import unicodedata

import pandas as pd
import yaml


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — used for dedup key."""
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def map_region(country: str, region_buckets: dict) -> str:
    """Return region bucket string for an ISO country code."""
    if not isinstance(country, str):
        return "Other"
    country = country.strip().upper()
    for bucket, codes in region_buckets.items():
        if country in codes:
            return bucket
    return "Other"


def parse_revenue_to_eur(value, unit: str) -> float | None:
    """Convert a raw revenue value to EUR based on declared unit."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if unit == "tsd_eur":
        return v * 1_000
    if unit == "mn_eur":
        return v * 1_000_000
    return v   # assume already EUR


def safe_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def ownership_from_quoted(quoted_raw) -> str:
    """Map Orbis 'Quoted' field (Ja/Nein) to canonical ownership_status."""
    if isinstance(quoted_raw, str) and quoted_raw.strip().lower() in ("ja", "yes", "y"):
        return "Public"
    if isinstance(quoted_raw, str) and quoted_raw.strip().lower() in ("nein", "no", "n"):
        return "Private"
    return "Unknown"
