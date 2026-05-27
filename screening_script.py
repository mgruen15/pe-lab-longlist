import os
import json
import time
import pandas as pd
from tqdm import tqdm
from openai import OpenAI
from datetime import datetime

# --- CONFIGURATION ---
INPUT_FILE_EXCEL = "Longlist_Data.xlsx"
INPUT_FILE_CSV = "Longlist_Data.xlsx - Ergebnisse.csv"
OUTPUT_FILE = "Longlist_Enriched_AI_Screening.csv"

# OpenRouter Configuration
# Recommended models for online search:
# "perplexity/sonar-reasoning" or "meta-llama/llama-3.1-sonar-large-128k-online"
MODEL = "perplexity/sonar-reasoning" 
API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Retry logic configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds
SLEEP_INTERVAL = 1.5 # seconds between successful calls

# Column names from the source
COL_NAME = "Unternehmensname Latin alphabet"
COL_COUNTRY = "ISO Ländercode"
COL_NACE = "NACE Rev. 2 Core Code (4 Ziffern)"

def get_client():
    if not API_KEY:
        raise ValueError("OPENROUTER_API_KEY environment variable not set.")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )

def load_data():
    """Load data from CSV or Excel, prioritizing the CSV mentioned in instructions."""
    if os.path.exists(INPUT_FILE_CSV):
        print(f"Loading data from {INPUT_FILE_CSV}...")
        return pd.read_csv(INPUT_FILE_CSV)
    elif os.path.exists(INPUT_FILE_EXCEL):
        print(f"Loading data from {INPUT_FILE_EXCEL}...")
        try:
            # Try calamine first as it is more robust to Orbis styling
            try:
                import python_calamine
                engine = 'calamine'
            except ImportError:
                engine = 'openpyxl'
                
            print(f"Using {engine} engine to read 'Ergebnisse' sheet...")
            return pd.read_excel(INPUT_FILE_EXCEL, engine=engine, sheet_name='Ergebnisse')
        except Exception as e:
            print(f"Error reading Excel: {e}")
            print("Try exporting the 'Ergebnisse' sheet to CSV and name it 'Longlist_Data.xlsx - Ergebnisse.csv'")
            raise
    else:
        raise FileNotFoundError(f"Could not find {INPUT_FILE_CSV} or {INPUT_FILE_EXCEL}")

def extract_json(text):
    """Attempt to extract JSON from a string that might contain markdown or extra text."""
    text = text.strip()
    # Find the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    return json.loads(text)

def screen_company(client, company_name, country, nace_code):
    """Call OpenRouter API to evaluate a single company."""
    prompt = f"""
You are an expert Private Equity Investment Associate specializing in B2B Tech and AI.
Evaluate the following company against our 'AI Forward Deployed Engineering (FDE)' investment thesis.

### Company Information:
- Name: {company_name}
- Country: {country}
- NACE Code: {nace_code}

### Investment Thesis: AI Forward Deployed Engineering (FDE)
We are looking for companies that bridge the gap between AI research and practical enterprise application. 
They design, deploy, and maintain custom AI pipelines, proprietary RAG systems, and multi-agent workflows.

### Qualification Criteria:
1. **Direct Match:** Already provides custom AI deployment, RAG systems, or fine-tuning services.
2. **High Potential:** High-quality custom software development firms, cloud architecture consultancies, or IT service providers (NACE 6201/6202) with strong engineering talent that can pivot to AI scaling.

### Exclusion Criteria:
- Pure hardware distributors.
- Basic IT staffing or recruitment agencies.
- Low-value SaaS reseller shops.
- Traditional web design or marketing agencies.

### Task:
1. Search the web to understand the company's current service offering and technical depth.
2. Determine if the company is a 'Keep' (True) or 'Exclude' (False).
3. Provide a concise 3-4 sentence reasoning.

### Output Format:
Return ONLY a valid JSON object. No other text.
{{
  "keep_sample": boolean,
  "reasoning": "string"
}}
"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional investment screener. Respond ONLY with a JSON object."},
                    {"role": "user", "content": prompt}
                ]
                # Some models on OpenRouter don't support response_format={"type": "json_object"}
                # So we rely on prompting and the extract_json helper.
            )
            
            result_text = response.choices[0].message.content
            return extract_json(result_text)
            
        except Exception as e:
            backoff = INITIAL_BACKOFF * (2 ** attempt)
            print(f"\n[Error] Attempt {attempt + 1} for '{company_name}' failed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            
    return {"keep_sample": None, "reasoning": f"Failed after {MAX_RETRIES} retries due to API/Network errors."}

def main():
    try:
        df = load_data()
    except Exception as e:
        print(f"FATAL: Could not load data. {e}")
        return

    # Check for required columns
    required_cols = [COL_NAME, COL_COUNTRY, COL_NACE]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(f"FATAL: Missing columns in dataset: {missing_cols}")
        print(f"Available columns: {df.columns.tolist()}")
        return

    # Initialize results columns
    df['AI_FDE_Match'] = None
    df['Screening_Reasoning'] = ""

    client = get_client()
    total_rows = len(df)
    matches_found = 0
    errors_count = 0

    print(f"Starting screening for {total_rows} companies using model: {MODEL}...")

    # Process each company
    for index, row in tqdm(df.iterrows(), total=total_rows, desc="Screening Companies"):
        name = row[COL_NAME]
        country = row[COL_COUNTRY]
        nace = row[COL_NACE]

        result = screen_company(client, name, country, nace)
        
        df.at[index, 'AI_FDE_Match'] = result.get('keep_sample')
        df.at[index, 'Screening_Reasoning'] = result.get('reasoning')

        if result.get('keep_sample') is True:
            matches_found += 1
        elif result.get('keep_sample') is None:
            errors_count += 1

        # Rate limiting / Sleep interval
        time.sleep(SLEEP_INTERVAL)

    # Save results
    df.to_csv(OUTPUT_FILE, index=False)
    
    # Summary
    print("\n" + "="*30)
    print("SCREENING COMPLETE")
    print("="*30)
    print(f"Total processed:  {total_rows}")
    print(f"Matches found:    {matches_found}")
    print(f"Total excluded:   {total_rows - matches_found - errors_count}")
    print(f"Errors/Failed:    {errors_count}")
    print(f"Results saved to: {OUTPUT_FILE}")
    print("="*30)

if __name__ == "__main__":
    main()
