from typing import Dict, Any, List, Optional
import requests
import contextvars
from google.cloud import discoveryengine
from google.adk.tools import ToolContext
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
from dotenv import load_dotenv

load_dotenv()
# --- Configuration ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "bold-kit-384717")
LOCATION = os.getenv("VERTEX_SEARCH_LOCATION", "global")
SEARCH_APP_ID = os.getenv("VERTEX_SEARCH_APP_ID", "askhr_1774746828030")
EMPLOYEE_API_URL = os.getenv("EMPLOYEE_API_URL", "http://localhost:8080")

def get_email_from_oauth_token(token:str) -> str:
    """
    Discover user identity by resolving the token and extracting the email.
    Aligns with tools.py robustness patterns.
    """
    
    # 1. Robust token extraction (Context -> Environment Fallback)
    credentials = Credentials(token=token)
    service = build("oauth2","v2",credentials=credentials)
    userinfo = service.userinfo().get().execute()
    user_email = userinfo.get("email") 
    if user_email: # if null then return "[EMAIL_ADDRESS]"  
        return user_email
    else:
        return "admin_null@prothiag.altostrat.com"

token = os.getenv("GCP_ACCESS_TOKEN", "")
if token:
    get_email_from_oauth_token(token)
