"""Weather and environmental data querying tools for ADK Agent.

Uses Open-Meteo public APIs (no API key required) for real-time weather,
multi-day forecasts, air quality, and location geocoding.
"""

from typing import Any, Dict, List, Optional
import requests

WMO_WEATHER_CODES: Dict[int, str] = {
    0: "Clear sky ☀️",
    1: "Mainly clear 🌤️",
    2: "Partly cloudy ⛅",
    3: "Overcast ☁️",
    45: "Fog 🌫️",
    48: "Depositing rime fog 🌫️",
    51: "Light drizzle 🌦️",
    53: "Moderate drizzle 🌦️",
    55: "Dense drizzle 🌧️",
    56: "Light freezing drizzle 🌧️❄️",
    57: "Dense freezing drizzle 🌧️❄️",
    61: "Slight rain 🌧️",
    63: "Moderate rain 🌧️",
    65: "Heavy rain 🌧️🌧️",
    66: "Light freezing rain 🌧️❄️",
    67: "Heavy freezing rain 🌧️❄️",
    71: "Slight snow fall 🌨️",
    73: "Moderate snow fall 🌨️",
    75: "Heavy snow fall ❄️❄️",
    77: "Snow grains ❄️",
    80: "Slight rain showers 🌦️",
    81: "Moderate rain showers 🌧️",
    82: "Violent rain showers ⛈️",
    85: "Slight snow showers 🌨️",
    86: "Heavy snow showers ❄️❄️",
    95: "Thunderstorm ⛈️",
    96: "Thunderstorm with slight hail ⛈️🌨️",
    99: "Thunderstorm with heavy hail ⛈️❄️",
}


def _resolve_location(location: str) -> Optional[Dict[str, Any]]:
    """Resolve a city or place name into geographic coordinates using Open-Meteo Geocoding API."""
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": location, "count": 1, "language": "en", "format": "json"}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get("results")
        if not results:
            return None
        match = results[0]
        return {
            "name": match.get("name"),
            "latitude": match.get("latitude"),
            "longitude": match.get("longitude"),
            "country": match.get("country"),
            "admin1": match.get("admin1"),
            "timezone": match.get("timezone", "auto"),
            "elevation": match.get("elevation"),
        }
    except Exception as e:
        return None


def _celsius_to_fahrenheit(c: float) -> float:
    return round((c * 9 / 5) + 32, 1)


def _interpret_aqi(aqi: Optional[int]) -> str:
    if aqi is None:
        return "Unknown"
    if aqi <= 50:
        return "Good 🟢 (Air quality is satisfactory and poses little or no risk)"
    if aqi <= 100:
        return "Moderate 🟡 (Acceptable quality; some pollutants may pose minor concern)"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups 🟠 (Members of sensitive groups may experience health effects)"
    if aqi <= 200:
        return "Unhealthy 🔴 (Everyone may begin to experience health effects)"
    if aqi <= 300:
        return "Very Unhealthy 🟣 (Health alert: everyone may experience serious effects)"
    return "Hazardous 🟤 (Emergency health warning)"


def get_current_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
    """Retrieve current weather conditions for a given city or location.

    Args:
        location: City name, place, or region (e.g., 'San Francisco', 'Tokyo', 'London, UK').
        unit: Preferred temperature unit ('celsius' or 'fahrenheit'). Default is 'celsius'.

    Returns:
        A dictionary containing location details, current temperature, condition description,
        humidity, apparent (feels-like) temperature, wind speed, precipitation, and cloud cover.
    """
    geo = _resolve_location(location)
    if not geo:
        return {
            "status": "error",
            "message": f"Could not find coordinates for location '{location}'. Please check spelling or specify country.",
        }

    url = "https://api.open-meteo.com/v1/forecast"
    temp_unit = "fahrenheit" if unit.lower() == "fahrenheit" else "celsius"
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
            "weather_code",
            "cloud_cover",
            "pressure_msl",
            "surface_pressure",
            "wind_speed_10m",
            "wind_direction_10m",
        ],
        "temperature_unit": temp_unit,
        "wind_speed_unit": "kmh",
        "timezone": geo["timezone"],
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        weather_code = current.get("weather_code", 0)
        condition = WMO_WEATHER_CODES.get(weather_code, f"Code {weather_code}")
        temp = current.get("temperature_2m")
        feels_like = current.get("apparent_temperature")

        # Include both unit values for convenience
        if temp_unit == "celsius" and temp is not None:
            temp_c = temp
            temp_f = _celsius_to_fahrenheit(temp)
            feels_c = feels_like
            feels_f = _celsius_to_fahrenheit(feels_like) if feels_like is not None else None
        elif temp is not None:
            temp_f = temp
            temp_c = round((temp - 32) * 5 / 9, 1)
            feels_f = feels_like
            feels_c = round((feels_like - 32) * 5 / 9, 1) if feels_like is not None else None
        else:
            temp_c = temp_f = feels_c = feels_f = None

        return {
            "status": "success",
            "location": {
                "name": geo["name"],
                "region": geo["admin1"],
                "country": geo["country"],
                "latitude": geo["latitude"],
                "longitude": geo["longitude"],
                "timezone": geo["timezone"],
            },
            "current_weather": {
                "condition": condition,
                "weather_code": weather_code,
                "temperature": {
                    "celsius": temp_c,
                    "fahrenheit": temp_f,
                    "primary": f"{temp_c}°C" if temp_unit == "celsius" else f"{temp_f}°F",
                },
                "feels_like": {
                    "celsius": feels_c,
                    "fahrenheit": feels_f,
                    "primary": f"{feels_c}°C" if temp_unit == "celsius" else f"{feels_f}°F",
                },
                "relative_humidity_percent": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "cloud_cover_percent": current.get("cloud_cover"),
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "pressure_hpa": current.get("pressure_msl"),
                "is_day": bool(current.get("is_day", 1)),
                "observation_time": current.get("time"),
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch weather data: {str(e)}"}


def get_weather_forecast(location: str, days: int = 5, unit: str = "celsius") -> Dict[str, Any]:
    """Retrieve multi-day weather forecast for a given location (up to 14 days).

    Args:
        location: City name, place, or region.
        days: Number of forecast days (1 to 14, default is 5).
        unit: Preferred temperature unit ('celsius' or 'fahrenheit'). Default is 'celsius'.

    Returns:
        A dictionary containing daily forecasts with min/max temperatures, precipitation probability,
        weather conditions, UV index, and sunrise/sunset times.
    """
    geo = _resolve_location(location)
    if not geo:
        return {
            "status": "error",
            "message": f"Could not find coordinates for location '{location}'.",
        }

    days = max(1, min(days, 14))
    temp_unit = "fahrenheit" if unit.lower() == "fahrenheit" else "celsius"
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "precipitation_probability_max",
            "uv_index_max",
            "wind_speed_10m_max",
            "sunrise",
            "sunset",
        ],
        "temperature_unit": temp_unit,
        "wind_speed_unit": "kmh",
        "timezone": geo["timezone"],
        "forecast_days": days,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})

        times = daily.get("time", [])
        codes = daily.get("weather_code", [])
        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])
        precip_sum = daily.get("precipitation_sum", [])
        precip_prob = daily.get("precipitation_probability_max", [])
        uv_index = daily.get("uv_index_max", [])
        wind_max = daily.get("wind_speed_10m_max", [])
        sunrises = daily.get("sunrise", [])
        sunsets = daily.get("sunset", [])

        forecast_list = []
        for i in range(len(times)):
            code = codes[i] if i < len(codes) else 0
            condition = WMO_WEATHER_CODES.get(code, f"Code {code}")
            forecast_list.append({
                "date": times[i],
                "condition": condition,
                "temp_max": f"{t_max[i]}°{'F' if temp_unit == 'fahrenheit' else 'C'}" if i < len(t_max) else None,
                "temp_min": f"{t_min[i]}°{'F' if temp_unit == 'fahrenheit' else 'C'}" if i < len(t_min) else None,
                "precipitation_sum_mm": precip_sum[i] if i < len(precip_sum) else 0,
                "precipitation_probability_percent": precip_prob[i] if i < len(precip_prob) else 0,
                "uv_index_max": uv_index[i] if i < len(uv_index) else None,
                "max_wind_speed_kmh": wind_max[i] if i < len(wind_max) else None,
                "sunrise": sunrises[i] if i < len(sunrises) else None,
                "sunset": sunsets[i] if i < len(sunsets) else None,
            })

        return {
            "status": "success",
            "location": {
                "name": geo["name"],
                "region": geo["admin1"],
                "country": geo["country"],
                "timezone": geo["timezone"],
            },
            "forecast_days": len(forecast_list),
            "unit": temp_unit,
            "daily_forecast": forecast_list,
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch forecast: {str(e)}"}


def get_air_quality(location: str) -> Dict[str, Any]:
    """Retrieve current air quality index (AQI) and pollutant levels for a location.

    Args:
        location: City name, place, or region.

    Returns:
        A dictionary containing US AQI, European AQI, PM2.5, PM10, ozone, and health assessment.
    """
    geo = _resolve_location(location)
    if not geo:
        return {
            "status": "error",
            "message": f"Could not find coordinates for location '{location}'.",
        }

    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "current": [
            "us_aqi",
            "european_aqi",
            "pm10",
            "pm2_5",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "ozone",
        ],
        "timezone": geo["timezone"],
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})

        us_aqi = current.get("us_aqi")
        assessment = _interpret_aqi(us_aqi)

        return {
            "status": "success",
            "location": {
                "name": geo["name"],
                "region": geo["admin1"],
                "country": geo["country"],
            },
            "air_quality": {
                "us_aqi": us_aqi,
                "european_aqi": current.get("european_aqi"),
                "assessment": assessment,
                "pollutants": {
                    "pm2_5_ug_m3": current.get("pm2_5"),
                    "pm10_ug_m3": current.get("pm10"),
                    "ozone_ug_m3": current.get("ozone"),
                    "nitrogen_dioxide_ug_m3": current.get("nitrogen_dioxide"),
                    "carbon_monoxide_ug_m3": current.get("carbon_monoxide"),
                    "sulphur_dioxide_ug_m3": current.get("sulphur_dioxide"),
                },
                "time": current.get("time"),
            },
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch air quality data: {str(e)}"}


def compare_weather(locations: List[str], unit: str = "celsius") -> Dict[str, Any]:
    """Compare current weather across multiple cities or locations simultaneously.

    Args:
        locations: List of city or place names (e.g., ['London', 'Paris', 'Tokyo']).
        unit: Preferred temperature unit ('celsius' or 'fahrenheit'). Default is 'celsius'.

    Returns:
        A dictionary containing comparative weather data across all requested locations.
    """
    results = []
    for loc in locations:
        res = get_current_weather(location=loc, unit=unit)
        results.append({"query": loc, "result": res})

    return {
        "status": "success",
        "total_compared": len(results),
        "comparisons": results,
    }
