"""
Generate the final top-10 shortlist and a screening summary report.

Input:  output/stage2_scored.csv
Output: output/top10_shortlist.csv
        output/screening_summary.md
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import load_config

INPUT_PATH   = ROOT / "output/stage2_scored.csv"
SHORTLIST    = ROOT / "output/top10_shortlist.csv"
SUMMARY_PATH = ROOT / "output/screening_summary.md"
SCORE_CFG    = ROOT / "config/scoring_stage2.yaml"


def generate_shortlist(input_path=INPUT_PATH) -> pd.DataFrame:
    cfg = load_config(SCORE_CFG)
    top_n = int(cfg.get("top_n", 10))

    df = pd.read_csv(input_path)

    # Top N from stage2_pass, ranked by stage2_score desc, stage1_score as tiebreaker
    top = (
        df[df["stage_status"] == "stage2_pass"]
        .sort_values(["stage2_score", "stage1_score"], ascending=[False, False])
        .head(top_n)
        .reset_index(drop=True)
    )
    top.index = top.index + 1  # rank 1-based

    display_cols = [
        "company_name", "country", "revenue_eur_latest", "ebitda_eur_latest",
        "employees", "industry_code", "stage1_score", "stage2_score",
        "ai_fde_match", "screening_reasoning", "source",
    ]
    top_display = top[[c for c in display_cols if c in top.columns]]

    SHORTLIST.parent.mkdir(parents=True, exist_ok=True)
    top_display.to_csv(SHORTLIST, index_label="rank")
    print(f"Top {top_n} shortlist → {SHORTLIST}")

    _write_summary(df, top, top_n)
    return top_display


def _write_summary(df: pd.DataFrame, top: pd.DataFrame, top_n: int) -> None:
    status_counts = df["stage_status"].value_counts().to_dict()

    def n(status): return status_counts.get(status, 0)

    total           = len(df)
    merged          = total
    hf_pass         = n("hard_filter_pass")
    hf_margin       = n("hard_filter_margin")
    hf_fail         = n("hard_filter_fail")
    s1_pass         = n("stage1_pass")
    s1_fail         = n("stage1_fail")
    s2_pass         = n("stage2_pass")
    s2_fail         = n("stage2_fail")

    source_counts = df["source"].value_counts().to_dict() if "source" in df.columns else {}

    lines = [
        "# Screening Summary",
        "",
        f"**Pipeline run date:** see file timestamps",
        "",
        "## Funnel",
        "",
        f"| Stage | Count |",
        f"|---|---|",
        f"| Merged longlist | {merged} |",
        f"| Hard filter pass | {hf_pass} |",
        f"| Hard filter margin | {hf_margin} |",
        f"| Hard filter fail | {hf_fail} |",
        f"| Stage 1 pass | {s1_pass} |",
        f"| Stage 1 fail | {s1_fail} |",
        f"| Stage 2 pass | {s2_pass} |",
        f"| Stage 2 fail | {s2_fail} |",
        f"| **Top {top_n} shortlist** | **{len(top)}** |",
        "",
        "## Sources",
        "",
    ]
    for src, cnt in sorted(source_counts.items()):
        lines.append(f"- **{src}:** {cnt} companies")

    lines += [
        "",
        f"## Top {top_n}",
        "",
        "| Rank | Company | Country | Revenue (€M) | Stage1 | Stage2 |",
        "|---|---|---|---|---|---|",
    ]
    for rank, (_, row) in enumerate(top.iterrows(), 1):
        rev = row.get("revenue_eur_latest")
        rev_str = f"{float(rev)/1e6:.1f}" if pd.notna(rev) else "n/a"
        s1 = f"{row.get('stage1_score', ''):.2f}" if pd.notna(row.get("stage1_score")) else "n/a"
        s2 = f"{row.get('stage2_score', ''):.2f}" if pd.notna(row.get("stage2_score")) else "n/a"
        lines.append(
            f"| {rank} | {row.get('company_name','')} | {row.get('country','')} "
            f"| {rev_str} | {s1} | {s2} |"
        )

    lines += [
        "",
        "## Known limitations",
        "",
        "- Orbis coverage of private companies can be incomplete; revenue and EBITDA figures "
        "may lag by one to two years.",
        "- Business model tags are not available from Orbis exports; the `hf_business_model` "
        "dimension defaults to MARGIN_FLAG for all companies without analyst input.",
        "- Stage 2 qualitative analyst fields are optional; companies without them receive "
        "conservative missing-data scores.",
    ]

    SUMMARY_PATH.write_text("\n".join(lines))
    print(f"Screening summary → {SUMMARY_PATH}")


if __name__ == "__main__":
    generate_shortlist()
