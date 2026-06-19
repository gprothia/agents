import os
import logging
from typing import Optional
from google.oauth2.credentials import Credentials
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

def get_user_credentials(tool_context: ToolContext) -> Optional[Credentials]:
    """
    Extracts user OAuth2 credentials from the ToolContext state using the configured AUTH_ID.
    Checks inside both the ToolContext state dict and environment variables for local testing.
    
    Args:
        tool_context: The context provided by the ADK runtime.
        
    Returns:
        google.oauth2.credentials.Credentials if token is found, else None.
    """
    try:
        auth_id = os.getenv("AUTH_ID")
        if auth_id and tool_context.state:
            access_token = tool_context.state.get(auth_id)
            if access_token:
                logger.info(f"Successfully retrieved access token for AUTH_ID: {auth_id} from ToolContext state.")
                return Credentials(token=access_token)
        if auth_id:
            env_token_specific = os.getenv(auth_id)
            if env_token_specific:
                logger.info(f"Successfully retrieved access token from environment variable '{auth_id}'.")
                return Credentials(token=env_token_specific)

    except Exception as e:
        logger.error("Context retrieval tool failure:")
        print("Error: ", e)
        return None

    return None

