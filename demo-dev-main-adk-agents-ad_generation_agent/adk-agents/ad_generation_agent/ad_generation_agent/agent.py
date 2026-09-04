# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Initializes and configures the main content generation agent.

This script sets up the root agent responsible for orchestrating the entire
ad generation workflow. It defines the agent's instructions, registers all
necessary tools, and configures the underlying language model.
"""

import json
import os
from typing import Any, Optional

import requests
import vertexai
from adk_common.utils.constants import (get_optional_env_var,
                                        get_required_env_var)
from adk_common.utils.utils_logging import Severity, log_message
from google.adk.agents.readonly_context import ReadonlyContext


# --- 1. Environment Variable Retrieval ---
GOOGLE_CLOUD_PROJECT = get_required_env_var("GOOGLE_CLOUD_PROJECT")
LLM_GEMINI_MODEL_ADGEN_ROOT = get_required_env_var("LLM_GEMINI_MODEL_ADGEN_ROOT")
DEMO_COMPANY_NAME = get_optional_env_var("DEMO_COMPANY_NAME", "ACME Corp")

# --- 2. Configure Model Location ---
# Initialize Vertex AI
# We must prioritize MODELS_CLOUD_LOCATION to avoid conflict with reserved GOOGLE_CLOUD_LOCATION in Reasoning Engine
MODEL_LOCATION = os.environ.get("MODELS_CLOUD_LOCATION", os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
# Force GOOGLE_CLOUD_LOCATION for any libraries that rely on it (like google-genai)
os.environ["GOOGLE_CLOUD_LOCATION"] = MODEL_LOCATION
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True" # Retain this line from original code

log_message(f"GOOGLE_CLOUD_PROJECT: {GOOGLE_CLOUD_PROJECT}", Severity.DEBUG)
log_message(f"LLM_GEMINI_MODEL_ADGEN_ROOT: {LLM_GEMINI_MODEL_ADGEN_ROOT}", Severity.DEBUG)
log_message(f"Model location set to: {MODEL_LOCATION}", Severity.DEBUG)
log_message(f"Effective GOOGLE_CLOUD_LOCATION for genai client: {os.environ.get('GOOGLE_CLOUD_LOCATION')}", Severity.DEBUG)
log_message(f"GOOGLE_GENAI_USE_VERTEXAI: {os.environ.get('GOOGLE_GENAI_USE_VERTEXAI')}", Severity.DEBUG)

# This configures the default location for calls made *directly* through the vertexai SDK
# and influences the google-genai library when used with Vertex AI.
try:
    vertexai.init(project=GOOGLE_CLOUD_PROJECT, location=MODEL_LOCATION)
    log_message(f"vertexai.init() called successfully with project={GOOGLE_CLOUD_PROJECT}, location={MODEL_LOCATION}", Severity.DEBUG)
except Exception as e:
    log_message(f"Error initializing Vertex AI SDK: {e}. Continuing, as google-genai env vars might suffice.", Severity.DEBUG)

from adk_common.utils import utils_gcs, utils_prompts
from adk_common.utils.utils_agents import SESSION_ARTIFACTS_STATE_KEY
from adk_common.dtos.generated_media import GeneratedMedia
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types as genai_types
from .func_tools.combine_video import combine
from .func_tools.generate_audio import generate_audio_and_voiceover
from .func_tools.generate_asset_sheet import generate_asset_sheet
from .func_tools.generate_image import generate_image_from_storyline
from .func_tools.generate_display_ad import generate_display_ad
from .func_tools.generate_video import generate_video
from .func_tools.retrieve_generated_assets import retrieve_generated_assets
from .func_tools.evaluate_ad import evaluate_ad
from .utils.storytelling import STORYTELLING_INSTRUCTIONS


async def _dynamic_instruction_provider(
    context: ReadonlyContext,
) -> str:
    """Dynamically provides instructions to the agent by loading and formatting a prompt."""

    prompt = utils_prompts.load_prompt_file_from_calling_agent(
        {
            "DEMO_COMPANY_NAME": DEMO_COMPANY_NAME,
            "STORYTELLING_INSTRUCTIONS": STORYTELLING_INSTRUCTIONS,
            "GCS_AUTHENTICATED_DOMAIN": utils_gcs.GCS_AUTHENTICATED_DOMAIN,
            "GCS_AUTHENTICATED_DOMAIN_SANS_PROTOCOL": utils_gcs.GCS_AUTHENTICATED_DOMAIN_SANS_PROTOCOL,
            "SESSION_ARTIFACTS_STATE": json.dumps(context.state.get(SESSION_ARTIFACTS_STATE_KEY, "{}"))
        }
    )
    return prompt


def _before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext) -> dict | None:

    log_message(f"Tool Call: {tool.name}", Severity.INFO)
    log_message(f"Arguments: {args}", Severity.INFO)


def confirm_url_exists(url: str) -> bool:
    """Confirm if a URL exists."""
    try:
        response = requests.get(url, timeout=10)
        return response.status_code == 200
    except Exception as e:
        log_message(f"Error checking URL {url}: {e}", Severity.ERROR)
        return False


root_agent = LlmAgent(
    name="content_generation_agent",
    model=LLM_GEMINI_MODEL_ADGEN_ROOT,
    instruction=_dynamic_instruction_provider,
    tools=[
        FunctionTool(func=generate_asset_sheet),
        FunctionTool(func=generate_image_from_storyline),
        FunctionTool(func=generate_display_ad),
        FunctionTool(func=generate_video),
        FunctionTool(func=generate_audio_and_voiceover),
        FunctionTool(func=combine),
        FunctionTool(func=retrieve_generated_assets),
        FunctionTool(func=evaluate_ad),
        FunctionTool(func=confirm_url_exists),
    ],
    before_tool_callback=_before_tool_callback,
)
