# ComponentIQ - Electrical Component Datasheet Finder Agent (ADK)

A standalone **Google Agent Development Kit (ADK)** agent that resolves noisy or imprecise electrical part numbers, constructs targeted Google search queries for PDF datasheets, verifies the downloaded file bytes, and extracts component specifications.

## Project Structure

```
datasheet_finder_agent/
├── agent.py         # ADK Root Agent and App definition
├── prompts.py       # Part number resolution & search instructions
├── tools.py         # Google search, OCR cleaner, PDF downloader & inspector
├── runner.py        # CLI test runner
├── deploy.py        # Vertex AI Agent Engine deployment script
├── requirements.txt # Python dependencies
├── .env             # GCP Environment configuration
└── downloads/       # Directory where downloaded PDFs are saved
```

## Quickstart

### 1. Test via CLI

```bash
# Interactive REPL mode
python3 datasheet_finder_agent/runner.py

# Single query mode
python3 datasheet_finder_agent/runner.py "Find datasheet for MAX232|PE"
python3 datasheet_finder_agent/runner.py "Download datasheet for stm32f407"
```

### 2. Deploy to Vertex AI Agent Engine

```bash
python3 datasheet_finder_agent/deploy.py
```
