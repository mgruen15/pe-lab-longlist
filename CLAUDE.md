# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install pandas openpyxl tqdm openai python-calamine python-dotenv google-generativeai pyyaml pytest

# Run full pipeline (in order)
python3 src/ingest/load_orbis.py
python3 src/ingest/load_internal.py
python3 src/merge/merge_longlist.py
python3 src/filters/apply_hard_filters.py
python3 src/scoring/score_stage1.py
python3 src/scoring/score_stage2.py      # calls Gemini API
python3 src/outputs/generate_shortlist.py

# Run tests
python3 -m pytest tests/ -v
```

## Architecture

Two-stage, configuration-driven screening pipeline:

### Stage flow
1. **Ingest** — `src/ingest/load_orbis.py` reads `data/raw/orbis/Longlist_Data.xlsx` (sheet: `Ergebnisse`) using `python-calamine`, normalises to canonical schema, writes `data/interim/orbis_normalized.csv`. `load_internal.py` does the same for `data/raw/internal_research/Combined_Longlist.xlsx`.
2. **Merge** — `src/merge/merge_longlist.py` combines both sources with exact + fuzzy dedup (threshold 0.88), preserves source traceability (`Orbis` / `Both` / internal label), writes `output/merged_longlist.csv`.
3. **Hard filter** — `src/filters/apply_hard_filters.py` applies region / revenue / EBITDA filters from `config/hard_filters.yaml`. Each company gets PASS / MARGIN_FLAG / FAIL per dimension; binding dims are region+revenue+EBITDA; business model is a soft signal. Writes `output/hard_filtered_longlist.csv`.
4. **Stage 1** — `src/scoring/score_stage1.py` runs a weighted quantitative scorecard (config: `config/scoring_stage1.yaml`) over all hard_filter_pass and hard_filter_margin companies. Score ≥ 6.0 → stage1_pass. Writes `output/stage1_scored.csv`.
5. **Stage 2** — `src/scoring/score_stage2.py` calls Gemini with `config/prompt_template.md` per company (same retry/resume logic as original scripts). Merges optional analyst input from `data/interim/stage2_analyst_input.csv`. Writes `output/stage2_scored.csv`.
6. **Output** — `src/outputs/generate_shortlist.py` writes `output/top10_shortlist.csv` and `output/screening_summary.md`.

### Configuration files (change these, not the scripts)
| File | Controls |
|---|---|
| `config/field_mappings.yaml` | Column name aliases and region bucket definitions |
| `config/hard_filters.yaml` | Region/revenue/EBITDA thresholds and margin bands |
| `config/scoring_stage1.yaml` | Quantitative criterion weights, bins, missing-data rules |
| `config/scoring_stage2.yaml` | Qualitative criterion weights, LLM model, pass threshold |
| `config/prompt_template.md` | LLM evaluation prompt — single source of truth for thesis logic |

### Key design rules
- **Configuration-driven:** thresholds, weights, and model names live in YAML, not scripts.
- **Source traceability:** every company carries `source` (Orbis / Both / Internal label) and `duplicate_match_type` (Exact / Fuzzy / None).
- **Stage traceability:** `stage_status` tracks every company's pipeline position.
- **Crash-safe:** Stage 2 resumes from the last completed company; Stage 1 and filters are fully idempotent.
- **Deterministic:** no random state; rerunning on the same inputs produces identical outputs.

### Output columns added by pipeline
- `merged_id` — stable 12-char hash ID per company
- `hf_region`, `hf_revenue`, `hf_ebitda`, `hf_business_model` — per-dimension filter results
- `hard_filter_status` — overall filter outcome
- `stage1_score`, `s1_*` — Stage 1 criterion scores
- `ai_fde_match`, `screening_reasoning` — Stage 2 LLM output
- `stage2_score`, `s2_*` — Stage 2 criterion scores
- `stage_status` — lifecycle position
