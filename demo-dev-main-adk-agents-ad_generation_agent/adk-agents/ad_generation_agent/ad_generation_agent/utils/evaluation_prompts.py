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
"""Provides prompts for evaluating generated media with a Unified JSON Schema."""

from typing import Optional
from adk_common.utils.utils_logging import log_function_call

# @log_function_call
def get_image_evaluation_prompt(input_prompt: str, reference_image_descriptions: Optional[list[str]], allow_collage: bool = False) -> str:
    """Generates a detailed prompt for evaluating an AI-generated image.

    Args:
        input_prompt: The original user prompt that was used for image generation.
        reference_image_descriptions: A list of descriptions for each reference image.
        allow_collage: If True, allows collages and storyboards. Defaults to False.

    Returns:
        A formatted string containing the evaluation prompt for the AI model.
    """

    formatted_descriptions = ""
    if reference_image_descriptions:
        formatted_descriptions = "### 1.3. Reference Images"
        formatted_descriptions += "\n\nThe user has provided the following reference images:\n"
        formatted_descriptions += "\n".join([f"* {desc}" for desc in reference_image_descriptions]) 

    criteria_6 = """
    6.  **No Storyboard/Collage:** Is the image a single, cohesive scene? It
        should not be a storyboard, collage, split-screen, or contain multiple
        distinct panels.
    """
    
    if allow_collage:
        criteria_6 = """
    6.  **Collage/Asset Sheet:** If the prompt requests a collage or asset sheet, 
        does the image correctly present multiple distinct elements or panels as requested?
        If the prompt does NOT request a collage, this criterion is N/A (Pass).
    """

    return f"""
    # ROLE: Commercial Art Director & QA Specialist

    You are a meticulous evaluator for an AI image generation system.
    Your task is to approve or reject images for a high-end advertising campaign.

    ## 1. INPUTS

    ### 1.1. Original User Prompt
    ```text
    {input_prompt}
    ```

    ### 1.2. Generated Image
    (The user has provided the image for evaluation.)

    {formatted_descriptions}
    

    ## 2. EVALUATION INSTRUCTIONS

    Evaluate the "Generated Image" against the "Original User Prompt" using the criteria below.
    The final `decision` is "Pass" only if *every single criterion* is met.

    ### 2.1. Forensic Checklist
    1.  **Subject & Brand (subject_and_brand):** * Does the image contain the correct subject/attributes?
        * **Typography:** Is all text spelled 100% correctly? (No gibberish).
    2.  **Physics & Logic (physics_and_logic):** * **Anatomy:** Are hands/fingers correct? (No 6 fingers, claws).
        * **Optical Logic:** Is the perspective and scale correct?
        * **Any biological horror is an automatic FAIL.**
    3.  **Visual Fidelity (visual_fidelity):** * Does the style match the prompt (e.g. Photo vs Sketch)?
        * Is the image free of artifacts/glitches?
    4.  **Consistency:** Does the image match the reference images (Face/Product) exactly?

    ## 3. OUTPUT FORMAT

    Your response **must** be a single, valid JSON object using the exact schema below.

    ### 3.1. JSON Template
    ```json
    {{
        "decision": "Pass", // "Pass" only if ALL criteria are met.
        "score": 95,        // 0-100
        "summary_reason": "Consolidated explanation of failure.",
        "improvement_prompt": "Specific instructions to fix defects (e.g., 'Regenerate hand to have 5 fingers').",
        "defects": [
            {{
                "timestamp": "N/A", 
                "category": "Physics/Anatomy",
                "description": "Hand has 6 fingers."
            }}
        ],
        "scene_feedback": [],
        "category_scores": {{
            "subject_and_brand": "Pass",
            "physics_and_logic": "Pass", 
            "visual_fidelity": "Pass",
            "temporal_flow": "N/A",
            "consistency": "Pass"
        }}
    }}
    ```
    """

# @log_function_call
def get_video_evaluation_prompt(input_prompt: str, reference_image_descriptions: Optional[list[str]]) -> str:
    """Generates a detailed prompt for evaluating an AI-generated video.

    Args:
        input_prompt: The original user prompt that was used for video generation.
        reference_image_descriptions: A list of descriptions for each reference image.

    Returns:
        A formatted string containing the evaluation prompt for the AI model.
    """
    formatted_descriptions = ""
    if reference_image_descriptions:
        formatted_descriptions = "### 1.3. Reference Images"
        formatted_descriptions += "\n\nThe user has provided the following reference images:\n"
        formatted_descriptions += "\n".join([f"* {desc}" for desc in reference_image_descriptions]) 

    return f"""
# ROLE: VFX Supervisor & AI Video QA

You are a meticulous evaluator for an AI video generation system.
Your task is to spot technical artifacts in short video clips.

## 1. INPUTS

### 1.1. Original User Prompt
```text
{input_prompt}
```

### 1.2. Generated Video
(The user has provided the video for evaluation.)

{formatted_descriptions}

## 2. EVALUATION INSTRUCTIONS

Evaluate the video using the "Stare Test" to detect subtle artifacts.

### 2.1. Forensic Checklist
1.  **Subject & Brand (subject_and_brand):** Is the correct subject present?
2.  **Physics & Logic (physics_and_logic):** * **Gravity:** Do objects float or move naturally?
    * **Newton's Law:** Do interactions (steps, impacts) have weight?
    * **Identity:** Does the face morph or change?
3.  **Visual Fidelity (visual_fidelity):** * **Texture Stability:** Do static backgrounds "boil" or shimmer?
    * **Style:** Does it match the requested look?
4.  **Temporal Flow (temporal_flow):** * Does the camera move as requested? (Zoom/Pan).
    * Is the motion smooth?
5.  **Consistency:** Matches reference images exactly.

## 3. OUTPUT FORMAT

Your response **must** be a single, valid JSON object.

### 3.1. JSON Template
```json
{{
    "decision": "Pass", // "Pass" only if ALL criteria are met.
    "score": 60,        // 0-100
    "summary_reason": "Explanation of failure.",
    "improvement_prompt": "Detailed instruction to fix artifacts (e.g. 'Stabilize background texture').",
    "defects": [
        {{
            "timestamp": "00:03", 
            "category": "Visual Fidelity",
            "description": "Background texture is boiling/flickering."
        }}
    ],
    "scene_feedback": [],
    "category_scores": {{
        "subject_and_brand": "Pass",
        "physics_and_logic": "Pass",
        "visual_fidelity": "Fail",
        "temporal_flow": "Pass",
        "consistency": "Pass"
    }}
}}
```
"""


# @log_function_call
def get_final_ad_evaluation_prompt(input_prompt: str, reference_image_descriptions: Optional[list[str]]) -> str:
    """Generates a detailed prompt for evaluating a final consolidated video ad.
    
    This prompt is specifically designed for ads with multiple scenes, transitions,
    voiceover, and background music.
    
    Args:
        input_prompt: The original user prompt that was used for video generation.
        reference_image_descriptions: A list of descriptions for each reference image.

    Returns:
        A formatted string containing the evaluation prompt for the AI model.
    """
    formatted_descriptions = ""
    if reference_image_descriptions:
        formatted_descriptions = "### 1.3. Reference Images (CRITICAL)"
        formatted_descriptions += "\n\nThe user has provided the following reference images. Compare the LOGO against these:\n"
        formatted_descriptions += "\n".join([f"* {desc}" for desc in reference_image_descriptions]) 

    return f"""
    # ROLE: Lead Creative Technologist & VFX Supervisor

    You are the final gatekeeper for a high-budget AI video campaign. 
    Your job is to identify "AI Tells" (physics/brand errors) and creative flaws.

    ## 1. INPUTS

    ### 1.1. Creative Brief / Intent
    ```text
    {input_prompt}
    ```

    ### 1.2. Generated Video Ad
    (The user has provided the final video file for evaluation.)

    {formatted_descriptions}

    ## 2. EVALUATION FRAMEWORK

    ### PASS 1: The "Reality Check" (Physics & Logic) -> [physics_and_logic]
    1.  **Object Permanence:** Do objects disappear/morph?
    2.  **Newton's Law:** Do fluids (splashes) and impacts behave realistically?
    3.  **Scale & Optical Logic:** Do objects fit the scene size? (No "Giant Shoes").
    4.  **Lighting (Sticker Effect):** Do objects cast proper contact shadows?

    ### PASS 2: Brand & Subject (Brand Integrity) -> [subject_and_brand]
    5.  **Forensic Brand Match:** Compare the video logo to the Reference Images. 
        * **Fail Condition:** If the logo is a generic "redrawn" approximation, it is a FAIL. It must match exactly.

    ### PASS 3: Creative Quality -> [temporal_flow] & [visual_fidelity]
    6.  **Pacing:** Is the video boring (dead air) or confusing (hyper-fast cuts)?
    7.  **Narrative:** Does the sequence make sense?

    ### PASS 4: Scene-Level Analysis -> [scene_feedback]
    8.  **Granular Review:** Evaluate each distinct scene/shot individually.
        *   **Pass:** Scene is high quality and consistent.
        *   **Fix:** Scene has minor defects (e.g., glitchy texture, minor continuity error) but is usable if regenerated/fixed.
        *   **Fail:** Scene is fundamentally broken (wrong subject, biological horror) or breaks continuity ruinously.
    9.  **Continuity Check:** If you demand a "Fix" for Scene 2, consider if it impacts Scene 1 or 3.

    ## 3. FEEDBACK INSTRUCTIONS

    If you find a defect, your `improvement_prompt` must be **technically actionable**.
    * *Good:* "Brand error at 0:09: The AI generated a generic 'V' logo. Composite the exact logo file provided in references."
    
    For `scene_feedback`, provide specific instructions for EACH scene.

    ## 4. OUTPUT FORMAT

    Your response **must** be a single, valid JSON object.

    ### 4.1. JSON Template
    ```json
    {{
        "decision": "Pass", 
        "score": 45, 
        "summary_reason": "Brand integrity failure in Scene 2.",
        "improvement_prompt": "Regenerate what seems to be Scene 2 (at 0:09), replace the generated logo with the correct asset.",
        "defects": [
            {{
                "timestamp": "00:09",
                "category": "Brand Integrity",
                "description": "Logo is a generic approximation; does not match reference."
            }}
        ],
        "scene_feedback": [
            {{
                "timestamp": "00:00-00:04", 
                "decision": "Pass",
                "description": "Opening shot establishes location effectively.",
                "improvement_suggestion": "",
                "impact_analysis": ""
            }},
            {{
                "timestamp": "00:04-00:08",
                "decision": "Fix",
                "description": "Logo on shirt is blurry.",
                "improvement_suggestion": "Composite high-res logo onto shirt.",
                "impact_analysis": "Ensure lighting matches Scene 1."
            }}
        ],
        "category_scores": {{
            "subject_and_brand": "Fail",
            "physics_and_logic": "Pass",
            "visual_fidelity": "Pass",
            "temporal_flow": "Pass",
            "consistency": "Pass"
        }}
    }}
    ```
    """