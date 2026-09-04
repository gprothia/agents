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
"""Generates video clips from images using Google's Vertex AI services."""

import asyncio
import json
import os
import random
import re
import string
import datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from ad_generation_agent.utils import ad_generation_constants

from ad_generation_agent.utils.eval_result import EvalResult
from ad_generation_agent.utils.evaluate_media import evaluate_media
from ad_generation_agent.utils.gemini_utils import get_gemini_client
from ad_generation_agent.utils.scene import Scene
from adk_common.dtos.generated_media import GeneratedMedia
from adk_common.utils import utils_agents
from adk_common.utils.constants import get_optional_env_var, get_required_env_var
from adk_common.utils.utils_logging import Severity, log_function_call, log_message
from google import genai
from google.adk.tools.tool_context import ToolContext
from google.api_core import exceptions as api_exceptions
from google.cloud import storage
from google.genai import types
from google.genai.types import (
    GenerateContentConfig,
    GeneratedVideo,
    GenerateVideosConfig,
)
from google.genai.types import Image as GenImage

# --- Configuration ---

GOOGLE_CLOUD_BUCKET_ARTIFACTS = get_required_env_var("GOOGLE_CLOUD_BUCKET_ARTIFACTS")
VIDEO_GENERATION_MODEL = get_required_env_var("VIDEO_GENERATION_MODEL")
LLM_GEMINI_MODEL_ADGEN_SUBCALLS = get_required_env_var("LLM_GEMINI_MODEL_ADGEN_SUBCALLS") 
VIDEO_DEFAULT_ASPECT_RATIO = get_required_env_var("VIDEO_DEFAULT_ASPECT_RATIO")
VIDEO_GENERATION_EVAL_REATTEMPTS = int(get_required_env_var("VIDEO_GENERATION_EVAL_REATTEMPTS"))
VIDEO_GENERATION_RETRY_DELAY_SECONDS = int(get_required_env_var("VIDEO_GENERATION_RETRY_DELAY_SECONDS"))
VIDEO_GENERATION_STATUS_POLL_SECONDS = int(get_required_env_var("VIDEO_GENERATION_STATUS_POLL_SECONDS"))
VIDEO_GENERATION_TENACITY_ATTEMPTS = int(get_required_env_var("VIDEO_GENERATION_TENACITY_ATTEMPTS"))
VIDEO_GENERATION_CONCURRENCY_LIMIT = int(get_required_env_var("VIDEO_GENERATION_CONCURRENCY_LIMIT"))
VIDEO_DEFAULT_DURATION = int(get_required_env_var("VIDEO_DEFAULT_DURATION"))

RENDER_IMAGES_INLINE = get_required_env_var("RENDER_IMAGES_INLINE").lower() in ("true", "1", "yes")
RENDER_VIDEOS_INLINE = get_required_env_var("RENDER_VIDEOS_INLINE").lower() in ("true", "1", "yes")


GCS_TEMPLATE_IMAGE_FOLDER = "template_images/"
ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
VIDEO_FPS = 24


@dataclass
class VideoGenerationInput:
    """Input parameters for video generation."""

    video_query: str
    input_image: GenImage
    image_identifier: str
    duration: int
    scene_number: int
    is_logo_scene: bool = False


async def _monitor_video_operation(
    operation: Any, image_identifier: str, vertex_client: genai.Client
) -> Tuple[Optional[GeneratedVideo], Optional[str]]:
    """Monitors a video generation operation until completion.

    Args:
        operation (Any): The video generation operation to monitor.
        image_identifier (str): An identifier for the image being processed.
        vertex_client (genai.Client): The Vertex AI client.

    Returns:
        A tuple containing the generated video object and an error message.
    """
    log_message(
        f"Submitted video generation request for image {image_identifier}. Operation: {operation.name}",
        Severity.INFO,
    )

    while not operation.done:
        await asyncio.sleep(VIDEO_GENERATION_STATUS_POLL_SECONDS)
        operation = await vertex_client.aio.operations.get(operation)
        log_message(
            f"Operation status for {image_identifier}: {operation.name} - Done: {operation.done}",
            Severity.INFO,
        )

    if operation.error:
        error_message = operation.error.get("message", str(operation.error))
        log_message(
            f"ERROR: Operation for {image_identifier} failed with error: {error_message}",
            Severity.ERROR,
        )
        return None, error_message
    if not (
        operation.result
        and hasattr(operation.result, "generated_videos")
        and operation.result.generated_videos
    ):
        # Safe logging of why the check failed
        op_result = getattr(operation, "result", None)
        has_gen_videos_attr = hasattr(op_result, "generated_videos") if op_result else False
        gen_videos_value = getattr(op_result, "generated_videos", None) if has_gen_videos_attr else None
        
        log_message(
            f"No generated videos found for {image_identifier}. \n"
            f"Operation: {operation}\n"
            f"Result: {op_result}\n"
            f"Has 'generated_videos': {has_gen_videos_attr}\n"
            f"Value of 'generated_videos': {gen_videos_value}",
            Severity.ERROR,
        )
        return None, "No videos found in the response."
    return operation.result.generated_videos[0], None


def _round_to_nearest_veo_duration(duration: int) -> int:
    """Rounds the desired duration to the nearest supported VEO duration.

    Args:
        duration (int): The desired duration of the video in seconds.
    """
    if duration <= 4:
        return 4
    if duration <= 6:
        return 6
    return 8


async def _enhance_prompt_with_llm(
    raw_prompt: str, is_logo_scene: bool, tool_context: ToolContext
) -> str:
    """
    Uses an LLM (Director's Mode) to expand a simple prompt into a detailed visual brief.
    Now includes aspect ratio awareness.
    """
    try:
        utils_agents.agentspace_print(tool_context, "Refining video prompt with Director's Agent...")
        
        # Determine composition based on aspect ratio
        composition_guide = "Wide cinematic landscape composition"
        if "9:16" in VIDEO_DEFAULT_ASPECT_RATIO:
            composition_guide = "Vertical, social-media focused composition (tall frame)"
        elif "1:1" in VIDEO_DEFAULT_ASPECT_RATIO:
            composition_guide = "Square composition, centered subject"

        prompt_context = f"""
Context: The video will be generated by animating a reference image.
Is this is a logo scene: {"YES - This scene contains a corporate logo." if is_logo_scene else "NO."}

REWRITE THIS PROMPT TO BE CINEMATIC AND PHYSICALLY ACCURATE:

User Request: "{raw_prompt}"
"""

        system_instruction = f"""
You are an expert Director of Photography and Visual Effects Supervisor.
Your goal is to rewrite a user's video request into a "Production Ready" description for a video generation model.
        
MANDATES:
    1. VISUALS: Describe lighting (e.g., 'golden hour', 'soft studio', 'volumetric fog'), camera movement (e.g., 'slow dolly in', 'tracking shot'), and texture.
    2. PHYSICS: Explicitly describe how objects move. Mention weight, impact, and friction.
       * AVOID describing complex human coordination (e.g., running up stairs, complex dancing, parkour, tying shoelaces) as models struggle with this.
       * If fast movement is needed, describe it as 'CAPTURED IN SLOW MOTION' to maintain stability.
    3. FRAMING: The video aspect ratio is {VIDEO_DEFAULT_ASPECT_RATIO}. Ensure the shot description fits a {composition_guide}.
    4. REALISM: Use keywords like 'photorealistic', '4k', 'highly detailed', 'raw footage'.
    5. LOGO SAFETY: If the user mentions a logo, ensure you specify it must remain static and undistorted.
        
Output ONLY the refined paragraph. Do not include introductory text.

{prompt_context}
"""

        vertex_client = get_gemini_client()
        response = await vertex_client.aio.models.generate_content(
            model=LLM_GEMINI_MODEL_ADGEN_SUBCALLS,
            contents=system_instruction,
            config=GenerateContentConfig(temperature=0.7),
        )
        
        if response.text:
            log_message(f"Enhanced Prompt: {response.text}", Severity.INFO)
            return response.text
        return raw_prompt
        
    except Exception as e:
        log_message(f"Prompt enhancement failed, using raw prompt. Error: {e}", Severity.WARNING)
        return raw_prompt


def _construct_technical_prompt(enhanced_description: str, is_logo_scene: bool) -> str:
    """
    Wraps the enhanced description in a strict technical container 
    to enforce physics and camera mandates. Now includes Depth/Occlusion logic.
    """
    
    # 1. Cinematography Style
    # Default to Photorealistic, but allow override if user requested a specific style in the raw prompt
    cinematography = (
        "Cinematic footage. 35mm film grain. "
        "Unless a specific style is requested, maintain a Photorealistic 4K style with subtle film grain, chromatic aberration, High Dynamic Range, and natural motion blur. "
    )
    
    # 2. Physics & Motion (The "How")
    physics_engine = (
        "PHYSICS MANDATE: Movement must be weighted and grounded. "
        "Subject must have heavy interaction with the ground. "
        "Feet must plant firmly without sliding. "
        "Muscles must tense and relax naturally. "
        "Gravity is accurate. No floating."
    )

    # 3. Spatial Integrity (NEW: Fixes the 'walking through people' bug)
    spatial_integrity = (
        "SPATIAL INTEGRITY: Respect depth layers. Background objects/people MUST NOT pass through foreground subjects. "
        "Solid objects are impenetrable. Maintain correct occlusion. "
        "The main subject must react to the environment (e.g., swaying slightly with vehicle momentum)."
    )

    # 4. Consistency (The "Identity")
    consistency = (
        "CONSISTENCY: Maintain exact character identity, clothing textures, and facial features "
        "from the input image. Do NOT morph rigid objects (shoes, jewelry, background architecture)."
    )
    
    # 5. Negative Constraints (What NOT to do)
    negative_constraints = (
        "NEGATIVE CONSTRAINTS: No cartoon styles (unless requested). No text overlays. No morphing limbs. "
        "No unnatural stretching. No blurry background warping. No jerky camera movements. "
        "No clipping (objects passing through each other). "
        "No hyper-fast jerky movements. No complex footwork (e.g. running on stairs). No unnatural limb crossings."
    )
    
    # 6. Logo Logic
    logo_instruction = ""
    if is_logo_scene:
        logo_instruction = (
            "LOGO PROTOCOL: The logo in the scene is a rigid, static asset. "
            "It must not warp, bend, or dissolve. It must match the reference pixels exactly."
        )

    # Combine
    final_prompt = f"""
    {cinematography}
    
    {physics_engine}
    
    {spatial_integrity}
    
    {consistency}
    
    {negative_constraints}
    
    {logo_instruction}
    
    SCENE ACTION:
    {enhanced_description}
    """
    
    return final_prompt


# @retry(
#     stop=stop_after_attempt(VIDEO_GENERATION_TENACITY_ATTEMPTS),
#     wait=wait_random_exponential(multiplier=2, min=VIDEO_GENERATION_RETRY_DELAY_SECONDS, max=35),
#     retry=retry_if_exception_type((api_exceptions.ResourceExhausted, api_exceptions.ServiceUnavailable))
# )
async def _generate_single_video(
    video_input: VideoGenerationInput,
    tool_context: ToolContext,
    video_semaphore: asyncio.Semaphore,
) -> Tuple[Optional[Dict[str, str | int]], Optional[Tuple[str, int]]]:
    """Generates a single video from a given image and prompt.

    Args:
        video_input (VideoGenerationInput): The input parameters for video generation.
        tool_context (ToolContext): The context for artifact management.
        video_semaphore (asyncio.Semaphore): The semaphore to control concurrency.

    Returns:
        A tuple containing the video result and an error message.
    """
    best_video: Optional[GeneratedVideo] = None
    error: Optional[str] = None
    best_evaluation: Optional[EvalResult] = None

    video_duration = _round_to_nearest_veo_duration(video_input.duration)

    prompt_to_use = video_input.video_query
    should_run_eval = VIDEO_GENERATION_EVAL_REATTEMPTS > 0
    for i in range(VIDEO_GENERATION_EVAL_REATTEMPTS + 1):
        try:
            log_message(
                f"Generating video attempt {i + 1} of {VIDEO_GENERATION_EVAL_REATTEMPTS+1} eval attempts",
                Severity.INFO,
            )
            
            request = {
                "model": VIDEO_GENERATION_MODEL,
                "source": {
                    "prompt": prompt_to_use,
                    "image": video_input.input_image,
                },
                "config": GenerateVideosConfig(
                    aspect_ratio=VIDEO_DEFAULT_ASPECT_RATIO,
                    generate_audio=False,
                    number_of_videos=1,
                    duration_seconds=video_duration,
                    fps=VIDEO_FPS,
                    person_generation="allow_all",
                    enhance_prompt=True,
                ),
            }

            utils_agents.agentspace_print(
                tool_context,
                f"Generating video clip for {video_input.image_identifier} (Attempt {i+1})...",
            )
            
            video: Optional[GeneratedVideo] = None
            
            for i in range(VIDEO_GENERATION_TENACITY_ATTEMPTS):
                log_message(
                    f"Generating video attempt {i + 1} of {VIDEO_GENERATION_TENACITY_ATTEMPTS+1} tenacity attempts",
                    Severity.INFO,
                )
                
                error = ""
                try:
                    async with video_semaphore:
                        vertex_client = get_gemini_client()
                        operation = await vertex_client.aio.models.generate_videos(**request)

                    video, error = await _monitor_video_operation(
                        operation, video_input.image_identifier, vertex_client
                    )
                    
                    break
                except (api_exceptions.ResourceExhausted) as e:
                    error = str(e)
                    log_message(f"In _call_gemini_image_api received an api_exceptions.ResourceExhausted. Will attempt again: {e}", Severity.WARNING)
                    time.sleep(random.uniform(0, VIDEO_GENERATION_RETRY_DELAY_SECONDS))
                    continue


            if error or not (video and video.video and video.video.video_bytes):
                error = (
                    error
                    or "Generated video (video or video.video or video.video.video_bytes) has no content."
                )
                continue
            else:
                evaluation: EvalResult | None = None
                
                if should_run_eval:
                    evaluation = await evaluate_media(
                        video.video.video_bytes, "video/mp4", video_input.video_query
                    )

                if evaluation and evaluation.decision != "Pass":
                    
                    log_message(
                        f"The generated video did not pass the evaluation. Best Score: {evaluation.averaged_evaluation_score}. Suggestions: {evaluation.improvement_prompt}",
                        Severity.WARNING,
                    )
                    
                    # Update the prompt input for the NEXT loop to include the error context.
                    # This ensures the LLM Director knows specifically what to fix.
                    improvement_prompt = (
                        f"You are tasked with improving a prompt. A video was already generated but it failed the evaluation.\n"
                        f"See next original request and suggested improvement:\n"
                        f"<ORIGINAL-REQUEST>{video_input.video_query}</ORIGINAL-REQUEST>\n"
                        f"<SUGGESTED-IMPROVEMENT>{evaluation.improvement_prompt}</SUGGESTED-IMPROVEMENT>"
                    )
                    
                    prompt_to_use = await _enhance_prompt_with_llm(
                        improvement_prompt, 
                        video_input.is_logo_scene, 
                        tool_context
                    )
                    
                    if not best_evaluation:
                        best_evaluation = evaluation
                        best_video = video
                    elif (
                        evaluation.averaged_evaluation_score
                        > best_evaluation.averaged_evaluation_score
                    ):
                        best_evaluation = evaluation
                        best_video = video

                    continue
                else:
                    best_video = video
                    best_evaluation = evaluation
                    log_message(
                        f"Successfully generated video. Size: {len(video.video.video_bytes)} bytes, Evaluation: {evaluation}",
                        Severity.INFO,
                    )
                    break
        except (api_exceptions.Aborted, ValueError) as e:
            log_message(
                f"Error in _generate_single_video for {video_input.image_identifier}: {e}",
                Severity.ERROR,
            )
            error = str(e)

    if best_video and best_video.video and best_video.video.video_bytes:
        # Microsecond Timestamp + Random Chars
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S_%f")
        random_chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))
        
        filename = f"{ad_generation_constants.SCENE_VIDEO_FILENAME_PREFIX}_{video_input.scene_number}_{timestamp_str}_{random_chars}.mp4"
        generated_media = GeneratedMedia(
            filename=filename,
            mime_type=ad_generation_constants.VIDEO_MIMETYPE,
            media_bytes=best_video.video.video_bytes,
        )

        # 2. Upload to GCS (Standard logic)
        generated_media = await utils_agents.save_to_artifact_and_render_asset(
            asset=generated_media,
            context=tool_context,
            save_in_gcs=True,
            save_in_artifacts=RENDER_VIDEOS_INLINE,
            gcs_folder=utils_agents.get_or_create_unique_session_id(tool_context),
        )

        return_object = {
            "name": filename,
            "duration_seconds": video_duration,
            "scene_description": video_input.video_query,
            "source_image": video_input.image_identifier,
            "scene_number": video_input.scene_number,
            "best_eval": best_evaluation,
        }

        if generated_media and generated_media.gcs_uri:
            return_object["gcs_uri"] = generated_media.gcs_uri

        return return_object, None
    elif error:
        return None, (error, video_input.scene_number)
    else:
        log_message(
            f"ERROR: Unknown error while generating video for {video_input.video_query}",
            Severity.ERROR,
        )
        return None, (
            "Failed to generate video. Unknown error.",
            video_input.scene_number,
        )


# @log_function_call
async def generate_video(
    scene_number: int,
    prompt: str,
    reference_image: str,
    is_logo_scene: bool,
    duration_seconds: int,
    tool_context: ToolContext,
) -> Dict[str, Any]:
    f"""Generates a single video clip based on the provided parameters.

    Args:
        scene_number (int): The sequential number of the scene (starting from 1).
        prompt (str): A detailed video generation prompt for the scene.
            * Should describe the motion and events for each scene.
            * Should only describe a 4 second scene, so describe a quick scene with only one setting.
            * Should be of a single take in a single location. Avoid collages and multiple shots in a single video.
            * Character names won't be understood here, use pronouns + descriptions to detail actions.
            * Be VERY descriptive in what movements and camera angles you expect and what should not move in the scene. Describe who/what is causing the movement.
            * The video generation model will use this image as a starting point. Be clear about how the scene transitions and keep it on theme.
            * Explicitly ground each of your prompts to follow the laws of physics.
        reference_image (str): The exact GCS URI (e.g., "gs://bucket/image.png") of the reference image to use.
        is_logo_scene (bool): True if this scene features the company logo, False otherwise.
        duration_seconds (int): The desired duration of the scene in seconds. Default is {VIDEO_DEFAULT_DURATION}.
        tool_context (ToolContext): The context for artifact management.

    Returns:
        Dict[str, Any]: A dictionary containing the status and details of the video generation process.
    """
    # Create a semaphore for this specific generation task to limit concurrency 
    # within this event loop context.
    video_semaphore = asyncio.Semaphore(VIDEO_GENERATION_CONCURRENCY_LIMIT)

    log_message(f"Starting video generation for scene {scene_number}...", Severity.INFO)
    utils_agents.agentspace_print(
        tool_context, f"Generating video for scene {scene_number}..."
    )

    try:
        # Load reference image
        generated_media: GeneratedMedia | None = await utils_agents.load_resource(
            source_path=reference_image, tool_context=tool_context
        )

        if not generated_media or not generated_media.media_bytes:
            message = f"The provided image for scene number `{scene_number}` does not exist or returned empty. The URI provided was: {reference_image}."
            log_message(message, Severity.ERROR)
            response = {
                "status": "failed",
                "detail": message,
                "scene_number": scene_number,
            }
            log_message(f"[generate_video_response] {response}", Severity.ERROR)
            return response

        # Prompt step 1: Enhance the prompt using LLM (Director's Treatment)
        llm_enhanced_description = await _enhance_prompt_with_llm(
                prompt, 
                is_logo_scene, 
                tool_context
            )

        # Prompt step 2: Wrap in technical mandates
        final_prompt = _construct_technical_prompt(
            llm_enhanced_description, 
            is_logo_scene
        )
        
        log_message(f"Calling VEO with prompt: {final_prompt}", Severity.DEBUG)
            
        video_input = VideoGenerationInput(
            video_query=final_prompt,
            input_image=GenImage(
                image_bytes=generated_media.media_bytes,
                mime_type=generated_media.mime_type,
            ),
            image_identifier=generated_media.filename or "unknown_image",
            duration=duration_seconds,
            is_logo_scene=is_logo_scene,
            scene_number=scene_number,
        )

        result = await _generate_single_video(
            video_input=video_input,
            tool_context=tool_context,
            video_semaphore=video_semaphore,
        )

        video_data, error_info = result

        if video_data:
            # Return response
            response = {
                "status": "success",
                "detail": "Video generated successfully.",
                "generated_video_uri": str(video_data["gcs_uri"]),
            }
            log_message(f"[generate_video_response] {response}", Severity.INFO)
            return response
        elif error_info:
            error_message, _ = error_info

            response = {
                "status": "failed",
                "detail": error_message,
                "scene_number": scene_number,
            }
            log_message(f"[generate_video_response] {response}", Severity.ERROR)
            return response
        else:
            response = {
                "status": "failed",
                "detail": "Unknown error during video generation.",
                "scene_number": scene_number,
            }
            log_message(f"[generate_video_response] {response}", Severity.ERROR)
            return response

    except Exception as e:
        response = {
            "status": "failed",
            "detail": str(e),
            "scene_number": scene_number,
        }
        log_message(f"[generate_video_response] {response}", Severity.ERROR)
        return response
