#!/usr/bin/env python3
"""
List all Discovery Engine OAuth Authorizations and their linked resources 
(Vertex AI Agent Reasoning Engines, Search Apps/Engines, and GCP OAuth Clients).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from dotenv import load_dotenv
import google.auth
import google.auth.transport.requests

def get_auth_token():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token, project

def make_request(url, access_token, project):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Silently handle 404 or empty response if location has no resources
        return {}
    except Exception as e:
        return {}

def list_linked_resources():
    load_dotenv()
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "bold-kit-384717")
    de_location = os.getenv("VERTEX_SEARCH_LOCATION", "global")
    re_location = os.getenv("DEPLOYMENT_LOCATION", "us-central1")

    print(f"🔍 Auditing Discovery Engine OAuth Authorizations for Project: {project}\n")

    try:
        token, default_project = get_auth_token()
        if not project:
            project = default_project
    except Exception as e:
        print(f"❌ Error getting Google Cloud credentials: {e}")
        return

    # 1. Fetch Authorizations
    auth_url = f"https://global-discoveryengine.googleapis.com/v1alpha/projects/{project}/locations/global/authorizations"
    auth_resp = make_request(auth_url, token, project)
    authorizations = auth_resp.get("authorizations", [])

    if not authorizations:
        print("No OAuth Authorizations found in Discovery Engine.")
        return

    # 2. Fetch Reasoning Engines (Agent Engines)
    re_url = f"https://{re_location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{re_location}/reasoningEngines"
    re_resp = make_request(re_url, token, project)
    reasoning_engines = re_resp.get("reasoningEngines", [])

    # Map Reasoning Engines by AUTH_ID
    re_by_auth = {}
    for re_item in reasoning_engines:
        re_name = re_item.get("name", "")
        re_id = re_name.split("/")[-1] if "/" in re_name else re_name
        re_display_name = re_item.get("displayName", "Unnamed Agent")
        
        env_vars = {}
        deployment_spec = re_item.get("spec", {}).get("deploymentSpec", {})
        for env_entry in deployment_spec.get("env", []):
            if "name" in env_entry and "value" in env_entry:
                env_vars[env_entry["name"]] = env_entry["value"]
        
        auth_id_var = env_vars.get("AUTH_ID")
        search_app_var = env_vars.get("VERTEX_SEARCH_APP_ID")
        
        re_info = {
            "id": re_id,
            "full_name": re_name,
            "display_name": re_display_name,
            "auth_id": auth_id_var,
            "search_app_id": search_app_var,
            "location": re_location,
        }
        
        if auth_id_var:
            re_by_auth.setdefault(auth_id_var, []).append(re_info)
        # Also map by full authorization ID or bare string match
        re_by_auth.setdefault("__ALL__", []).append(re_info)

    # 3. Fetch Discovery Engine Search Apps / Engines
    de_engines_url = f"https://discoveryengine.googleapis.com/v1alpha/projects/{project}/locations/{de_location}/collections/default_collection/engines"
    de_resp = make_request(de_engines_url, token, project)
    engines = de_resp.get("engines", [])
    engines_by_id = {
        eng.get("name", "").split("/")[-1]: eng.get("displayName", "")
        for eng in engines
    }

    # 4. Display Results
    print(f"Found {len(authorizations)} Discovery Engine OAuth Authorization(s):\n" + "=" * 80)

    for auth in authorizations:
        full_name = auth.get("name", "")
        auth_id = full_name.split("/")[-1]
        display_name = auth.get("displayName", "N/A")
        oauth_details = auth.get("serverSideOauth2", {})
        client_id = oauth_details.get("clientId", "N/A")

        print(f"📌 Authorization ID:  {auth_id}")
        print(f"   Resource Name:     {full_name}")
        print(f"   Display Name:      {display_name}")
        print(f"   GCP OAuth Client:  {client_id}")

        # Linked Reasoning Engines
        linked_res = [
            r for r in re_by_auth.get("__ALL__", [])
            if (
                r.get("auth_id") == auth_id
                or r.get("auth_id") == display_name
                or (r.get("auth_id") and (auth_id in r["auth_id"] or r["auth_id"] in auth_id or r["auth_id"] in full_name))
            )
        ]
        
        if linked_res:
            print(f"   🔗 Linked Vertex AI Agent Reasoning Engine(s):")
            for r in linked_res:
                print(f"      • Agent Name: {r['display_name']}")
                print(f"        Engine ID:  {r['id']}")
                print(f"        Full Name:  {r['full_name']}")
                if r.get("search_app_id"):
                    app_title = engines_by_id.get(r["search_app_id"], "Unknown")
                    print(f"        Search App: {r['search_app_id']} ({app_title})")
        else:
            print("   🔗 Linked Vertex AI Agent Reasoning Engine(s): None found matching AUTH_ID")

        print("-" * 80)

if __name__ == "__main__":
    list_linked_resources()
