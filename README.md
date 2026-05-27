# PE AI Screening Automation

This project automates the commercial screening of Private Equity investment targets using OpenRouter's online-enabled LLMs (e.g., Perplexity Sonar). It evaluates companies against the "AI Forward Deployed Engineering (FDE)" investment thesis.

## Features

- **Automated Screening**: Iterates through a list of companies from an Orbis export.
- **Real-time Evaluation**: Uses OpenRouter models with web search capabilities to lookup current company offerings.
- **Thesis-Driven Logic**: Evaluates firms for their ability to deploy custom AI pipelines, RAG systems, and multi-agent workflows.
- **Robust Ingestion**: Handles Excel (`.xlsx`) and CSV files, specifically optimized for Orbis export formats.
- **Structured Results**: Outputs an enriched CSV with boolean matches and detailed reasoning.

## Prerequisites

- Python 3.8+
- OpenRouter API Key

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd pe-lab-longlist
   ```

2. Install dependencies:
   ```bash
   pip install pandas openpyxl tqdm openai python-calamine python-dotenv
   ```

## Configuration

1. Create a `.env` file in the root directory (already included in `.gitignore`):
   ```bash
   OPENROUTER_API_KEY='your_api_key_here'
   ```
2. The script will automatically load this key using `python-dotenv`.

## Usage

1. Place your input data in the root directory as `Longlist_Data.xlsx`.
2. Ensure the Excel file contains a sheet named `Ergebnisse`.
3. Run the screening script:
   ```bash
   python3 screening_script.py
   ```
4. The enriched data will be saved to `Longlist_Enriched_AI_Screening.csv`.

## Investment Thesis: AI Forward Deployed Engineering (FDE)

We look for companies that bridge the gap between AI research and enterprise application.
- **Qualification**: Custom AI pipelines, RAG systems, or high-potential custom software shops.
- **Exclusion**: Hardware distributors, basic staffing, SaaS resellers, or traditional marketing agencies.
