# GE Activation Agent — POC

A working proof of concept of the **GE Activation Agent**: an ADK agent that guides a
customer through Gemini Enterprise setup like a consultant — asking a few questions,
recommending a configuration with pros and watch-outs (grounded in real Google docs),
and saving the decision to a **plan sheet** that a second **deployment agent** reads and
turns into **Terraform**.

This POC covers three setup areas (Jira comes later):
- **Infrastructure** — region / data residency + encryption (CMEK vs Google-managed). *(one-way; do first)*
- **App setup** — who the first app is for, and what it does.
- **Gmail connector** — guided, domain-wide (all users), messages + attachments, read **and** actions (send/reply/draft/download).

All follow the same three beats: **Discovery → Recommendation (pros/cons) → Decision saved.**

### The guided Gmail flow
The Gmail connector is a *consultative* flow: the agent reads the saved infra decision
(`read_plan`) so region/encryption stay consistent, grounds itself in the Gmail playbook,
asks what to index and whether to enable actions, then **walks the admin prerequisites one
by one and explains why each matters** — Workspace-only (no personal @gmail.com), Smart
features on, OAuth app allowlisted, identity provider configured, and the one-time OAuth
consent for actions. It only saves the decision after the user approves *and* confirms the
prerequisites. The deploy agent then emits a real `google_discovery_engine_data_connector`
(`data_source = "google_mail"`) plus a `google_discovery_engine_acl_config` (GSUITE) so
users only see mail they can already access.

---

## What's real vs. simulated

| Real | Simulated (for the POC) |
|---|---|
| ADK agent + Gemini function-calling | — |
| Grounding & citations (local playbooks) | full doc corpus (here: 3 files) |
| Version-controlled plan sheet (`plan.xlsx`) | — |
| Terraform using real `google_discovery_engine_*` resources | placeholder values (PROJECT_ID, kms_key) |
| Two-agent hand-off (planning → deployment) | `terraform plan` dry-run only; nothing is applied |

---

## Layout

```
ge_activation_poc/
  grounding/            # local grounding playbooks (the agent's knowledge)
    app_setup.md  region.md  encryption_cmek.md  connector_gmail.md
  ge_agent/
    agent.py            # ADK planning agent (adk web / adk run entrypoint)
    tools.py            # ADK tool functions
    playbooks.py        # load + search grounding
    recommend.py        # answers -> grounded recommendation (pros/cons)
    plan_sheet.py       # read/write plan.xlsx  (hand-off contract)
    a2ui.py             # build A2UI surfaces (discovery / recommendation / decision)
    terraform_gen.py    # decision -> real GE Terraform
  deploy_agent.py       # reads plan.xlsx -> generates TF -> validate/plan -> status back
  run_simulated.py      # full pipeline WITHOUT the LLM (run this first)
  web/a2ui_demo.html    # tiny A2UI viewer for the recommendation card
  plan.xlsx             # created on first run
  terraform_out/        # generated .tf files
```

## Requirements
```
pip install -r requirements.txt      # google-adk, openpyxl, python-dotenv
```

## Run it

**1) See the whole pipeline immediately (no API key needed):**
```
python run_simulated.py      # discovery -> recommendation -> plan.xlsx  (+ prints an A2UI surface)
python deploy_agent.py       # plan.xlsx -> terraform_out/*.tf  -> updates status in plan.xlsx
```
Open `plan.xlsx` to see the decisions, and `terraform_out/` for the generated Terraform.

**2) The live agent demo (needs a Gemini API key):**
```
cp .env.example .env         # add GOOGLE_API_KEY
adk web                      # then pick "ge_agent" in the browser UI
# or:  adk run ge_agent
```
Say: *"Help me set up Gemini Enterprise."* The agent runs discovery, recommends with
pros/cons (citing the playbook), asks you to approve, and saves each decision to `plan.xlsx`.
Then run `python deploy_agent.py` to deploy from the sheet.

**3) A2UI card:** open `web/a2ui_demo.html`, paste the JSONL printed by `run_simulated.py`
(or returned by the `build_recommendation_ui` tool), and click **Render**.

## Notes on A2UI
The agent emits A2UI surface JSON (`ge_agent/a2ui.py`) — the declarative
surfaceUpdate / dataModelUpdate / beginRendering shape. `web/a2ui_demo.html` renders the
subset used here. In phase 1 these surfaces are sent over A2A to a production A2UI client
(or the ADK web renderer with a custom component catalogue) instead of the static viewer.

## Turning the dry-run into a real deploy
In `deploy_agent.py`, set `RUN_APPLY = True` **only** against a throwaway sandbox GCP
project you own (with billing + the Discovery Engine API enabled). Fill the placeholder
variables (project_id, kms_key, data_store_ids) first. Keep it off for the leadership demo.

## API surface used (verified against current Google docs)
- Provisioning: **Discovery Engine API** (`discoveryengine.googleapis.com`)
- App/engine: `google_discovery_engine_search_engine` (app_type = APP_TYPE_INTRANET)
- Encryption: `google_discovery_engine_cmek_config` (UpdateCmekConfig / cmekConfigs)
- Data store / connector (Jira, later): `google_discovery_engine_data_store` / `_data_connector`
- Licenses (later): `userStores…batchUpdateUserLicenses`

*Product/API facts reflect Google Cloud documentation as of September 2026; re-validate at build time.*
