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
"""Handles the generation of asset sheets."""

import asyncio
import datetime
import json
import random
import re
import string
import time
from typing import Any, Dict, List, Optional, Tuple, cast
from unittest import result

from ad_generation_agent.func_tools.select_product import \
    retrieve_product_uri_from_bq
from ad_generation_agent.utils import ad_generation_constants, backup_media_configs
from ad_generation_agent.utils.eval_result import EvalResult
from ad_generation_agent.utils.gemini_utils import \
    generate_and_select_best_image
from adk_common.dtos import backup_media
from adk_common.dtos.generated_media import GeneratedMedia
from adk_common.utils import utils_agents
from adk_common.utils.utils_logging import (Severity, log_function_call,
                                            log_message)
from google import genai
from google.adk.tools.tool_context import ToolContext
from google.api_core import exceptions as api_exceptions
from google.genai import types


# @log_function_call
async def generate_asset_sheet(
    product_name: str,
    storyline: str,
    visual_style_guide: Dict[str, Any],
    tool_context: ToolContext,
    product_image_reference: str,
    prompt: str = "",
    brand_guidelines: str = "",
    reference_images: List[str] = [],
    previous_asset_sheet_uri: str = "",
    logo_image_uri: str = "",
) -> Dict[str, Any]:
    """Generates a visual asset sheet for a marketing campaign.

    This tool creates a comprehensive visual guide (an "Asset Sheet"), a single
    comprehensive artifact that establishes the core visual elements for the campaign.
    It includes the hero character, key locations, color palette, and overall style.

    Args:
        product_name (str): The name of the product being advertised.
        storyline (str): The complete narrative arc and script of the commercial.
        visual_style_guide (Dict[str, Any]): A dictionary defining the visual language,
            including color palettes, lighting, composition, and mood.
        prompt (str, optional): Additional specific instructions or constraints for the
            asset sheet generation. Defaults to "".
        brand_guidelines (str, optional): A comprehensive string detailing the brand's
            voice, core values, and visual identity standards. Defaults to "".
        product_image_reference (str, optional): A URI or path to the canonical product image.
            Defaults to "".
        reference_images (List[str], optional): A list of URIs or paths to additional
            reference imagery (e.g., style examples, competitors). Defaults to [].
        previous_asset_sheet_uri (str, optional): A URI or path to a previously generated
            asset sheet that should be used as a base for refinement. Defaults to "".
        logo_image_uri (str, optional): A URI or path to the brand logo. Defaults to "".

    Returns:
        Dict[str, Any]: The result containing the asset sheet filename and URI.
    """
    try:
        utils_agents.agentspace_print(tool_context, f"Generating asset sheet for {product_name}...")

        # Grab the product photo from BQ based on the product name
        retrieved_photo_image: GeneratedMedia | None = await _ensure_product_photo_artifact(
            product_name, tool_context, product_image_reference
        )
        
        utils_agents.agentspace_print(tool_context, "Product photo processed.")

        # Product photo is a requirement
        if not retrieved_photo_image or not retrieved_photo_image.media_bytes:
            response = {
                "status": "failed",
                "detail": "Failed to populate product photos.",
            }
            log_message(f"[generate_asset_sheet_response] {response}", Severity.ERROR)
            return response

        # Ensure logo logic
        final_logo_uri = logo_image_uri or backup_media_configs.get_backup_logo_url()
        log_message(f"Using logo URI: {final_logo_uri}", Severity.INFO)
        
        # Load logo
        logo_media: GeneratedMedia | None = None
        if final_logo_uri:
             logo_media = await utils_agents.load_resource(
                source_path=final_logo_uri, tool_context=tool_context
            )
             if not logo_media or not logo_media.media_bytes:
                 log_message(f"Failed to load logo from {final_logo_uri}, proceeding without explicit logo artifact.", Severity.WARNING)

        # Load reference images
        loaded_reference_images: List[Tuple[genai.types.Part, str]] = []
        
        if logo_media and logo_media.media_bytes:
             part = types.Part.from_bytes(data=logo_media.media_bytes, mime_type=logo_media.mime_type)
             loaded_reference_images.append((part, f"BRAND LOGO: This is the official brand logo (`{logo_media.filename}`). It must be clearly visible."))

        for ref_img_path in reference_images:
             generated_media: GeneratedMedia | None = await utils_agents.load_resource(
                source_path=ref_img_path, tool_context=tool_context
            )
             if generated_media and generated_media.media_bytes:
                part = types.Part.from_bytes(data=generated_media.media_bytes, mime_type=generated_media.mime_type)
                # We don't have descriptions for raw reference images passed here, so we use empty string or generic
                loaded_reference_images.append((part, f"Reference image: `{generated_media.filename}`"))

        # Load previous asset sheet if provided
        if previous_asset_sheet_uri:
             generated_media: GeneratedMedia | None = await utils_agents.load_resource(
                source_path=previous_asset_sheet_uri, tool_context=tool_context
            )
             if generated_media and generated_media.media_bytes:
                part = types.Part.from_bytes(data=generated_media.media_bytes, mime_type=generated_media.mime_type)
                # Strong instruction for the prompt
                loaded_reference_images.append((part, f"PREVIOUS ASSET SHEET: This is the existing asset sheet (`{generated_media.filename}`). Refine this specific image based on the user's new instructions. Maintain what wasn't asked to change."))

        story_data = {
            "storyline": storyline,
            "visual_style_guide": visual_style_guide
        }

        # Generate the asset sheet
        result: Tuple[GeneratedMedia, EvalResult | None]| None = await _generate_asset_sheet_image(
            story_data=story_data,
            product_image=retrieved_photo_image,
            tool_context=tool_context,
            additional_instructions=prompt,
            reference_images=loaded_reference_images,
            brand_guidelines=brand_guidelines
        )

        if not result:
            response = {
                "status": "failed",
                "detail": "Failed to generate asset sheet image.",
            }
            log_message(f"[generate_asset_sheet_response] {response}", Severity.ERROR)
            return response

        generated_media, _ = result
        
        description_parts = [
            f"Product Name: {product_name}",
            f"Storyline: {storyline}",
            f"Visual Style Guide: {visual_style_guide}",
            f"Brand Guidelines: {brand_guidelines}",
        ]
        if prompt:
            description_parts.append(f"Additional Instructions: {prompt}")
        if product_image_reference:
            description_parts.append(f"Product Image Reference: {product_image_reference}")
        if reference_images:
            description_parts.append(f"Reference Images: {', '.join(reference_images)}")
        if final_logo_uri:
             description_parts.append(f"Logo Image: {final_logo_uri}")

        utils_agents.agentspace_print(tool_context, "Asset sheet generation complete.")

        response = {
            "status": "success",
            "asset_sheet_filename": generated_media.filename,
            "asset_sheet_gcs_uri": generated_media.gcs_uri,
            "generation_details": json.dumps(description_parts),
        }
        log_message(f"[generate_asset_sheet_response] {response}", Severity.INFO)
        return response

    except Exception as e:
        log_message(f"Error in generate_asset_sheet: {e}", Severity.ERROR)
        raise e


# @log_function_call
async def _ensure_product_photo_artifact(
    product_name: str, tool_context: ToolContext, product_image_reference: Optional[str]
) -> Optional[GeneratedMedia]:
    """Ensures the product photo artifact exists, creating it if necessary.

    If a `product_photo_filename` is provided, it will be used directly.
    Otherwise, it fetches the product's image URI from BigQuery, downloads it
    from GCS, and saves it as an artifact.

    Args:
        product (str): The product name to look up if no filename is provided.
        tool_context (ToolContext): The context for accessing and saving artifacts.
        product_image_reference (Optional[str]): The reference to the product image. Defaults to None.

    Returns:
        The filename of the product photo artifact, or None on failure.
    """

    log_message("_ensure_product_photo_artifact called with product_name: {product_name}, product_image_reference: {product_image_reference}", Severity.DEBUG)
    
    product_uri = product_image_reference or backup_media_configs.get_backup_catalog_image_url()
    generated_media: GeneratedMedia | None = await utils_agents.load_resource(
            source_path=product_uri, tool_context=tool_context
        )
        
    if generated_media and generated_media.media_bytes:
        return generated_media
    else:
        return None


    # Commenting out the BQ retrieval piece.
    # product_gcs_uri = retrieve_product_uri_from_bq(product_name)
    # if not product_gcs_uri:
    #     log_message(f"Product '{product_name}' not found in BigQuery.", Severity.ERROR)
    #     return None

    # try:
    #     generated_media: GeneratedMedia | None = await utils_agents.load_resource(
    #         source_path=product_gcs_uri, tool_context=tool_context
    #     )
        
    #     if not generated_media or not generated_media.media_bytes:
    #         raise ValueError("Failed to download image bytes.")

    #     await utils_agents.save_to_artifact_and_render_asset(
    #         asset=generated_media,
    #         context=tool_context,
    #         save_in_gcs=True,
    #         gcs_folder=utils_agents.get_or_create_unique_session_id(tool_context),
    #     )
        
    #     log_message(
    #         f"Saved product photo '{product_gcs_uri}' as artifact '{generated_media.filename}'",
    #         Severity.INFO,
    #     )
    #     return generated_media
    # except (api_exceptions.GoogleAPICallError, IOError) as e:
    #     log_message(
    #         f"Failed to download or save product photo from GCS: {e}", Severity.ERROR
    #     )
    #     return None


# @log_function_call
def _process_visual_style_guide(visual_style_guide: Dict[str, Any]) -> Dict[str, str]:
    """Processes the visual style guide into formatted strings.

    Args:
        visual_style_guide (Dict[str, Any]): The visual style guide dictionary.

    Returns:
        A dictionary of processed descriptions.
    """

    def format_list(items: List[Any]) -> str:
        processed = []
        for item in items:
            if isinstance(item, dict):
                processed.append(" ".join(str(v) for v in item.values()))
            else:
                processed.append(str(item))
        return ", ".join(processed)

    if isinstance(visual_style_guide, list):
        log_message(
            "visual_style_guide is a list, expected a dict. Using first element if available.",
            Severity.WARNING,
        )
        if visual_style_guide:
            temp_list = cast(List[Any], visual_style_guide)
            visual_style_guide = cast(Dict[str, Any], temp_list[0])
        else:
            visual_style_guide = {}

    if not isinstance(visual_style_guide, dict):
        log_message(
            "visual_style_guide is not a dict. Using empty dict.", Severity.WARNING
        )
        visual_style_guide = {}

    asset_sheet_items = visual_style_guide.get("asset_sheet", [])
    characters = visual_style_guide.get("characters", [])
    locations = visual_style_guide.get("locations", [])

    return {
        "asset_sheet": format_list(asset_sheet_items),
        "characters": ". ".join(
            (
                f"{item.get('name', '')}: {item.get('description', '')}"
                if isinstance(item, dict)
                else str(item)
            )
            for item in characters
        ),
        "locations": format_list(locations),
    }


# @log_function_call
def _create_asset_sheet_prompt(
    story_data: Dict[str, Any],
    additional_instructions: str,
    reference_images_descriptions: list[str],
    brand_guidelines: str = "",
) -> str:
    """Creates the prompt for the asset sheet image."""
    visual_style_guide = story_data.get("visual_style_guide", {})
    processed_vsg = _process_visual_style_guide(visual_style_guide)

    additional_instructions_bullet = ""
    reference_images_list = ""
    brand_guidelines_text = ""

    if brand_guidelines:
        brand_guidelines_text = f"\n# Brand Guidelines:\n{brand_guidelines}\n\nEnsure the asset sheet strictly adheres to these brand guidelines, especially regarding color palette and visual identity."

    if reference_images_descriptions:
        additional_instructions_bullet = (
            "# The user provided images that you **MUST** leverage"
        )
        for image_description in reference_images_descriptions:
            reference_images_list += f"\n* {image_description}"

    return f"""
Create a visual asset sheet for an ad (i.e. a commercial).

# Instructions: 

Create a clean, organized collage displaying each of the following:
1) Front and side profiles of each character
2) Locations/settings for each scene
3) The attached image of the product (you must use this exact product)
4) Ensure the result is a beautiful, high-quality image that is easy to understand and visually appealing.
5) Avoid white dull background.
6) It is imperative that if a logo is provided, it makes it to the resulting asset sheet.

# Additional Information:

* Characters: {processed_vsg["characters"]}
* Locations: {processed_vsg["locations"]}

{brand_guidelines_text}

{additional_instructions_bullet}

{reference_images_list}

# Additional instructions: 

{additional_instructions}

"""


# @log_function_call
async def _generate_asset_sheet_image(
    story_data: Dict[str, Any],
    product_image: GeneratedMedia,
    tool_context: ToolContext,
    additional_instructions: str,
    reference_images: Optional[List[Tuple[genai.types.Part, str]]] = None,
    brand_guidelines: str = "",
) -> Tuple[GeneratedMedia, EvalResult | None] | None:
    """Generates and evaluates asset sheet images, saving the best one.

    Args:
        story_data (Dict[str, Any]): The storyline and visual style guide data.
        product_photo (GeneratedMedia): The product photo.
        tool_context (ToolContext): The context for saving artifacts.
        additional_instructions (str): Additional instructions provided by the user or the agent.

    Returns:
        The filename of the generated asset sheet
    """

    image_prompt = _create_asset_sheet_prompt(
        story_data=story_data,
        additional_instructions=additional_instructions,
        reference_images_descriptions=(
            [desc for _, desc in reference_images] if reference_images else []
        ),
        brand_guidelines=brand_guidelines,
    )
    
    utils_agents.agentspace_print(tool_context, "Generating asset sheet image...")
    
    log_message(
        f"Generating asset sheet image for prompt: '{image_prompt}'", Severity.INFO
    )

    try:
        contents = []
        
        if product_image and product_image.media_bytes:
            part = types.Part.from_bytes(data=product_image.media_bytes, mime_type=product_image.mime_type)
            contents.append(part)
        
        if reference_images:
            for part, _ in reference_images:
                contents.append(part)
    except (FileNotFoundError, ValueError) as e:
        log_message(
            f"Failed to load product photo artifact with name: `{product_image.filename}` and GCS URI: `{product_image.gcs_uri}`. Error: {e}",
            Severity.ERROR,
        )
        return None

    # Microsecond Timestamp + Random Chars
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
    random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
    
    best_attempt = await generate_and_select_best_image(
        filename_without_extension=f"asset_sheet_{timestamp_str}_{random_chars}",
        prompt=image_prompt,
        input_images=contents,
        allow_collage=True,
    )

    if not best_attempt:
        return None
    else:
        best_eval = best_attempt.get("best_eval")
        best_attempt_evaluation = cast(EvalResult, best_eval) if best_eval else None
        image_bytes = best_attempt["image_bytes"]
        mime_type = best_attempt["mime_type"]
        file_name = best_attempt["file_name"]

        log_message(
            f"Successfully generated asset sheet image. Filename: {file_name}, Size: {len(image_bytes)} bytes, MIME: {mime_type}",
            Severity.INFO,
        )

        generated_media = GeneratedMedia(
            media_bytes=image_bytes,
            filename=file_name,
            mime_type=mime_type,
        )

        generated_media = await utils_agents.save_to_artifact_and_render_asset(
            asset=generated_media,
            context=tool_context,
            save_in_gcs=True,
            gcs_folder=utils_agents.get_or_create_unique_session_id(tool_context),
            save_in_artifacts=True,
        )

        log_message(f"Saved asset sheet image to {file_name}", Severity.INFO)

        return generated_media, best_attempt_evaluation
