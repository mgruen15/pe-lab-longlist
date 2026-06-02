# PE Lab — AI Forward Deployed Engineering Screening

A reproducible, configuration-driven pipeline for screening private equity targets against the **AI Forward Deployed Engineering (FDE)** investment thesis. The pipeline merges two input sources, applies hard filters, runs a two-stage scorecard, and produces a ranked top-10 shortlist.

---

## Screening funnel

```
Orbis export  +  Internal research
        ↓
    Merge & dedup (merge_longlist.py)
        ↓
  Hard filter — PASS / MARGIN_FLAG / FAIL  (apply_hard_filters.py)
        ↓
  Stage 1 — Quantitative scorecard  (score_stage1.py)
        ↓
  Stage 2 — Qualitative + LLM screening  (score_stage2.py)
        ↓
     Top-10 shortlist  (generate_shortlist.py)
```

---

## Repository structure

```
├── config/
│   ├── field_mappings.yaml       # Canonical field names, column mappings, region buckets
│   ├── hard_filters.yaml         # Region / revenue / EBITDA thresholds + margin bands
│   ├── scoring_stage1.yaml       # Quantitative scorecard weights and bins
│   ├── scoring_stage2.yaml       # Qualitative scorecard + LLM config
│   └── prompt_template.md        # LLM prompt for AI FDE thesis evaluation
├── data/
│   ├── raw/
│   │   ├── orbis/                # Orbis export(s)  — Longlist_Data.xlsx
│   │   └── internal_research/    # Internal lists   — Combined_Longlist.xlsx
│   ├── interim/                  # Normalised intermediates (generated)
│   └── processed/                # Prior screened results for reference
├── src/
│   ├── ingest/
│   │   ├── load_orbis.py         # Normalise Orbis export → canonical schema
│   │   └── load_internal.py      # Normalise internal list → canonical schema
│   ├── merge/
│   │   └── merge_longlist.py     # Exact + fuzzy dedup; source tracing
│   ├── filters/
│   │   └── apply_hard_filters.py # PASS / MARGIN_FLAG / FAIL per dimension
│   ├── scoring/
│   │   ├── score_stage1.py       # Weighted quantitative scorecard
│   │   └── score_stage2.py       # LLM + analyst qualitative scorecard
│   ├── outputs/
│   │   └── generate_shortlist.py # Top-10 CSV + screening_summary.md
│   └── utils/
│       ├── normalize_fields.py   # Shared normalization helpers
│       └── validate_schema.py    # Schema and weight validation
├── notebooks/                    # Exploratory analysis
├── tests/                        # Unit tests
└── output/                       # All generated outputs
```

---

## Required input files

| File | Location | Description |
|---|---|---|
| `Longlist_Data.xlsx` | `data/raw/orbis/` | Orbis export, sheet `Ergebnisse` |
| `Combined_Longlist.xlsx` | `data/raw/internal_research/` | Internally researched companies |

Place new Orbis exports in `data/raw/orbis/` before running.

---

## Configuration

### Hard filters — `config/hard_filters.yaml`

Controls which companies pass, receive a margin flag, or are excluded:

- **Region:** DACH, Benelux, Denmark (Adjacent countries → MARGIN_FLAG)
- **Revenue:** €5M – €100M (±10% margin band)
- **EBITDA:** €1M – €15M (±20% margin band)
- **Business model:** project fees, retainers, SaaS (soft signal; missing data → MARGIN_FLAG)

### Stage 1 scoring — `config/scoring_stage1.yaml`

Six quantitative criteria, each with a weight (total = 100) and score bins (0–10):
revenue size, EBITDA margin, region fit, NACE alignment, revenue per employee, FTE count.
Companies with `stage1_score ≥ 6.0` advance to Stage 2.

### Stage 2 scoring — `config/scoring_stage2.yaml`

Seven qualitative criteria (total weight = 100). LLM-assisted AI FDE thesis fit is scored
automatically; remaining criteria (value creation, management team, exit optionality, etc.)
can be supplied via `data/interim/stage2_analyst_input.csv`.

---

## Running the pipeline

### Install dependencies

```bash
pip install pandas openpyxl tqdm openai python-calamine python-dotenv google-generativeai pyyaml
```

### Environment variables

Create a `.env` file in the repo root:

```
GEMINI_API_KEY=your_key_here
```

### Run full pipeline

```bash
python3 src/ingest/load_orbis.py
python3 src/ingest/load_internal.py
python3 src/merge/merge_longlist.py
python3 src/filters/apply_hard_filters.py
python3 src/scoring/score_stage1.py
python3 src/scoring/score_stage2.py       # calls Gemini API — incurs cost
python3 src/outputs/generate_shortlist.py
```

Stage 2 is crash-safe: rerunning resumes from the last completed company.

### Run tests

```bash
python3 -m pytest tests/ -v
```

---

## Output files

| File | Description |
|---|---|
| `output/merged_longlist.csv` | Full merged dataset before filtering |
| `output/hard_filtered_longlist.csv` | Pass / margin / fail results per dimension |
| `output/stage1_scored.csv` | Quantitative scores per company |
| `output/stage2_scored.csv` | LLM + qualitative scores per company |
| `output/top10_shortlist.csv` | Final ranked shortlist |
| `output/screening_summary.md` | Funnel counts and top-10 table |

---

## Stage status lifecycle

| Status | Meaning |
|---|---|
| `raw` | Imported, not yet normalised |
| `merged` | Deduplicated into master longlist |
| `hard_filter_pass` | Passed all hard criteria |
| `hard_filter_margin` | Borderline fit — retained for scoring |
| `hard_filter_fail` | Excluded at hard-filter stage |
| `stage1_pass` | Advanced after quantitative scoring |
| `stage1_fail` | Dropped after quantitative scoring |
| `stage2_pass` | Advanced after qualitative screening |
| `stage2_fail` | Dropped after qualitative screening |
| `top10` | Final shortlist |

---

## Known data limitations

- **Orbis coverage:** Private company coverage is uneven. Smaller companies and recent incorporations may be absent or have incomplete financials. Revenue and EBITDA figures often lag by one to two years.
- **Business model tags:** Not available from Orbis exports. All companies default to `hf_business_model = MARGIN_FLAG`. Populate `business_model_tags` manually in the internal research list for binding business model filters.
- **EBITDA missing values:** Approximately 5–15% of private companies in Orbis do not report EBITDA. Missing values receive a margin flag rather than a hard fail.
- **Stage 2 analyst fields:** Optional. Companies without analyst input receive conservative missing-data scores and may rank lower than their true quality warrants.
- **LLM screening accuracy:** The Gemini screening in Stage 2 is a first-pass signal, not a definitive judgment. Always verify LLM reasoning against primary sources before investment decisions.
