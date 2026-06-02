"""
Load and normalise the Orbis export into the canonical schema.

Input:  data/raw/orbis/Longlist_Data.xlsx  (sheet: Ergebnisse)
Output: data/interim/orbis_normalized.csv
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
    ownership_from_quoted,
    parse_revenue_to_eur,
    safe_int,
)

INPUT_PATH  = ROOT / "data/raw/orbis/Longlist_Data.xlsx"
OUTPUT_PATH = ROOT / "data/interim/orbis_normalized.csv"
MAPPING_CFG = ROOT / "config/field_mappings.yaml"
SHEET_NAME  = "Ergebnisse"


def load_orbis(input_path=INPUT_PATH, output_path=OUTPUT_PATH) -> pd.DataFrame:
    cfg = load_config(MAPPING_CFG)
    m   = cfg["orbis"]
    rb  = cfg["region_buckets"]

    # python-calamine is faster and handles Orbis exports better than openpyxl
    try:
        df_raw = pd.read_excel(input_path, sheet_name=SHEET_NAME, engine="calamine")
    except Exception:
        df_raw = pd.read_excel(input_path, sheet_name=SHEET_NAME)

    print(f"Loaded {len(df_raw)} rows from Orbis export.")

    # Drop completely empty rows
    df_raw = df_raw.dropna(how="all")

    records = []
    for _, row in df_raw.iterrows():
        raw_name    = row.get(m["company_name"], "")
        raw_country = row.get(m["country"], "")
        raw_rev     = row.get(m["revenue_eur_latest"])
        raw_ebitda  = row.get(m["ebitda_eur_latest"])
        raw_year    = row.get(m["revenue_year"])
        raw_emp     = row.get(m["employees"])
        raw_nace    = row.get(m["industry_code"])
        raw_quoted  = row.get(m["ownership_status"], "")
        raw_inactive = row.get(m["inactive"], "")

        country = str(raw_country).strip().upper() if isinstance(raw_country, str) else ""

        records.append({
            "company_name":       str(raw_name).strip() if isinstance(raw_name, str) else "",
            "_name_key":          normalize_name(str(raw_name)),
            "country":            country,
            "region_bucket":      map_region(country, rb),
            "revenue_eur_latest": parse_revenue_to_eur(raw_rev, m["revenue_unit"]),
            "ebitda_eur_latest":  parse_revenue_to_eur(raw_ebitda, m["ebitda_unit"]),
            "revenue_year":       safe_int(raw_year),
            "employees":          str(raw_emp).strip() if pd.notna(raw_emp) else None,
            "industry_code":      str(int(raw_nace)) if pd.notna(raw_nace) else None,
            "ownership_status":   ownership_from_quoted(raw_quoted),
            "inactive":           str(raw_inactive).strip().lower() in ("ja", "yes"),
            "business_model_tags": None,
            "source":             "Orbis",
            "stage_status":       "raw",
        })

    df = pd.DataFrame(records)
    df = df[df["company_name"] != ""]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows → {output_path}")
    return df


if __name__ == "__main__":
    load_orbis()
