import os
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.apps import App

from .prompts import WEATHER_AGENT_INSTRUCTION
from .tools import (
    compare_weather,
    get_air_quality,
    get_current_weather,
    get_weather_forecast,
)

# Load environment variables
load_dotenv()

MODEL = os.getenv("MODEL", "gemini-3.5-flash")

root_agent = Agent(
    name="weather_agent",
    description="Agent for querying real-time weather conditions, multi-day forecasts, air quality, and city weather comparisons.",
    instruction=WEATHER_AGENT_INSTRUCTION,
    tools=[
        get_current_weather,
        get_weather_forecast,
        get_air_quality,
        compare_weather,
    ],
    model=MODEL,
)

app = App(name="weather_report", root_agent=root_agent)
