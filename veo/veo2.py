import base64


def b64decode(b64_encoded_string: str) -> bytes:
  return base64.b64decode(b64_encoded_string.encode('utf-8'))


import time
import sys
from google import genai
from google.genai import types


client = genai.Client(
    project="bold-kit-384717",
    location="us-central1",
)

source = types.GenerateVideosSource(
    prompt="""A futuristic vehicle powered by a miniature, contained singularity, leaving trails of distorted space and shimmering light as it speeds through a desert landscape at sunset. Style: Sci-Fi Concept Art, Motion Blur, Lens Flare, Warm Sunset Palette against Cool Tech Tones.""",
)

config = types.GenerateVideosConfig(
    aspect_ratio="16:9",
    number_of_videos=4,
    duration_seconds=8,
    person_generation="dont_allow",
    resolution="720p",
    seed=50,
    enhance_prompt=True,
)

# Generate the video generation request
operation = client.models.generate_videos(
    model="veo-3.1-generate-001", source=source, config=config
)

# Waiting for the video(s) to be generated
while not operation.done:
    print("Video has not been generated yet. Check again in 10 seconds...")
    time.sleep(10)
    operation = client.operations.get(operation)

response = operation.result
if not response:
    print("Error occurred while generating video.")
    sys.exit(1)

generated_videos = response.generated_videos
if not generated_videos:
    print("No videos were generated.")
    sys.exit(1)

print(f"Generated {len(generated_videos)} video(s).")
for generated_video in generated_videos:
    if generated_video.video:
        generated_video.video.show()

for i, generated_video in enumerate(generated_videos):
  if generated_video.video:
    filename = f"output_video_{i+1}.mp4"
    generated_video.video.save(filename)
    print(f"Saved video to {filename}")


