"""
Merge Orbis and internal research datasets into a single deduplicated longlist.

Input:  data/interim/orbis_normalized.csv
        data/interim/internal_normalized.csv
Output: output/merged_longlist.csv
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.validate_schema import validate_merged

ORBIS_PATH    = ROOT / "data/interim/orbis_normalized.csv"
INTERNAL_PATH = ROOT / "data/interim/internal_normalized.csv"
OUTPUT_PATH   = ROOT / "output/merged_longlist.csv"

FUZZY_THRESHOLD = 0.88   # SequenceMatcher ratio above which names are treated as the same


def _make_id(name: str, country: str) -> str:
    key = f"{name}|{country}".encode()
    return hashlib.md5(key).hexdigest()[:12]


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def merge_longlists(
    orbis_path=ORBIS_PATH,
    internal_path=INTERNAL_PATH,
    output_path=OUTPUT_PATH,
) -> pd.DataFrame:

    df_o = pd.read_csv(orbis_path)
    df_i = pd.read_csv(internal_path)

    df_o["_src_label"] = "Orbis"
    df_i["_src_label"] = "Internal"

    combined = pd.concat([df_o, df_i], ignore_index=True)
    combined["_name_key"] = combined["_name_key"].fillna("")
    combined["country"]   = combined["country"].fillna("").str.strip().str.upper()

    # ── Pass 1: exact dedup on (name_key, country) ───────────────────────────
    exact_key = combined["_name_key"] + "|" + combined["country"]
    dupe_mask = exact_key.duplicated(keep=False)

    exact_dupes = combined[dupe_mask].copy()
    unique_rows = combined[~dupe_mask].copy()

    merged_exact = []
    for key, grp in exact_dupes.groupby(exact_key[dupe_mask]):
        base = grp.iloc[0].to_dict()
        sources = grp["_src_label"].tolist()
        base["source"] = "Both" if len(set(sources)) > 1 else sources[0]
        base["duplicate_match_type"] = "Exact"
        # Prefer Orbis financial data; fill from Internal if missing
        if len(grp) > 1:
            other = grp.iloc[1]
            for field in ["revenue_eur_latest", "ebitda_eur_latest", "employees", "industry_code"]:
                if pd.isna(base.get(field)) and pd.notna(other.get(field)):
                    base[field] = other[field]
            # Flag discrepancy if revenue differs by >20%
            rev_a = grp.iloc[0].get("revenue_eur_latest")
            rev_b = grp.iloc[1].get("revenue_eur_latest")
            try:
                if pd.notna(rev_a) and pd.notna(rev_b) and abs(rev_a - rev_b) / max(rev_a, rev_b) > 0.20:
                    base["data_discrepancy_flag"] = "YES"
                    base["data_discrepancy_note"] = (
                        f"Revenue discrepancy: Orbis={rev_a:,.0f} vs Internal={rev_b:,.0f}"
                    )
            except Exception:
                pass
        merged_exact.append(base)

    df_exact = pd.DataFrame(merged_exact) if merged_exact else pd.DataFrame()

    # ── Pass 2: fuzzy dedup on remaining unique rows ──────────────────────────
    unique_rows = unique_rows.reset_index(drop=True)
    fuzzy_groups: dict[int, int] = {}   # index → canonical index

    keys = unique_rows["_name_key"].tolist()
    countries = unique_rows["country"].tolist()

    for i in range(len(keys)):
        if i in fuzzy_groups:
            continue
        for j in range(i + 1, len(keys)):
            if j in fuzzy_groups:
                continue
            if countries[i] != countries[j]:
                continue
            if _fuzzy_ratio(keys[i], keys[j]) >= FUZZY_THRESHOLD:
                fuzzy_groups[j] = i

    fuzzy_dupes_idx = set(fuzzy_groups.keys())
    truly_unique = unique_rows[~unique_rows.index.isin(fuzzy_dupes_idx)].copy()
    truly_unique["duplicate_match_type"] = "None"

    fuzzy_merged = []
    for child_idx, parent_idx in fuzzy_groups.items():
        base = unique_rows.iloc[parent_idx].to_dict()
        other = unique_rows.iloc[child_idx]
        sources = [base.get("_src_label", ""), other["_src_label"]]
        base["source"] = "Both" if len(set(sources)) > 1 else sources[0]
        base["duplicate_match_type"] = "Fuzzy"
        base["data_discrepancy_note"] = (
            f"Fuzzy match: '{keys[parent_idx]}' ~ '{keys[child_idx]}'"
        )
        for field in ["revenue_eur_latest", "ebitda_eur_latest", "employees"]:
            if pd.isna(base.get(field)) and pd.notna(other.get(field)):
                base[field] = other[field]
        fuzzy_merged.append(base)

    df_fuzzy = pd.DataFrame(fuzzy_merged) if fuzzy_merged else pd.DataFrame()

    # ── Combine and assign IDs ────────────────────────────────────────────────
    all_parts = [p for p in [df_exact, df_fuzzy, truly_unique] if len(p)]
    result = pd.concat(all_parts, ignore_index=True)

    raw_ids = result.apply(
        lambda r: _make_id(r.get("_name_key", ""), r.get("country", "")), axis=1
    )
    # Resolve hash collisions by appending a counter suffix
    seen: dict[str, int] = {}
    final_ids = []
    for mid in raw_ids:
        if mid not in seen:
            seen[mid] = 0
            final_ids.append(mid)
        else:
            seen[mid] += 1
            final_ids.append(f"{mid}_{seen[mid]}")
    result["merged_id"] = final_ids

    # Fill default values
    result["data_discrepancy_flag"] = result.get("data_discrepancy_flag", pd.Series("NO")).fillna("NO")
    result["data_discrepancy_note"] = result.get("data_discrepancy_note", pd.Series("")).fillna("")
    result["stage_status"] = "merged"

    # Safety net: if two rows survived with identical (name_key, country) keep the first
    # (Orbis-sourced rows sort first because _src_label == "Orbis" < "Internal")
    result = result.sort_values("_src_label", na_position="last")
    result = result.drop_duplicates(subset=["_name_key", "country"], keep="first")

    # Drop internal bookkeeping column
    result = result.drop(columns=["_src_label"], errors="ignore")

    # Reorder columns
    lead_cols = [
        "merged_id", "company_name", "country", "region_bucket",
        "revenue_eur_latest", "ebitda_eur_latest", "revenue_year",
        "employees", "industry_code", "ownership_status", "inactive",
        "business_model_tags", "source", "duplicate_match_type",
        "data_discrepancy_flag", "data_discrepancy_note", "stage_status",
    ]
    extra = [c for c in result.columns if c not in lead_cols and not c.startswith("_")]
    result = result[[c for c in lead_cols if c in result.columns] + extra]

    validate_merged(result, context="merge_longlist")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    orbis_n    = (result["source"] == "Orbis").sum()
    internal_n = (result["source"] == "Internal").sum()
    both_n     = (result["source"] == "Both").sum()
    print(
        f"Merged longlist: {len(result)} companies "
        f"(Orbis={orbis_n}, Internal={internal_n}, Both={both_n})"
    )
    print(f"Wrote → {output_path}")
    return result


if __name__ == "__main__":
    merge_longlists()
