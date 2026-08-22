import os
import logging
from typing import Dict, Any, List, Optional
import requests
import contextvars
from google.cloud import discoveryengine
from google.adk.tools import ToolContext
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger("ASKHR")

def get_email_from_oauth_token(token: str) -> str:
    """
    Discover user identity by resolving the token using Google's tokeninfo endpoint.
    Avoids automatic credential refresh errors from google-auth.
    """
    try:
        print("Resolving token via Google tokeninfo endpoint...")
        url = f"https://oauth2.googleapis.com/tokeninfo?access_token={token}"
        response = requests.get(url, timeout=10)
        print("DEBUG Response", response.text)
        if response.status_code == 200:
            data = response.json()
            email = data.get("email")
            if email:
                print(f"Successfully resolved email from tokeninfo: {email}")
                return email
        else:
            print(f"tokeninfo returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Failed to resolve token via tokeninfo: {e}")
    
    return "admin_null@prothiag.altostrat.com"

