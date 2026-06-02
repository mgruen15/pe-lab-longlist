"""
Stage 1 – quantitative scoring over hard-filter survivors.

Input:  output/hard_filtered_longlist.csv
Output: output/stage1_scored.csv
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import load_config
from src.utils.validate_schema import validate_score_weights

INPUT_PATH  = ROOT / "output/hard_filtered_longlist.csv"
OUTPUT_PATH = ROOT / "output/stage1_scored.csv"
SCORE_CFG   = ROOT / "config/scoring_stage1.yaml"

ELIGIBLE_STATUSES = {"hard_filter_pass", "hard_filter_margin"}


def _bin_score(value, bins: list) -> int:
    """Return score for the first bin whose upper bound is >= value."""
    if pd.isna(value):
        return None
    v = float(value)
    for upper, score in bins:
        if v < upper:
            return score
    return bins[-1][1]


def _score_criterion(name: str, crit: dict, row: pd.Series) -> tuple[float | None, str]:
    """Return (raw_score 0-10, note)."""

    missing_rule = crit.get("missing_data_rule", "score_0")
    default_missing = int(missing_rule.split("_")[1]) if missing_rule.startswith("score_") else 0

    if name == "revenue_size":
        v = row.get("revenue_eur_latest")
        score = _bin_score(v, crit["bins"]) if pd.notna(v) else None

    elif name == "ebitda_margin":
        rev   = row.get("revenue_eur_latest")
        ebit  = row.get("ebitda_eur_latest")
        if pd.notna(rev) and pd.notna(ebit) and float(rev) > 0:
            margin = float(ebit) / float(rev)
            score  = _bin_score(margin, crit["bins"])
        else:
            score = None

    elif name == "region_fit":
        bucket = row.get("region_bucket", "Other")
        score  = crit["mapping"].get(bucket, 0) if isinstance(bucket, str) else None

    elif name == "nace_alignment":
        code = row.get("industry_code")
        if pd.notna(code):
            score = crit["mapping"].get(int(float(code)), crit.get("default_score", 2))
        else:
            score = None

    elif name == "revenue_per_employee":
        rev = row.get("revenue_eur_latest")
        emp_raw = row.get("employees")
        try:
            emp = float(emp_raw)
            if emp > 0 and pd.notna(rev):
                score = _bin_score(float(rev) / emp, crit["bins"])
            else:
                score = None
        except (TypeError, ValueError):
            score = None

    elif name == "company_size_employees":
        try:
            emp = float(row.get("employees"))
            score = _bin_score(emp, crit["bins"])
        except (TypeError, ValueError):
            score = None

    else:
        score = None

    if score is None:
        score = default_missing
        note = f"missing data ({missing_rule})"
    else:
        note = ""

    return float(score), note


def score_stage1(input_path=INPUT_PATH, output_path=OUTPUT_PATH) -> pd.DataFrame:
    cfg = load_config(SCORE_CFG)
    validate_score_weights(cfg, "Stage1")

    df   = pd.read_csv(input_path)
    pool = df[df["stage_status"].isin(ELIGIBLE_STATUSES)].copy()
    excluded = df[~df["stage_status"].isin(ELIGIBLE_STATUSES)].copy()

    criteria = cfg["criteria"]
    pass_threshold = float(cfg["pass_threshold"])

    score_records = []
    for _, row in pool.iterrows():
        weighted_total = 0.0
        rec = {}
        for crit_name, crit_cfg in criteria.items():
            score, note = _score_criterion(crit_name, crit_cfg, row)
            weight = crit_cfg["weight"]
            weighted_total += score * weight / 100
            rec[f"s1_{crit_name}"] = round(score, 2)
            if note:
                rec[f"s1_{crit_name}_note"] = note
        rec["stage1_score"] = round(weighted_total, 3)
        rec["stage_status"] = "stage1_pass" if weighted_total >= pass_threshold else "stage1_fail"
        score_records.append(rec)

    scores_df = pd.DataFrame(score_records)
    # Drop any columns in pool that will be re-added from scores_df to avoid duplicates
    overlap = [c for c in scores_df.columns if c in pool.columns]
    pool = pool.drop(columns=overlap, errors="ignore")
    pool = pd.concat([pool.reset_index(drop=True), scores_df.reset_index(drop=True)], axis=1)

    # Reattach excluded rows (they keep their existing stage_status)
    result = pd.concat([pool, excluded], ignore_index=True)
    result = result.sort_values("stage1_score", ascending=False, na_position="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    passed = (pool["stage_status"] == "stage1_pass").sum()
    failed = (pool["stage_status"] == "stage1_fail").sum()
    print(f"Stage 1 scored {len(pool)} companies: {passed} pass, {failed} fail (threshold={pass_threshold})")
    print(f"Wrote → {output_path}")
    return result


if __name__ == "__main__":
    score_stage1()
