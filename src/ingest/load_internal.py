"""
Load and normalise the internally-researched company list into the canonical schema.

Input:  data/raw/internal_research/Combined_Longlist.xlsx
Output: data/interim/internal_normalized.csv
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import (
    load_config,
    map_region,
    normalize_name,
    parse_revenue_to_eur,
)

INPUT_PATH  = ROOT / "data/raw/internal_research/Combined_Longlist.xlsx"
OUTPUT_PATH = ROOT / "data/interim/internal_normalized.csv"
MAPPING_CFG = ROOT / "config/field_mappings.yaml"
SHEET_NAME  = "Combined Longlist"


def load_internal(input_path=INPUT_PATH, output_path=OUTPUT_PATH) -> pd.DataFrame:
    cfg = load_config(MAPPING_CFG)
    m   = cfg["internal"]
    rb  = cfg["region_buckets"]

    df_raw = pd.read_excel(input_path, sheet_name=SHEET_NAME)
    print(f"Loaded {len(df_raw)} rows from internal research list.")

    records = []
    for _, row in df_raw.iterrows():
        raw_name    = row.get(m["company_name"], "")
        raw_country = row.get(m["country"], "")
        raw_rev     = row.get(m["revenue_eur_latest"])
        raw_ebitda  = row.get(m["ebitda_eur_latest"])
        raw_emp     = row.get(m["employees"])
        raw_nace    = row.get(m["industry_code"])
        raw_match   = row.get(m.get("ai_fde_match", "AI_FDE_Match"))
        raw_desc    = row.get(m.get("description", "Description"))
        raw_src     = row.get(m.get("source", "Source"), "Internal")

        country = ""
        if isinstance(raw_country, str):
            # Internal list may have compound values like "Germany / Denmark"; take first
            country = raw_country.split("/")[0].strip().upper()
            # Map common country names to ISO codes
            name_to_iso = {
                "GERMANY": "DE", "AUSTRIA": "AT", "SWITZERLAND": "CH",
                "BELGIUM": "BE", "NETHERLANDS": "NL", "LUXEMBOURG": "LU",
                "DENMARK": "DK", "FRANCE": "FR", "UNITED KINGDOM": "UK",
                "NORWAY": "NO", "SWEDEN": "SE", "FINLAND": "FI",
                "ITALY": "IT", "SPAIN": "ES", "POLAND": "PL",
                "DACH": "DE", "BENELUX": "BE",
            }
            country = name_to_iso.get(country, country)

        # Revenue and EBITDA stored in €M in the Combined_Longlist
        try:
            rev = float(raw_rev) * 1_000_000 if pd.notna(raw_rev) else None
        except (TypeError, ValueError):
            rev = None
        try:
            ebitda = float(raw_ebitda) * 1_000_000 if pd.notna(raw_ebitda) else None
        except (TypeError, ValueError):
            ebitda = None

        records.append({
            "company_name":       str(raw_name).strip() if isinstance(raw_name, str) else "",
            "_name_key":          normalize_name(str(raw_name)),
            "country":            country,
            "region_bucket":      map_region(country, rb),
            "revenue_eur_latest": rev,
            "ebitda_eur_latest":  ebitda,
            "revenue_year":       None,
            "employees":          str(raw_emp).strip() if pd.notna(raw_emp) else None,
            "industry_code":      str(int(float(raw_nace))) if pd.notna(raw_nace) else None,
            "ownership_status":   "Unknown",
            "inactive":           False,
            "business_model_tags": None,
            "ai_fde_match_prior": str(raw_match) if pd.notna(raw_match) else None,
            "description":        str(raw_desc).strip() if isinstance(raw_desc, str) else None,
            "source":             "Internal" if str(raw_src) == "nan" else str(raw_src),
            "stage_status":       "raw",
        })

    df = pd.DataFrame(records)
    df = df[df["company_name"] != ""]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows → {output_path}")
    return df


if __name__ == "__main__":
    load_internal()
