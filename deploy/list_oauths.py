#!/usr/bin/env python3
"""
List all OAuth Auths (authorizations) registered in Gemini Enterprise / Vertex AI Search.
"""

import json
import os
import urllib.request
import urllib.error
from dotenv import load_dotenv
import google.auth
import google.auth.transport.requests

def list_authorizations():
    # Load environment variables from .env file in project root
    load_dotenv()
    
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("Error: GOOGLE_CLOUD_PROJECT environment variable is not set.")
        print("Please set it in your environment or in a .env file.")
        return

    print(f"Fetching OAuth Auths (Authorizations) for project: {project}...")
    
    try:
        credentials, _ = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        access_token = credentials.token
    except Exception as e:
        print(f"Error obtaining Google Cloud credentials: {e}")
        print("Please run 'gcloud auth application-default login' to authenticate.")
        return

    base_url = f"https://global-discoveryengine.googleapis.com/v1alpha/projects/{project}/locations/global"
    list_auth_url = f"{base_url}/authorizations"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project,
    }

    req = urllib.request.Request(list_auth_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            authorizations = data.get("authorizations", [])
            if not authorizations:
                print("No OAuth Auths (authorizations) found.")
                return
            
            print(f"\nFound {len(authorizations)} OAuth Auth(s):")
            print("-" * 80)
            for auth in authorizations:
                name = auth.get("name", "Unknown")
                # Extract resource ID from the full name path
                auth_id = name.split("/")[-1] if "/" in name else name
                display_name = auth.get("displayName", "N/A")
                
                print(f"Auth ID:       {auth_id}")
                print(f"Resource Name: {name}")
                print(f"Display Name:  {display_name}")
                
                # Check for server-side OAuth details
                oauth_details = auth.get("serverSideOauth2", {})
                if oauth_details:
                    print(f"Client ID:     {oauth_details.get('clientId', 'N/A')}")
                    print(f"Token URI:     {oauth_details.get('tokenUri', 'N/A')}")
                print("-" * 80)
                
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP Error {e.code}: {body}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    list_authorizations()
