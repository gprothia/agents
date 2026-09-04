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
"""Handles the generation of images based on storyline prompts."""

import asyncio
import json
import datetime
import random
import string
import time
from typing import Any, Dict, List, Optional, cast

from ad_generation_agent.utils import ad_generation_constants
from ad_generation_agent.utils.eval_result import EvalResult
from ad_generation_agent.utils.gemini_utils import (
    generate_and_select_best_image)
from ad_generation_agent.utils.scene import Scene
from adk_common.dtos.generated_media import GeneratedMedia
from adk_common.utils import utils_agents, utils_gcs
from adk_common.utils.constants import get_required_env_var
from adk_common.utils.utils_logging import (Severity, log_function_call,
                                            log_message)
from google import genai
from google.adk.tools.tool_context import ToolContext
from google.cloud import storage
from google.genai import types
from google.genai.types import HarmBlockThreshold, HarmCategory
from vertexai.preview.vision_models import ImageGenerationModel

GOOGLE_CLOUD_PROJECT = get_required_env_var("GOOGLE_CLOUD_PROJECT")
STORYBOARD_GENERATION_MODEL = get_required_env_var("STORYBOARD_GENERATION_MODEL")
GOOGLE_CLOUD_BUCKET_ARTIFACTS = get_required_env_var("GOOGLE_CLOUD_BUCKET_ARTIFACTS")

RENDER_IMAGES_INLINE = get_required_env_var("RENDER_IMAGES_INLINE").lower() in ("true", "1", "yes")
RENDER_VIDEOS_INLINE = get_required_env_var("RENDER_VIDEOS_INLINE").lower() in ("true", "1", "yes")


# @log_function_call
async def _load_asset_sheet(asset_sheet_uri: str, tool_context: ToolContext) -> tuple[Optional[types.Part], Optional[str]]:
    """Loads the asset sheet image."""
    try:
        if not asset_sheet_uri:
            return None, "Asset sheet URL is empty, please pass a correct URL of the asset sheet to use."

        generated_media: GeneratedMedia | None = None
        if asset_sheet_uri:
            generated_media = await utils_agents.load_resource(
                source_path=asset_sheet_uri,
                tool_context=tool_context,
            )

        if not generated_media or not generated_media.media_bytes:
            return None, "Asset sheet could not be retrieved. The URL sent is invalid or the file is corrupted."
        
        asset_sheet_image = types.Part.from_bytes(
            data=generated_media.media_bytes, mime_type=generated_media.mime_type
        )
    except Exception as e:
        log_message(f"Failed to load asset sheet: {e}", Severity.ERROR)
        return None, f"Failed to load asset sheet: {e}"

    return asset_sheet_image, None


# @log_function_call
async def _create_image_generation_task(
    scene: Scene, asset_sheet_image: types.Part, tool_context: ToolContext
) -> Dict[str, Any]:
    """Creates a task for generating a single image.

    Args:
        scene (Scene): The scene to generate an image for.
        asset_sheet_image (types.Part): The asset sheet image part.
        tool_context (ToolContext): The tool context for saving artifacts.

    Returns:
        Dict[str, Any]: A dictionary containing the result of the image generation.
            - "status" (str): "success" if the image was generated successfully.
            - "detail" (str): A message describing the result.
            - "file_name" (str): The filename of the generated image.
            - "image_bytes" (bytes): The binary content of the generated image.
            - "mime_type" (str): The MIME type of the generated image.
            Returns an empty dictionary if generation fails.
    """
    log_message(f"Generating image for scene: {scene}", Severity.INFO)

    if isinstance(scene, dict):
        scene = Scene(**scene)

    # Microsecond Timestamp + Random Chars
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
    random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
    
    filename_prefix = (
        f"{ad_generation_constants.SCENE_IMAGE_FILENAME_PREFIX}_{scene.scene_number}_{timestamp_str}_{random_chars}"
    )

    reference_image_parts = []
    reference_image_parts.append(asset_sheet_image)

    reference_images: List[str] | None = scene.reference_images
    if reference_images:
        for uri in reference_images:
            generated_media: GeneratedMedia | None = await utils_agents.load_resource(
                source_path=uri, tool_context=tool_context
            )
            
            if generated_media and generated_media.media_bytes:
                part = types.Part.from_bytes(data=generated_media.media_bytes, mime_type=generated_media.mime_type)
                reference_image_parts.append((part))

    prompt = f"{scene.image_prompt}"
    prompt += "\n\n**IMPORTANT GUIDELINES TO REINFORCE**:"
    prompt += "\n* Ensure the images generated follow all guidance provided in the asset sheet, most especially product & character consistency."
    prompt += "\n* The image will be for 1 scene so it is **IMPERATIVE THAT YOU AVOID GENERATING COLLAGES** - it should be a single image detailing a single scene."
    prompt += "\n* If the scene has the logo of the company, make sure it is visible and clear and extremely accurate."
    
    prompt += "\n\n**STYLE MANDATE**:"
    prompt += "\n* Unless a specific art style is requested in the prompt (e.g., Claymation, 3D Render, Line Art), the image MUST be **Hyper-Realistic** and **Photorealistic**."
    prompt += "\n* Default to Hyper-Realistic if no style is specified."
    prompt += "\n* Avoid any 'AI smoothness', cartoonish effects, or unnatural lighting."
    prompt += "\n* Textures (skin, fabric, materials) must be indistinguishable from real life."
    
    prompt += "\n\n**CONSISTENCY PROTOCOL**:"
    prompt += "\n* You **MUST** use the attached reference images to maintain consistent character appearance (face, clothes, age) and product details across all scenes."
    prompt += "\n* If the character's face is visible, it MUST match the reference image exactly, it should be pixel-perfect IDENTICAL."
    prompt += "\n* Do not force facial visibility if the scene calls for a rear/obscured view, but IF visible, identity must be identical."
    
    if scene.is_logo_scene:
        prompt += "\n\n**CRITICAL LOGO FIDELITY PROTOCOL**:"
        prompt += "\n* This scene features the company logo. You **MUST** use the provided logo asset EXACTLY as is."
        prompt += "\n* **DO NOT** alter, reimagine, or hallucinate the logo."
        prompt += "\n* It must match the reference pixel-perfectly if possible."
    
    prompt += "\n\nAttached you will find the images that should be used for the following purposes:"
    prompt += f"\n* Among them, you will find the Asset Sheet: a collage that details the main components of the story (like the company logo, the character, the main scenes, etc.). You **MUST** ensure the images generated follow the guidance from this asset sheet, most especially product & character consistency."

    prompt += "\n\n**VIDEO GENERATION COMPATIBILITY (CRITICAL)**:"
    prompt += "\n* This image will be the **FIRST FRAME** of a 4-second video generated by Google Veo."
    prompt += "\n* **SIMPLE ACTION:** Prefer broad body movements (running, jumping, walking). Avoid intricate fine motor interactions (e.g. tying shoes, eating, typing, finger movements) which are hard to generate by video generation models."
    prompt += "\n* **CLEAR SEPARATION:** Ensure the subject is clearly separated from the background to facilitate motion generation."
    prompt += "\n* **SINGLE SHOT:** This must be a single, cohesive framing. **ABSOLUTELY NO COLLAGES** or split screens."

    return await generate_and_select_best_image(
        filename_without_extension=filename_prefix,
        input_images=reference_image_parts,
        prompt=prompt,
    )


# @log_function_call
async def generate_image_from_storyline(
    scene_number: int,
    asset_sheet_uri: str,
    prompt: str,
    reference_images: List[str],
    is_logo_scene: bool,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    f"""Generates a single image for a commercial storyboard based on the provided parameters.

    Args:
        scene_number (int): The scene for which this image is being generated (starting from 1).
        asset_sheet_uri (str): the GCS URL of the asset sheet image. It is imperative that this be set to the URL of the asset sheet image selected by the user. Without it the tool will fail.
        prompt (str): A detailed image generation prompt for the scene.
            * Should describe in detail the scene.
            * Should be of a single location/setting. Avoid collages and multiple shots in a single video.
            * Character names won't be understood here, use pronouns + descriptions to detail actions.
            * Be VERY descriptive in what movements and camera angles you expect and what should not move in the scene. Describe who/what is causing the movement.
            * A video generation model will use this image as a starting point so consider how a subsequent video will move from it. Do not generate images that will lead to video inconsistencies.
            * For logo prompts ensure the logo is shown in a prominent position and that the outcome is 100% accurate. In this scenario, ensure you provide the logo as a reference image.
        reference_images (List[str]): A list of URIs, URLs or filenames for all the images that should be used as reference for the new image to be generated.
        is_logo_scene (bool): True if this scene features the company logo, False otherwise.

    Returns:
        Dict[str, Any]: A dictionary containing the status and details of the image generation process.
    """
    try:
        asset_sheet_image, error_msg = await _load_asset_sheet(asset_sheet_uri, tool_context)
        if not asset_sheet_image or error_msg:
            log_message(
                f"[generate_image_from_storyline_response] Error loading asset sheet. Error: {error_msg}. Asset sheet len: {len(asset_sheet_image.inline_data.data) if asset_sheet_image and asset_sheet_image.inline_data and asset_sheet_image.inline_data.data else 0}",
                Severity.ERROR,
            )
            response = {"status": "failed", "detail": error_msg}
            return response

        utils_agents.agentspace_print(tool_context, f"Generating image for scene {scene_number}...")

        # Construct a Scene object to reuse existing logic
        scene_obj = Scene(
            scene_number=scene_number,
            image_prompt=prompt,
            reference_images=reference_images,
            is_logo_scene=is_logo_scene,
        )

        result: Dict[str, Any] = await _create_image_generation_task(
            scene=scene_obj,
            asset_sheet_image=asset_sheet_image,
            tool_context=tool_context,
        )

        if result and result.get("status") == "success" and result.get("image_bytes"):
            generated_media = GeneratedMedia(
                filename=result["file_name"],
                mime_type=ad_generation_constants.IMAGE_MIMETYPE,
                media_bytes=result["image_bytes"],
            )

            generated_media = await utils_agents.save_to_artifact_and_render_asset(
                asset=generated_media,
                context=tool_context,
                save_in_gcs=True,
                save_in_artifacts=RENDER_IMAGES_INLINE,
                gcs_folder=utils_agents.get_or_create_unique_session_id(tool_context),
            )
    
            best_eval = result.get("best_eval")
            best_attempt_evaluation = cast(EvalResult, best_eval) if best_eval else None
            scene_obj.best_image_eval = best_attempt_evaluation

            log_message(f"[generate_image_from_storyline_response] Image generation successful for scene: `{scene_number}`. New image URI: {generated_media.gcs_uri}", Severity.INFO)
            return {
                "status": "success",
                "detail": "Image generation successful.",
                "generated_image_uri": generated_media.gcs_uri,
            }
           
        else:
            result_string = json.dumps(result) if result else "None"
            log_message(f"[generate_image_from_storyline_response] Failed to save generated image for scene: `{scene_number}`. Result: {result_string}", Severity.ERROR)
            response = {"status": "failed", "detail": "Image generation failed."}
            return response

    except Exception as e:
        log_message(f"Error in generate_image_from_storyline: {e}", Severity.ERROR)
        raise e
