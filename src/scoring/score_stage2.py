"""
Stage 2 – qualitative scoring.
Runs LLM-based AI FDE thesis screening (adapted from the original Gemini script)
and merges analyst input fields.

Input:  output/stage1_scored.csv
        (optional) data/interim/stage2_analyst_input.csv  — manual scoring fields
Output: output/stage2_scored.csv
"""

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils.normalize_fields import load_config
from src.utils.validate_schema import validate_score_weights

INPUT_PATH        = ROOT / "output/stage1_scored.csv"
OUTPUT_PATH       = ROOT / "output/stage2_scored.csv"
ANALYST_INPUT     = ROOT / "data/interim/stage2_analyst_input.csv"
SCORE_CFG         = ROOT / "config/scoring_stage2.yaml"

ELIGIBLE_STATUSES = {"stage1_pass"}

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _load_prompt_template(cfg: dict) -> str:
    template_path = ROOT / cfg["llm_screening"]["prompt_template"]
    return template_path.read_text()


def _call_gemini(prompt: str, model: str, max_retries: int, backoff: float) -> dict | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        gen_model = genai.GenerativeModel(model)
    except Exception as e:
        print(f"  Gemini init error: {e}", file=sys.stderr)
        return None

    for attempt in range(max_retries):
        try:
            response = gen_model.generate_content(prompt)
            text = response.text.strip()
            # Extract JSON from response
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")
            return json.loads(text[start:end])
        except Exception as e:
            wait = backoff * (2 ** attempt)
            print(f"  Attempt {attempt+1} failed: {e}. Retrying in {wait:.0f}s…", file=sys.stderr)
            time.sleep(wait)
    return None


def _llm_score_from_match(ai_fde_match) -> float:
    """Convert boolean/string LLM output to a numeric score."""
    if isinstance(ai_fde_match, bool):
        return 10.0 if ai_fde_match else 0.0
    if isinstance(ai_fde_match, str):
        if ai_fde_match.lower() in ("true", "yes", "1"):
            return 10.0
        if ai_fde_match.lower() in ("false", "no", "0"):
            return 0.0
    return 5.0   # unknown → mid-score


def _weighted_stage2_score(row: pd.Series, cfg: dict) -> float:
    criteria = cfg["criteria"]
    total = 0.0
    for crit_name, crit_cfg in criteria.items():
        weight = crit_cfg["weight"]
        missing_default = 0.0
        field = f"s2_{crit_name}"
        if crit_cfg["source"] == "llm":
            score = row.get("s2_ai_fde_thesis_fit", missing_default) or missing_default
        else:
            score = row.get(field, missing_default)
            if pd.isna(score):
                missing_rule = crit_cfg.get("missing_data_rule", "score_0")
                score = float(missing_rule.split("_")[1]) if missing_rule.startswith("score_") else 0.0
        total += float(score) * weight / 100
    return round(total, 3)


def score_stage2(input_path=INPUT_PATH, output_path=OUTPUT_PATH) -> pd.DataFrame:
    cfg = load_config(SCORE_CFG)
    validate_score_weights(cfg, "Stage2")

    df   = pd.read_csv(input_path)
    pool = df[df["stage_status"].isin(ELIGIBLE_STATUSES)].copy()
    excluded = df[~df["stage_status"].isin(ELIGIBLE_STATUSES)].copy()

    llm_cfg      = cfg["llm_screening"]
    template     = _load_prompt_template(cfg)
    sleep_secs   = llm_cfg.get("sleep_between_calls_seconds", 5)
    pass_threshold = float(cfg["pass_threshold"])

    # Resume: skip already-screened rows
    if output_path.exists():
        prior = pd.read_csv(output_path)
        prior_ids = set(prior["merged_id"].dropna()) if "merged_id" in prior.columns else set()
        already_done = pool[pool["merged_id"].isin(prior_ids)]
        pool = pool[~pool["merged_id"].isin(prior_ids)]
        print(f"Resuming: {len(already_done)} already screened, {len(pool)} remaining.")
    else:
        prior = pd.DataFrame()

    # Merge analyst input if available
    analyst_cols: list[str] = []
    if ANALYST_INPUT.exists():
        analyst_df = pd.read_csv(ANALYST_INPUT)
        pool = pool.merge(analyst_df, on="merged_id", how="left", suffixes=("", "_analyst"))
        analyst_cols = [c for c in analyst_df.columns if c != "merged_id"]

    col_match     = llm_cfg["output_field"]
    col_reasoning = llm_cfg["reasoning_field"]

    results = []
    for i, (_, row) in enumerate(pool.iterrows(), 1):
        name    = row.get("company_name", "")
        country = row.get("country", "")
        nace    = row.get("industry_code", "")

        prompt = template.format(
            company_name=name,
            country=country,
            nace_code=nace,
        )

        print(f"[{i}/{len(pool)}] Screening: {name}")
        llm_result = _call_gemini(prompt, llm_cfg["model"], llm_cfg["max_retries"], llm_cfg["backoff_base_seconds"])

        if llm_result:
            match     = llm_result.get("keep_sample")
            reasoning = llm_result.get("reasoning", "")
        else:
            match     = None
            reasoning = "LLM call failed"

        llm_score = _llm_score_from_match(match)

        row_out = row.to_dict()
        row_out[col_match]              = match
        row_out[col_reasoning]          = reasoning
        row_out["s2_ai_fde_thesis_fit"] = llm_score

        s2_total = _weighted_stage2_score(pd.Series(row_out), cfg)
        row_out["stage2_score"] = s2_total
        row_out["stage_status"] = "stage2_scored"

        results.append(row_out)

        # Save after every call
        batch = pd.DataFrame(results)
        combined = pd.concat([prior, batch, excluded], ignore_index=True) if len(prior) else pd.concat([batch, excluded], ignore_index=True)
        combined.to_csv(output_path, index=False)

        time.sleep(sleep_secs)

    # Final pass: mark stage2_pass / stage2_fail
    final = pd.read_csv(output_path)
    scored_mask = final["stage_status"] == "stage2_scored"
    final.loc[scored_mask & (final["stage2_score"] >= pass_threshold), "stage_status"] = "stage2_pass"
    final.loc[scored_mask & (final["stage2_score"] < pass_threshold),  "stage_status"] = "stage2_fail"
    final.to_csv(output_path, index=False)

    passed = (final["stage_status"] == "stage2_pass").sum()
    print(f"Stage 2 complete. {passed} companies advanced (threshold={pass_threshold}).")
    print(f"Wrote → {output_path}")
    return final


if __name__ == "__main__":
    score_stage2()
