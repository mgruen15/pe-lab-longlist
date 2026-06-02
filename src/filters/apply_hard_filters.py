"""
Apply hard filters to the merged longlist.
Each company gets PASS / MARGIN_FLAG / FAIL per dimension and an overall status.

Input:  output/merged_longlist.csv
Output: output/hard_filtered_longlist.csv
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import load_config

INPUT_PATH  = ROOT / "output/merged_longlist.csv"
OUTPUT_PATH = ROOT / "output/hard_filtered_longlist.csv"
FILTER_CFG  = ROOT / "config/hard_filters.yaml"

PASS   = "PASS"
MARGIN = "MARGIN_FLAG"
FAIL   = "FAIL"


def _filter_region(region_bucket: str, cfg: dict) -> str:
    if region_bucket in cfg["target"]:
        return PASS
    if region_bucket in cfg["adjacent"]:
        return MARGIN
    return FAIL


def _filter_numeric(value, lo: float, hi: float, margin_pct: float) -> str:
    if pd.isna(value):
        return MARGIN   # insufficient data → flag rather than kill
    v = float(value)
    lo_margin = lo * (1 - margin_pct)
    hi_margin = hi * (1 + margin_pct)
    if lo <= v <= hi:
        return PASS
    if lo_margin <= v < lo or hi < v <= hi_margin:
        return MARGIN
    return FAIL


def _filter_business_model(tags_raw, cfg: dict) -> str:
    if not tags_raw or (isinstance(tags_raw, float) and pd.isna(tags_raw)):
        return MARGIN   # no data → flag
    tags = [t.strip().lower() for t in str(tags_raw).split(",")]
    if any(t in cfg["pass_tags"] for t in tags):
        return PASS
    if any(t in cfg["margin_tags"] for t in tags):
        return MARGIN
    return FAIL


def _overall_status(binding_results: list[str], soft_results: list[str]) -> str:
    """
    binding_results: region, revenue, ebitda — a FAIL here excludes the company.
    soft_results: business_model — MARGIN here is noted but doesn't block PASS
                  when all binding dimensions pass.
    """
    if FAIL in binding_results:
        return "hard_filter_fail"
    if MARGIN in binding_results:
        return "hard_filter_margin"
    # All binding dims pass; soft MARGIN is noted as margin, not a hard block
    if MARGIN in soft_results:
        return "hard_filter_margin"
    return "hard_filter_pass"


def apply_hard_filters(input_path=INPUT_PATH, output_path=OUTPUT_PATH) -> pd.DataFrame:
    cfg = load_config(FILTER_CFG)
    df  = pd.read_csv(input_path)

    region_cfg  = cfg["region"]
    rev_cfg     = cfg["revenue_eur"]
    ebitda_cfg  = cfg["ebitda_eur"]
    bm_cfg      = cfg["business_model"]

    filter_cols = []
    for _, row in df.iterrows():
        r_region = _filter_region(row.get("region_bucket", ""), region_cfg)
        r_rev    = _filter_numeric(
            row.get("revenue_eur_latest"),
            rev_cfg["min"], rev_cfg["max"], rev_cfg["margin_pct"],
        )
        r_ebitda = _filter_numeric(
            row.get("ebitda_eur_latest"),
            ebitda_cfg["min"], ebitda_cfg["max"], ebitda_cfg["margin_pct"],
        )
        r_bm     = _filter_business_model(row.get("business_model_tags"), bm_cfg)

        overall  = _overall_status(
            binding_results=[r_region, r_rev, r_ebitda],
            soft_results=[r_bm],
        )
        filter_cols.append({
            "hf_region":         r_region,
            "hf_revenue":        r_rev,
            "hf_ebitda":         r_ebitda,
            "hf_business_model": r_bm,
            "hard_filter_status": overall,
        })

    hf_df = pd.DataFrame(filter_cols)
    result = pd.concat([df.reset_index(drop=True), hf_df], axis=1)
    result["stage_status"] = result["hard_filter_status"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    counts = result["hard_filter_status"].value_counts()
    print("Hard-filter results:")
    for status, n in counts.items():
        print(f"  {status}: {n}")
    print(f"Wrote → {output_path}")
    return result


if __name__ == "__main__":
    apply_hard_filters()
