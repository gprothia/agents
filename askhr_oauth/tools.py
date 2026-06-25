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
    if user_email:
        return user_email
    else:
        return "NotFound"

def debug_identity(callback_context) -> dict:
    data = callback_context.state.to_dict()      # <-- materialize the dict
    return {
        "state_keys": list(data.keys()),
        "state_sample": {k: str(v)[:60] for k, v in data.items()},
    }

def get_user_context(callback_context, **kwargs):
    """
    Retrieve the current authenticated user identity context (Email and HR Country).
    Always call this tool before making ANY decisions to understand who you are speaking with.
    """
    try:
        context = callback_context
        state = context.state
        if state.get("initialized") == True:
            return None
        user_email = None
        auth_client_id = os.getenv("AUTH_ID")
        token = state.get(auth_client_id)
        print("DEBUG IDENTITY",debug_identity(callback_context))

        if token:
            user_email = get_email_from_oauth_token(token) 
            print(f"User email: {user_email}")
            country = "USA"
            state["employee_id"] = user_email
            state["country"] = country
            state["initialized"] = True
            logger.info(f"User email: {user_email}")
            logger.info(f"User context: {callback_context}")
            
        return None
    except Exception as e:
        print("ERROR!!!",e)
        logger.error(f"Context retrieval callback failure: {e}")
        state = callback_context.state
        state["employee_id"] = "Unknown"
        state["country"] = "Unknown"
        state["initialized"] = True
        return None
    


def search_hr_policy(query: str,tool_context: ToolContext) -> str:
    """
    Search for HR policies, benefits, and company documentation using Vertex AI Search.
    
    Args:
        query: The user's question or search query regarding policies.
        country: Optional. The country of the employee (e.g., "USA", "India") to filter policies by.
        
    Returns:
        A summarized string of extracted document chunks from the search results.
    """
    try:
        client = discoveryengine.SearchServiceClient()
        country = tool_context.state.get("country")
        # Direct path to the engine's serving config as provided in the cURL
        serving_config = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/engines/{SEARCH_APP_ID}/servingConfigs/default_search"
        
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=10,
            filter=f'country: ANY("{country}")' if country else None,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO
            ),
            spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
            ),
            language_code="en-US",
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                    max_extractive_answer_count=5
                ),
                summary_spec=discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
                    summary_result_count=3,
                    include_citations=True
                )
            )
        )
        
        response = client.search(request)
        
        results = []
        if getattr(response, "summary", None) and response.summary.summary_text:
            results.append(f"--- GENERATIVE SUMMARY ---\n{response.summary.summary_text}\n\n--- EXACT VERBATIM CITATIONS ---")
                
        for result in response.results:
            # Depending on index type (unstructured vs structured), extract document text
            try:
                if result.document.derived_struct_data:
                    doc_title = result.document.derived_struct_data.get("title", "Unknown Policy Document")
                    extractive_answers = result.document.derived_struct_data.get("extractive_answers", [])
                    if extractive_answers:
                        for answer in extractive_answers:
                            snippet = answer.get("content", "").replace("&#39;", "'").replace("&quot;", '"')
                            page = answer.get("pageNumber", "?")
                            # Provide the LLM with the exact verbatim quote and its citation
                            results.append(f'Verbatim quote: "{snippet}"\n(Source: {doc_title}, Page {page})')
                elif result.document.struct_data:
                    # Generic fallback
                    results.append(str(result.document.struct_data))
            except Exception as e:
                logger.warning(f"Could not parse document result: {e}")
                pass
        if not results:
            return "No relevant HR policy documentation found for your query. The search app might be empty or still indexing."
            
        return "\n".join(set(results))
        
    except Exception as e:
        logger.error(f"Vertex AI Search Tool Error: {e}")
        return f"An error occurred while searching policies: {str(e)}. Please try again later."


def get_employee_info(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Fetch employee information (e.g., address, leave balance, role) from the HR database (via HTTP API).
    
    Args:
        tool_context: The ADK ToolContext containing employee information.
        
    Returns:
        A dictionary containing the requested employee information, or an error dictionary.
    """
    try:
        #creds = get_user_credentials(tool_context)
        headers = {}
        employee_id = tool_context.state.get("employee_id")
        # Commented out to avoid token validation issues on public API
        # if creds and creds.token:
        #     headers["Authorization"] = f"Bearer {creds.token}"
            
        url = f"{EMPLOYEE_API_URL.rstrip('/')}/employee/{employee_id}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 404:
            return {"error": "Employee ID not found in the HR database."}
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP API Get Info Error: {e}")
        return {"error": f"Failed to retrieve employee info from backend: {str(e)}"}


def update_employee_info(field_to_update: str, new_value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Update a specific field in the employee's HR profile via the backend API.
    
    Args:
        field_to_update: The name of the field to update (e.g., 'address', 'remote', 'officeLocation').
        new_value: The new value to set for the field.
        tool_context: T tool_context: The ADK ToolContext containing employee information.
        
    Returns:
        A dictionary indicating success and displaying the updated field.
    """
    try:
        #creds = get_user_credentials(tool_context)
        headers = {}
        employee_id = tool_context.state.get("employee_id")
        # Commented out to avoid token validation issues on public API
        # if creds and creds.token:
        #     headers["Authorization"] = f"Bearer {creds.token}"
            
        url = f"{EMPLOYEE_API_URL.rstrip('/')}/employee/{employee_id}/update"
        payload = {
            "field_to_update": field_to_update,
            "new_value": new_value
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 404:
            return {"error": "Employee ID not found in the HR database."}
            
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP API Update Info Error: {e}")
        return {"error": f"Failed to update employee info via backend: {str(e)}"}
