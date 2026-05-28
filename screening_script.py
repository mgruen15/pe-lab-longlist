import os
import json
import time
import pandas as pd
from tqdm import tqdm
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE_EXCEL = "Longlist_Data.xlsx"
INPUT_FILE_CSV = "Longlist_Data.xlsx - Ergebnisse.csv"
OUTPUT_FILE = "Longlist_Enriched_AI_Screening.csv"
PROMPT_TEMPLATE_FILE = "prompt_template.md"

# OpenAI / OpenRouter Configuration
MODEL = "openrouter/owl-alpha" # openrouter/owl-alpha
API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Retry logic configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds

# Column names from the source
COL_NAME = "Unternehmensname Latin alphabet"
COL_COUNTRY = "ISO Ländercode"
COL_NACE = "NACE Rev. 2 Core Code (4 Ziffern)"

def load_prompt_template():
    """Load the prompt template from the external markdown file."""
    if not os.path.exists(PROMPT_TEMPLATE_FILE):
        raise FileNotFoundError(f"Prompt template file not found: {PROMPT_TEMPLATE_FILE}")
    with open(PROMPT_TEMPLATE_FILE, 'r') as f:
        return f.read()

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

def screen_company(client, company_name, country, nace_code, template):
    """Call OpenRouter API to evaluate a single company."""
    prompt = template.format(
        company_name=company_name,
        country=country,
        nace_code=nace_code
    )

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional investment screener. Respond ONLY with a JSON object."},
                    {"role": "user", "content": prompt}
                ]
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
        # 1. Load the original source data
        df = load_data()
        # 2. Load the prompt template
        template = load_prompt_template()
    except Exception as e:
        print(f"FATAL: {e}")
        return

    # Check for required columns
    required_cols = [COL_NAME, COL_COUNTRY, COL_NACE]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(f"FATAL: Missing columns in dataset: {missing_cols}")
        print(f"Available columns: {df.columns.tolist()}")
        return

    # 2. Initialize results columns
    if 'AI_FDE_Match' not in df.columns:
        df['AI_FDE_Match'] = None
    if 'Screening_Reasoning' not in df.columns:
        df['Screening_Reasoning'] = ""

    # 3. Load existing progress and merge it into the dataframe to allow for resuming
    if os.path.exists(OUTPUT_FILE):
        print(f"Found existing progress in {OUTPUT_FILE}. Merging results...")
        try:
            existing_df = pd.read_csv(OUTPUT_FILE)
            processed = existing_df.dropna(subset=['AI_FDE_Match'])
            lookup = processed.set_index([COL_NAME, COL_NACE])[['AI_FDE_Match', 'Screening_Reasoning']].to_dict('index')
            
            for index, row in df.iterrows():
                key = (row[COL_NAME], row[COL_NACE])
                if key in lookup:
                    if pd.isnull(df.at[index, 'AI_FDE_Match']):
                        df.at[index, 'AI_FDE_Match'] = lookup[key]['AI_FDE_Match']
                        df.at[index, 'Screening_Reasoning'] = lookup[key]['Screening_Reasoning']
        except Exception as e:
            print(f"Warning: Could not merge existing progress: {e}")

    if not API_KEY:
        print("FATAL: OPENROUTER_API_KEY not found in environment.")
        return

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )

    total_rows = len(df)
    already_done = df['AI_FDE_Match'].notnull().sum()
    
    print(f"Starting screening for {total_rows} companies (Already processed: {already_done})...")

    # 4. Process each company
    for index, row in tqdm(df.iterrows(), total=total_rows, desc="Screening Companies"):
        # SKIP if already done
        if pd.notnull(df.at[index, 'AI_FDE_Match']):
            continue

        name = row[COL_NAME]
        country = row[COL_COUNTRY]
        nace = row[COL_NACE]

        result = screen_company(client, name, country, nace, template)
        
        df.at[index, 'AI_FDE_Match'] = result.get('keep_sample')
        df.at[index, 'Screening_Reasoning'] = result.get('reasoning')

        # SAVE AFTER EVERY SUCCESSFUL CALL
        df.to_csv(OUTPUT_FILE, index=False)

    # 5. Final Summary
    matches_found = (df['AI_FDE_Match'] == True).sum()
    total_processed = df['AI_FDE_Match'].notnull().sum()
    
    print("\n" + "="*30)
    print("SCREENING COMPLETE")
    print("="*30)
    print(f"Total processed:  {total_processed}")
    print(f"Matches found:    {matches_found}")
    print(f"Results saved to: {OUTPUT_FILE}")
    print("="*30)

if __name__ == "__main__":
    main()
