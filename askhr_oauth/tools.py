import os
import logging
from typing import Dict, Any, List, Optional
import requests
import contextvars
from google.cloud import discoveryengine
from google.adk.tools import ToolContext
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

from auth import get_user_credentials # <--- Changed from .auth to avoid relative import error

# --- Safe Cache for Gemini Identity ---
_current_user_email = contextvars.ContextVar("user_email", default=None)
_current_user_country = contextvars.ContextVar("user_country", default=None)

def _fetch_country_and_cache_isolated(email: str):
    """Silent helper to fetch the user's country from DB and cache it isolated to this thread."""
    if not email:
        return
    try:
        api_url = os.getenv("EMPLOYEE_API_URL", "https://employee-api-851970768145.us-central1.run.app")
        country_lookup = requests.get(f"{api_url.rstrip('/')}/employee/{email}", timeout=5)
        if country_lookup.status_code == 200:
            _current_user_country.set(country_lookup.json().get("country", "Unknown"))
    except requests.exceptions.RequestException as db_e:
        logger.warning(f"Failed country lookup for user ctx: {db_e}")

def get_user_identity(tool_context: ToolContext) -> str:
    """
    Discover user identity by resolving the token and extracting the email.
    Aligns with tools.py robustness patterns.
    """
    
    # 1. Robust token extraction (Context -> Environment Fallback)
    credentials = get_user_credentials(tool_context)
    active_token = credentials.token if credentials else ""
    
    if not active_token:
        # Fallback for local testing (matches your current tools.py pattern)
        auth_id = os.getenv("AUTH_ID")
        if auth_id:
            active_token = os.getenv(auth_id)

    if not active_token:
        return "" # Consistent return type (String)

    try:
        # 2. Use tokeninfo (handles both JWT and Access tokens like your current code)
        url = "https://oauth2.googleapis.com/tokeninfo"
        params = {}
        if len(active_token.split('.')) == 3:
            params["id_token"] = active_token
        else:
            params["access_token"] = active_token

        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            email = data.get("email")
            if email:
                _current_user_email.set(email) 
                _fetch_country_and_cache_isolated(email)
                return email
        else:
            logger.warning(f"Token verification failed (Status {response.status_code}): {response.text}")
                
    except Exception as e:
        # Use standard logging import from your file
        logging.error(f"User identity resolution failure: {e}")
        
    return "" # Consistent return type on failure

def get_current_user_context(tool_context: ToolContext) -> Dict[str, str]:
    """
    Retrieve the current authenticated user identity context (Email and HR Country).
    Always call this tool before making ANY decisions to understand who you are speaking with.
    
    Returns:
        A dictionary containing 'employee_id' (email) and 'country'.
    """
    try:
        # Support mock email for testing
        mock_email = os.getenv("MOCK_EMAIL")
        if mock_email:
            return {"employee_id": mock_email, "country": "USA"}
            
        # Evaluate context lazily
        email = get_user_identity(tool_context) or "unknown"
        country = _current_user_country.get() or "US"
        return {"employee_id": email, "country": country}
    except Exception as e:
        #logger.error(f"Context retrieval tool failure:")
        return {"employee_id": "Unknown", "country": "Unknown"}

# --- Configuration ---
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "bold-kit-384717")
LOCATION = os.getenv("VERTEX_SEARCH_LOCATION", "global")
SEARCH_APP_ID = os.getenv("VERTEX_SEARCH_APP_ID", "askhr_1774746828030")
EMPLOYEE_API_URL = os.getenv("EMPLOYEE_API_URL", "http://localhost:8080")

def search_hr_policy(query: str, country: str = None) -> str:
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


def get_employee_info(employee_id: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Fetch employee information (e.g., address, leave balance, role) from the HR database (via HTTP API).
    
    Args:
        employee_id: The unique employee ID of the user.
        tool_context: The ADK ToolContext to extract tokens for authorization.
        
    Returns:
        A dictionary containing the requested employee information, or an error dictionary.
    """
    try:
        creds = get_user_credentials(tool_context)
        headers = {}
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


def update_employee_info(employee_id: str, field_to_update: str, new_value: str, tool_context: ToolContext) -> Dict[str, Any]:
    """
    Update a specific field in the employee's HR profile via the backend API.
    
    Args:
        employee_id: The unique employee ID of the user.
        field_to_update: The name of the field to update (e.g., 'address', 'remote', 'officeLocation').
        new_value: The new value to set for the field.
        tool_context: The ADK ToolContext to extract tokens for authorization.
        
    Returns:
        A dictionary indicating success and displaying the updated field.
    """
    try:
        creds = get_user_credentials(tool_context)
        headers = {}
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
