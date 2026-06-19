import vertexai
from vertexai.preview.vision_models import VideoGenerationModel

vertexai.init(project="your-project", location="us-central1")
model = VideoGenerationModel.from_pretrained("veo-3-ultra-generate-001")

operation = model.generate_video(
    prompt="A professional product demo video showing a smartphone...",
    generate_audio=True,
    aspect_ratio="16:9"
)
