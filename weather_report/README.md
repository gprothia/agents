# Weather Report Agent

An intelligent weather assistant built with the **Google Agent Development Kit (ADK)** and powered by **Gemini 2.5 Flash** on **Google Cloud Vertex AI**.

---

## 🌟 Features

- **Current Weather Conditions**: Real-time temperatures, feels-like temperatures, humidity, wind speed, cloud cover, and precipitation for any city or location globally.
- **Multi-Day Forecast**: Day-by-day weather forecasts (1 to 14 days) with min/max temperatures, precipitation probabilities, UV index, and sunrise/sunset times.
- **Air Quality Index (AQI)**: Current AQI ratings (US & European standards), PM2.5, PM10, ozone, and health recommendations.
- **Multi-City Weather Comparison**: Side-by-side weather comparisons across multiple locations.
- **No External Weather API Keys Needed**: Leverages open meteorological services (Open-Meteo) with automatic geocoding.

---

## 📁 Directory Structure

```
weather_report/
├── .env              # Vertex AI configuration (project bold-kit-384717, region us-central1)
├── __init__.py       # Package definition
├── agent.py          # Root agent and App definition
├── prompts.py        # System instructions and prompt templates
├── tools.py          # Weather, forecast, air quality, and comparison tools
└── README.md         # Documentation
```

---

## 🚀 Quickstart

### 1. Run with ADK CLI

Run a single query:
```bash
adk run ./weather_report "What is the weather in Seattle right now?"
```

Run interactive mode:
```bash
adk run ./weather_report
```

### 2. Run with ADK Web UI

Launch the local web interface:
```bash
adk web
```
Then navigate to the web UI in your browser to chat with the weather agent interactively.

---

## 💡 Example Queries

- *"What is the weather in San Francisco right now?"*
- *"Give me a 5-day forecast for Tokyo, Japan."*
- *"What is the air quality in Paris today?"*
- *"Compare the current weather between New York and London."*
- *"Will it rain in Chicago tomorrow? Should I bring an umbrella?"*
