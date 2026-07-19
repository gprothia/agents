"""
Chain Veo 3.1 videos via Vertex AI.

Generates a base clip, then repeatedly extends it (~7s per hop, up to 20 hops,
~148s total ceiling), polling each long-running operation to completion before
starting the next hop. Output lands in a Cloud Storage bucket.

Setup:
    pip install google-genai
    gcloud auth application-default login      # sets up ADC credentials
    # Ensure the Vertex AI API is enabled on your project and you have a GCS bucket.

Required env / config:
    PROJECT_ID   your Google Cloud project id
    LOCATION     a region where Veo is available, e.g. "us-central1"
    OUTPUT_GCS   gs:// bucket path where results are written

Notes:
  - Auth uses Application Default Credentials (ADC). The account/service account
    needs the Vertex AI User role (roles/aiplatform.user) and write access to
    the output bucket.
  - Each generation is an async "long running operation" you must poll.
  - Vertex writes the MP4 to your GCS bucket; this script prints the final URI.
  - Model IDs and some config field names change between preview/GA releases.
    Verify MODEL_ID and the extend field against the current Vertex AI Veo docs
    if a call is rejected.
"""

import os
import time
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Config — edit these
# ---------------------------------------------------------------------------
PROJECT_ID = os.environ.get("PROJECT_ID", "bold-kit-384717")
LOCATION = os.environ.get("LOCATION", "us-central1")
OUTPUT_GCS = os.environ.get("OUTPUT_GCS", "gs://gap-1000")

MODEL_ID = "veo-3.1-generate-001"   # or the current GA id, e.g. veo-3.1-generate-001
ASPECT_RATIO = "16:9"                   # "16:9" or "9:16"
RESOLUTION = "720p"                     # extension hops are typically limited to 720p

BASE_PROMPT = (
    "A slow dolly shot past a neon-lit ramen stand at night, light rain, "
    "shallow depth of field, warm amber glow, cinematic."
)

# One prompt per extension hop. Write each as a "next shot" that continues the
# motion — name what stays the same (subject, lighting, palette), avoid hard cuts.
EXTENSION_PROMPTS = [
    "The camera keeps dollying forward at the same speed, same rain and amber "
    "glow, a chef leans out from behind the counter.",
    "The camera holds as the chef slides a steaming bowl across the counter, "
    "same warm amber light, same gentle rain.",
]

POLL_SECONDS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def wait_for(client, operation, label):
    """Poll a long-running video operation until it finishes."""
    print(f"[{label}] generating", end="", flush=True)
    while not operation.done:
        time.sleep(POLL_SECONDS)
        operation = client.operations.get(operation)
        print(".", end="", flush=True)
    print(" done.")

    if getattr(operation, "error", None):
        raise RuntimeError(f"[{label}] generation failed: {operation.error}")

    videos = operation.response.generated_videos
    if not videos:
        raise RuntimeError(f"[{label}] no video returned")
    return videos[0].video


def main():
    # Vertex AI client: uses ADC + project/location instead of an API key.
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION,
    )

    # --- 1) Base clip -------------------------------------------------------
    op = client.models.generate_videos(
        model=MODEL_ID,
        prompt=BASE_PROMPT,
        config=types.GenerateVideosConfig(
            aspect_ratio=ASPECT_RATIO,
            resolution=RESOLUTION,
            output_gcs_uri=OUTPUT_GCS,   # Vertex writes results to GCS
        ),
    )
    current_video = wait_for(client, op, "base")

    # --- 2) Extension hops --------------------------------------------------
    hops = min(len(EXTENSION_PROMPTS), 20)  # hard ceiling is 20 hops
    for i, prompt in enumerate(EXTENSION_PROMPTS[:hops], start=1):
        # The extend call feeds the previous result back in as `video`.
        # If your SDK version rejects this field name, check the current
        # Vertex AI Veo docs — the extend parameter has moved between releases.
        op = client.models.generate_videos(
            model=MODEL_ID,
            prompt=prompt,
            video=current_video,
            config=types.GenerateVideosConfig(
                aspect_ratio=ASPECT_RATIO,
                resolution=RESOLUTION,
                output_gcs_uri=OUTPUT_GCS,
            ),
        )
        current_video = wait_for(client, op, f"hop {i}/{hops}")

    # --- 3) Report the final result location --------------------------------
    uri = getattr(current_video, "uri", None) or OUTPUT_GCS
    print(f"\nFinal video written to: {uri}")
    print(f"Approx length: 8 + {hops} x 7 = {8 + hops * 7}s")


if __name__ == "__main__":
    main()