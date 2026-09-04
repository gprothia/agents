# Product Catalog Ad Generation Agent

## Description

This project is a Personalized Ad Generation Assistant that helps marketing teams generate short-form video ads grounded in their product catalog. The agent pulls product metadata from a catalog (e.g., BigQuery), validates demographic targeting, and generates a video using product imagery and corporate branding standards. A human-in-the-loop feedback mechanism allows for iterative refinement of the generated ad.

The agent is defined in `ad_generation_agent/agent.py` and uses the `gemini-2.5-pro` model. It orchestrates a multi-step workflow that includes product selection, storyline generation, asset sheet creation, image and video generation, audio synthesis, and final ad assembly.

## Project Directory Structure

```
ad_generation_agent/
├── ad_generation_agent/
│   ├── agent.py                  # Main agent that orchestrates the ad generation workflow.
│   ├── func_tools/
│   │   ├── select_product.py     # Selects a product from BigQuery based on user input.
│   │   ├── generate_storyline.py # Generates the storyline and visual style guide.
│   │   ├── generate_asset_sheet.py # Generates the asset sheet with scene details.
│   │   ├── generate_image.py     # Generates images based on the storyline and visual style guide.
│   │   ├── generate_video.py     # Generates video clips from images.
│   │   ├── generate_audio.py     # Generates background audio and voiceovers.
│   │   └── combine_video.py      # Combines video clips, audio, and voiceovers into a final video.
│   └── utils/
│       ├── creative.py           # Defines the Creative data model and state management.
│       ├── scene.py              # Defines the Scene data model.
│       ├── evaluate_media.py     # Evaluates the generated media to ensure quality.
│       ├── evaluation_prompts.py # Contains prompts used for media evaluation.
│       ├── storytelling.py       # Contains prompts used for generating the storyline.
│       ├── gemini_utils.py       # Helper functions for interacting with Gemini models.
│       └── ad_generation_constants.py # Constants used throughout the agent.
├── scripts/
│   ├── 01-setup-gcp.sh           # Enables required Google Cloud APIs.
│   ├── 02-deploy-gcs-and-bq.sh   # Deploys GCS, BigQuery, and populates with product data.
│   ├── populate_bq_with_gemini.py # Script to populate BigQuery with product metadata using Gemini.
│   ├── generate_sample_data.py   # Generates sample product images and a logo based on configuration.
│   └── add_padding.py            # Adds whitespace padding to images to fix aspect ratio.
├── static/
│   ├── uploads/                  # Contains all the static assets to be uploaded to GCS.
│   └── generated/                # Local directory where generated videos are saved.
├── pyproject.toml                # Project configuration and dependencies.
└── README.md                     # This file.
```

## Prerequisites

Before deploying, ensure you have:
1.  **Google Cloud CLI (`gcloud`)** installed and authenticated.
2.  **Poetry** installed for dependency management.
3.  **Python 3.10+** installed.

## Setup & Deployment

The `scripts/` directory inside `ad_generation_agent/` contains automation scripts for setting up the Google Cloud infrastructure.

### 1. Set up Local Environment

Run the following commands from the root `adk-agents` directory:

```bash
poetry config virtualenvs.in-project true # Optional
poetry install
eval $(poetry env activate) # Optional
gcloud config configurations activate <your-config>
gcloud auth application-default login
```

### 2. Set up Cloud Infrastructure

These scripts should be run from the `ad_generation_agent` subdirectory:

#### Enable APIs (`01-setup-gcp.sh`)

This script enables the required Google Cloud APIs for the project.

```bash
cd ad_generation_agent
bash scripts/01-setup-gcp.sh
cd ..
```

#### Deploy GCS & BigQuery (`02-deploy-gcs-and-bq.sh`)

This script provisions the GCS bucket, uploads static assets, creates the BigQuery dataset/table, and populates it with product data.

```bash
cd ad_generation_agent
bash scripts/02-deploy-gcs-and-bq.sh
cd ..
```

### 3. (Optional) Generate Sample Data

If you do not have your own product images, use this script to generate sample data using Gemini.

```bash
cd ad_generation_agent
python scripts/generate_sample_data.py
cd ..
```

## Usage

### Run Locally

To test the agent locally, run the following command from the `adk-agents` directory:

```bash
adk web
```

### Agent Workflow

The main agent orchestrates the entire ad generation workflow:

1.  **Product Selection & Demographic Targeting**: Fetches product details from BigQuery and validates suitability for the target audience.
2.  **Storyline Generation**: Creates a narrative and visual style guide grounded in the product and branding.
3.  **Asset Sheet Generation**: Produces a structured asset sheet detailing each scene.
4.  **Image Generation**: Generates consistent images for each scene based on the asset sheet.
5.  **Video Generation**: Converts images into video clips using the Veo model.
6.  **Audio & Voiceover Generation**: Creates a background track and voiceover using Lyria and Gemini TTS.
7.  **Final Assembly**: Combines all assets into a final video ad.

### Bring Your Own Asset Sheet

You can provide a GCS URI to an existing asset sheet to skip the product selection and storyline generation steps. The agent will use the provided asset sheet to generate the remaining assets.

### Bring Your Own Product Photo

You can provide a direct GCS URI for a product photo to bypass the BigQuery lookup.

## Deployment

We use a Python-based deployment script (`deploy.py`) that leverages the Vertex AI Reasoning Engine (Agent Engine). This allows for version-controlled, configuration-driven deployments.

### 1. Configuration

Deployment configurations are stored as JSON files (e.g., `deployment_scripts/nrf_marketing-*.json`) that control both the deployment process and the agent's runtime behavior. 

### Top-Level Deployment Settings

| Field | Description | Example |
| :--- | :--- | :--- |
| `agent` | Identifier for the agent type (do not change). | `"ad_generation_agent"` |
| `agent_module` | Import path for the agent code. | `"ad_generation_agent.agent"` |
| `agent_variable` | Name of the agent instance variable. | `"root_agent"` |
| `whl_file_path` | Path to the built python package (.whl). | `"dist/content_gen_agent-3.20260119.1-py3-none-any.whl"` |
| `deployment_environment` | Target environment label. | `"prod"` or `"staging"` |
| `gcs_bucket_deployment_location` | Region for the deployment bucket. | `"US"` |
| `agent_display_name` | Name shown in Vertex AI Console. | `"Ad Generation Agent [3.20260119.1]"` |
| `agent_engine_id_to_update` | Reasoning Engine ID to overwrite. Leave empty string `""` to create new. | `"1757962962162679808"` |
| `google_cloud_reasoning_engine_location` | Region for Agnet Engine execution. | `"us-central1"` |

### Runtime Environment Variables (`env_vars`)

These are injected into the agent at runtime.

#### Core Infrastructure
*   `GOOGLE_CLOUD_PROJECT`: GCP Project ID.
*   `GOOGLE_CLOUD_LOCATION`: Default location for resources (often `"global"`).
*   `MODELS_CLOUD_LOCATION`: Location where models are hosted.
*   `GOOGLE_CLOUD_BUCKET_ARTIFACTS`: GCS bucket for storing generated images/videos.
*   `AGENT_VERSION`: Explicit version string for runtime verification.

#### Model Selection
*   `LLM_GEMINI_MODEL_ADGEN_ROOT`: Main orchestration model (e.g., `gemini-2.5-flash`).
*   `LLM_GEMINI_MODEL_ADGEN_SUBCALLS`: Model for smaller, specific tool calls.
*   `LLM_GEMINI_MODEL_EVALUATION`: Model used for checking quality/safety.
*   `IMAGE_GENERATION_MODEL`: e.g., `imagen-4.0-ultra-generate-001`.
*   `VIDEO_GENERATION_MODEL`: e.g., `veo-3.1-generate-preview`.
*   `AUDIO_LYRIA_GENERATION_MODEL`: e.g., `lyria-002`.
*   `AUDIO_TTS_GENERATION_MODEL`: e.g., `gemini-2.5-pro-tts`.
*   `STORYBOARD_GENERATION_MODEL`: e.g., `gemini-3-pro-image-preview`.

#### Generation Parameters
*   `IMAGE_DEFAULT_ASPECT_RATIO`: e.g., `"9:16"`.
*   `VIDEO_DEFAULT_DURATION`: Duration in seconds (e.g., `"4"`).
*   `VIDEO_DEFAULT_RESOLUTION`: e.g., `"1080p"`.
*   `MAX_NUMBER_OF_IMAGES`: Hard limit per generation turn.

#### Resilience & Performance
*   `*_CONCURRENCY_LIMIT`: Max parallel requests for Image/Video generation.
*   `*_TENACITY_ATTEMPTS`: Number of retries for failed generations.
*   `*_RETRY_DELAY_SECONDS`: Wait time between retries.
*   `VIDEO_GENERATION_STATUS_POLL_SECONDS`: Polling interval for long-running video tasks.

#### UX & Demo Settings
*   `DEMO_COMPANY_NAME`: Name of the fictitious brand (e.g., `"Verana"`).
*   `RENDER_IMAGES_INLINE`: `1` (true) or `0` (false) to show images in chat.
*   `RENDER_VIDEOS_INLINE`: `1` (true) or `0` (false) to show videos in chat.
*   `BACKUP_CATALOG_IMAGE_URL`: Fallback image if product lookup fails.


Example Config (`deployment_scripts/nrf_marketing-1445-3.20260119.1-prod.json`):
```json
{
  "agent": "ad_generation_agent",
  "deployment_environment": "prod",
  "env_vars": {
    "GOOGLE_CLOUD_PROJECT": "gemini-enterprise-tahoe-1445",
    "AGENT_VERSION": "3.20260119.1"
    ...
  }
}
```

### 2. Build the Package

Before deploying, you must build the python package to generate the `.whl` file referenced in the config:

```bash
poetry build
```

### 3. Deploy

Run the `deploy.py` script from the `adk-agents` root directory with the desired configuration file. **Note:** You must run this using `poetry run` to ensure all dependencies (like `google-cloud-aiplatform`) are available.

```bash
poetry run python deploy.py --config_file deployment_scripts/nrf_marketing-1445-3.20260119.1-prod.json
```

#### Troubleshooting Deployment

If you encounter a **500 Internal Server Error** regarding `storage.objects.get` permissions:
*   **Cause**: The Vertex AI Service Agent does not have permission to read the uploaded artifacts from the deployment bucket.
*   **Fix**: Grant `roles/storage.objectViewer` to the service account listed in the error message.

```bash
gcloud storage buckets add-iam-policy-binding gs://<deployment-bucket-name> \
  --member=serviceAccount:<service-account-email> \
  --role=roles/storage.objectViewer
```

### 4. Updating an Existing Agent

To update an existing agent, ensure the `agent_engine_id_to_update` field is set in your JSON config. If it is empty (`""`), a **new** agent will be created.

## Local Development

To run the agent locally for testing:

1.  Activate your poetry environment: `poetry shell`
2.  Run the ADK web server: `adk web`

## Key Features

*   **Strict URL Handling**: The agent is instructed to pass through URLs from tools exactly as returned, without hallucinating content or attempting to "fix" `gs://` paths itself (the tools handle this).
*   **Codebase Safety**: The project includes safety scans to prevent unauthorized monkey-patching of core libraries.
*   **Artifacts**: Generated assets (Videos, Images) are stored in GCS and referenced by signed HTTPs URLs.

## License

This project is licensed under the Apache License, Version 2.0.
