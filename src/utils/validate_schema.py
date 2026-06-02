"""Schema validation helpers. Raises on critical errors, warns on soft issues."""

import sys

import pandas as pd

REQUIRED_CANONICAL = [
    "merged_id",
    "company_name",
    "country",
    "region_bucket",
    "revenue_eur_latest",
    "ebitda_eur_latest",
    "source",
    "stage_status",
]


def validate_merged(df: pd.DataFrame, context: str = "") -> None:
    prefix = f"[{context}] " if context else ""
    errors = []
    warnings = []

    missing_cols = [c for c in REQUIRED_CANONICAL if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")

    if "merged_id" in df.columns and df["merged_id"].duplicated().any():
        n = df["merged_id"].duplicated().sum()
        errors.append(f"{n} duplicate merged_id values")

    if "revenue_eur_latest" in df.columns:
        neg = (df["revenue_eur_latest"].dropna() < 0).sum()
        if neg:
            warnings.append(f"{neg} rows have negative revenue")

    if "ebitda_eur_latest" in df.columns:
        extreme = (df["ebitda_eur_latest"].dropna().abs() > 1e9).sum()
        if extreme:
            warnings.append(f"{extreme} rows have |EBITDA| > €1B (unit error?)")

    for w in warnings:
        print(f"{prefix}WARNING: {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"{prefix}ERROR: {e}", file=sys.stderr)
        raise ValueError(f"{prefix}Schema validation failed — see errors above.")


def validate_score_weights(config: dict, stage: str) -> None:
    total = sum(c["weight"] for c in config["criteria"].values())
    if abs(total - 100) > 0.01:
        raise ValueError(f"{stage} scoring weights sum to {total}, must be 100.")
