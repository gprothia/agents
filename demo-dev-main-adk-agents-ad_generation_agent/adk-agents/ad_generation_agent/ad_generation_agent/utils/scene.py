from typing import List, Optional

from ad_generation_agent.utils.eval_result import EvalResult
from google.adk.tools.tool_context import ToolContext
from pydantic import BaseModel


class Scene(BaseModel):
    scene_number: int
    is_logo_scene: bool = False
    duration_seconds: int = 4
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None
    reference_images: Optional[List[str]] = None
    scene_image: Optional[str] = None
    scene_video: Optional[str] = None
    best_image_eval: Optional[EvalResult] = None
    best_video_eval: Optional[EvalResult] = None