"""Generate Terraform for a saved decision using the real Gemini Enterprise resources.

Resources used (hashicorp/google provider 7.7.0+):
  - google_discovery_engine_search_engine   (an "app"/engine, app_type=APP_TYPE_INTRANET)
  - google_discovery_engine_cmek_config     (customer-managed encryption)
The emitted values are POC placeholders (PROJECT_ID etc.); the structure is production-shaped.
"""
from __future__ import annotations
import os
import re

PROVIDER_HEADER = '''terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.7.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  user_project_override = true
  billing_project       = var.project_id
}

variable "project_id" { type = string }
'''


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", (s or "resource").lower()).strip("_") or "resource"


def _app_tf(dec: dict) -> str:
    v = dec.get("value", {})
    name = _slug(v.get("app_name", "employee_assistant"))
    return f'''
# Decision {dec.get("id")}: {dec.get("title")}
# Source: {dec.get("source_url")}
resource "google_discovery_engine_search_engine" "{name}" {{
  engine_id         = "{name}"
  collection_id     = "{v.get('collection_id', 'default_collection')}"
  location          = var.location
  display_name      = "{v.get('app_name', 'Employee Assistant')}"
  industry_vertical = "GENERIC"
  data_store_ids    = var.data_store_ids  # attach your data stores

  search_engine_config {{
    search_tier = "SEARCH_TIER_ENTERPRISE"
  }}
  # app_type resolves to APP_TYPE_INTRANET for Gemini Enterprise
  common_config {{
    company_name = "{v.get('app_name', 'Employee Assistant')}"
  }}
}}

variable "location"       {{ type = string, default = "global" }}
variable "data_store_ids" {{ type = list(string), default = [] }}
'''


def _cmek_tf(dec: dict) -> str:
    v = dec.get("value", {})
    if v.get("encryption") != "cmek":
        return (f'\n# Decision {dec.get("id")}: {dec.get("title")}\n'
                f'# Google-managed encryption (GMEK) selected \u2014 no CMEK resource required.\n'
                f'# Location: {v.get("location", "global")}\n')
    return f'''
# Decision {dec.get("id")}: {dec.get("title")}
# Source: {dec.get("source_url")}
# One-way: a registered CMEK key cannot be swapped; register BEFORE creating data connectors.
resource "google_discovery_engine_cmek_config" "default" {{
  cmek_config_id = "{v.get('cmek_config_id', 'default')}"
  location       = "{v.get('location', 'eu')}"
  kms_key        = var.kms_key
  set_default    = true
}}

variable "kms_key" {{
  type        = string
  description = "Full Cloud KMS key resource name (multi-region symmetric key)."
  default     = "{v.get('kms_key', '')}"
}}
'''


def generate_terraform(decision: dict, out_dir: str) -> str:
    """Write a .tf file for a decision and return its path."""
    os.makedirs(out_dir, exist_ok=True)
    area = decision.get("area")
    if area == "app":
        body = _app_tf(decision)
    elif area == "infra":
        body = _cmek_tf(decision)
    else:
        body = f'\n# Decision {decision.get("id")}: no generator for area "{area}" yet.\n'
    fname = f'{decision.get("id", "decision")}_{area}.tf'
    path = os.path.join(out_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(PROVIDER_HEADER + "\n" + body)
    return path
