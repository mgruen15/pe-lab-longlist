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

# ... rest of configuration ...

def load_prompt_template():
    """Load the prompt template from the external markdown file."""
    if not os.path.exists(PROMPT_TEMPLATE_FILE):
        raise FileNotFoundError(f"Prompt template file not found: {PROMPT_TEMPLATE_FILE}")
    with open(PROMPT_TEMPLATE_FILE, 'r') as f:
        return f.read()

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

    # ... rest of setup ...

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

        # ... rest of loop ...

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
