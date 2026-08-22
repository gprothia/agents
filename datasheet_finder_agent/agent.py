"""Main ADK Agent definition for ComponentIQ - Electrical Datasheet Finder."""

import os
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.apps import App

from .prompts import DATASHEET_FINDER_INSTRUCTION
from .tools import (
    download_and_verify_pdf,
    extract_pdf_metadata,
    normalize_part_number,
    search_google_datasheets,
)

load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

root_agent = Agent(
    name="datasheet_finder_agent",
    description="Autonomous agent for resolving imprecise electrical component part numbers, searching Google for official datasheets, and downloading verified PDFs.",
    instruction=DATASHEET_FINDER_INSTRUCTION,
    tools=[
        normalize_part_number,
        search_google_datasheets,
        download_and_verify_pdf,
        extract_pdf_metadata,
    ],
    model=MODEL,
)

app = App(name="datasheet_finder_agent", root_agent=root_agent)
