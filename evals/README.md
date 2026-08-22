# Agent Evaluation Framework (ADK & Vertex AI GEAP)

This directory provides evaluation suites, reference benchmarks, interactive notebooks, and configuration datasets for evaluating conversational AI agents. It covers two complementary evaluation paradigms:

1. **Local Agent Evaluation with ADK CLI (`adk eval`)**: Rapid local benchmarking of tool call trajectories, response matching, LLM-as-a-judge scoring, rubrics, and automated multi-turn user simulation.
2. **Enterprise Agent Evaluation with Vertex AI / GEAP**: Scalable cloud evaluation using synthetic scenario generation, custom computation/LLM metrics, loss clustering analysis, and managed evaluation runs for deployed agents.

---

## Directory Structure

```
evals/
├── README.md                                          # This documentation
├── Lab_A_evaluate_adk_agents.ipynb                   # Interactive Lab A: Local ADK evaluations
├── Lab_B_eval_geap.ipynb                             # Interactive Lab B: Vertex AI / GEAP evaluations
├── travel_data.py                                    # Mock flight and hotel database for travel agent evals
└── customer_service_agent/                           # ADK Customer Service Agent & Eval Assets
    ├── __init__.py
    ├── agent.py                                      # Cymbal Home & Garden retail agent implementation
    ├── cs_eval_set.evalset.json                      # Golden multi-case evaluation dataset
    ├── cs_refund.evalset.json                        # Trajectory-focused evalset for refund workflows
    ├── cs_user_sim.evalset.json                      # User simulation evalset generated from scenarios
    ├── conversation_scenarios.json                   # Scenario definitions for simulated user testing
    ├── session_input.json                            # Session context configuration
    ├── eval_config.reference.json                    # Config: exact tool trajectory & response match
    ├── eval_config.judge.json                        # Config: LLM-as-a-judge response matching
    ├── eval_config.rubric.json                       # Config: custom rubric grading (conciseness, completeness)
    ├── eval_config_with_metrics.json                 # Config: user simulation with safety & hallucination criteria
    └── eval_config_without_metrics.json              # Config: dry-run user simulation (no metrics)
```

---

## Key Files & Assets

### Interactive Notebooks
* [`Lab_A_evaluate_adk_agents.ipynb`](file:///Users/prothiag/code/agents/evals/Lab_A_evaluate_adk_agents.ipynb) — Step-by-step walkthrough covering local ADK agent development, reference metrics, LLM judges, rubrics, user simulation, and iterative instruction optimization.
* [`Lab_B_eval_geap.ipynb`](file:///Users/prothiag/code/agents/evals/Lab_B_eval_geap.ipynb) — Advanced evaluation with Gemini Enterprise Agent Platform (GEAP) / Vertex AI Gen AI Evaluation, custom computation and LLM metrics, loss clustering, and managed evaluation of deployed reasoning engines.

### Agent & Evaluation Data
* [`customer_service_agent/agent.py`](file:///Users/prothiag/code/agents/evals/customer_service_agent/agent.py) — ADK Agent definition (`customer_service_agent`) equipped with tools: [`get_purchase_history`](file:///Users/prothiag/code/agents/evals/customer_service_agent/agent.py#L28-L38), [`issue_refund`](file:///Users/prothiag/code/agents/evals/customer_service_agent/agent.py#L40-L71), and [`lookup_product_info`](file:///Users/prothiag/code/agents/evals/customer_service_agent/agent.py#L73-L106).
* [`travel_data.py`](file:///Users/prothiag/code/agents/evals/travel_data.py) — Mock dataset containing `FLIGHT_DB` and `HOTEL_DB` used in travel concierge evaluation scenarios.

### Evaluation Sets (`.evalset.json`)
* [`customer_service_agent/cs_eval_set.evalset.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/cs_eval_set.evalset.json) — Multi-turn test cases covering customer purchase history, product lookup, and order status verification.
* [`customer_service_agent/cs_refund.evalset.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/cs_refund.evalset.json) — Target test cases validating proper tool invocation order (e.g. asking for reason prior to issuing refund).
* [`customer_service_agent/cs_user_sim.evalset.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/cs_user_sim.evalset.json) — Generated evaluation set pairing starting prompts with goal-driven conversation plans.

### Evaluation Configurations (`eval_config*.json`)
* [`customer_service_agent/eval_config.reference.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/eval_config.reference.json) — Evaluates `tool_trajectory_avg_score` and `response_match_score`.
* [`customer_service_agent/eval_config.judge.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/eval_config.judge.json) — Configures `final_response_match_v2` with multi-sample judge options.
* [`customer_service_agent/eval_config.rubric.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/eval_config.rubric.json) — Configures `rubric_based_final_response_quality_v1` assessing specific criteria like conciseness and completeness.
* [`customer_service_agent/eval_config_with_metrics.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/eval_config_with_metrics.json) — Runs user simulator with `hallucinations_v1` and `safety_v1` thresholds.
* [`customer_service_agent/eval_config_without_metrics.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/eval_config_without_metrics.json) — Runs user simulator in dry-run mode to inspect conversation traces without metric calculation.

---

## Quickstart & Environment Setup

### 1. Install Dependencies

```bash
# ADK with evaluation extras and Vertex AI evaluation SDK
pip install --upgrade \
    "google-adk[eval]==1.34.1" \
    "google-cloud-aiplatform[adk,agent_engines,evaluation]>=1.148.1"
```

### 2. Configure Google Cloud

Set your Google Cloud project and region to authenticate against Vertex AI:

```bash
export GCP_PROJECT="bold-kit-384717"
export GCP_LOCATION="us-central1"
```

---

## Evaluation Workflow 1: Local ADK Evaluation

ADK's built-in evaluation framework runs locally without requiring deployment. It tests agents against fixed golden evalsets or dynamically generated simulation runs.

### 1. Reference Metrics Evaluation
Evaluates tool calling accuracy against the golden trajectory and checks textual response similarity:

```bash
adk eval customer_service_agent \
    customer_service_agent/cs_eval_set.evalset.json \
    --config_file_path customer_service_agent/eval_config.reference.json
```

**Metrics Evaluated:**
* `tool_trajectory_avg_score` (Target: `1.0`): Measures whether the agent called the exact expected tools with matching arguments in the correct order.
* `response_match_score` (Target: `>= 0.8`): Computes semantic/token similarity between agent response and expected reference response.

### 2. LLM-as-a-Judge Evaluation
Uses a judge model (e.g. `gemini-3.5-flash`) with sampling to evaluate the final response semantically:

```bash
adk eval customer_service_agent \
    customer_service_agent/cs_eval_set.evalset.json \
    --config_file_path customer_service_agent/eval_config.judge.json
```

### 3. Rubric-Based Evaluation
Scores responses against structured rubric criteria (e.g. conciseness, completeness, empathy):

```bash
adk eval customer_service_agent \
    customer_service_agent/cs_eval_set.evalset.json \
    --config_file_path customer_service_agent/eval_config.rubric.json
```

### 4. Multi-Turn User Simulation
Automates dynamic multi-turn interactions by pitting an LLM User Simulator against your agent based on defined goals in [`conversation_scenarios.json`](file:///Users/prothiag/code/agents/evals/customer_service_agent/conversation_scenarios.json):

```bash
# Step 1: Generate the simulation eval set from scenarios
adk eval_set create customer_service_agent cs_user_sim \
    --scenario_file_path customer_service_agent/conversation_scenarios.json \
    --session_input_file_path customer_service_agent/session_input.json \
    --eval_set_file_path customer_service_agent/cs_user_sim.evalset.json

# Step 2: Run simulation with Hallucination and Safety metrics
adk eval customer_service_agent \
    customer_service_agent/cs_user_sim.evalset.json \
    --config_file_path customer_service_agent/eval_config_with_metrics.json
```

---

## Evaluation Workflow 2: Vertex AI / GEAP Managed Evaluation

For large-scale, automated evaluation pipelines and deployed reasoning engines, Vertex AI Gen AI Evaluation provides managed services:

### 1. Synthetic Scenario Generation
Automatically synthesize realistic multi-turn conversation scenarios from an agent definition:

```python
import vertexai
from vertexai.preview.evaluation import eval_service_client, types

client = eval_service_client.EvalServiceClient(
    project="bold-kit-384717",
    location="us-central1"
)

agent_info = types.evals.AgentInfo.load_from_agent(agent=travel_agent)
eval_dataset = client.evals.generate_conversation_scenarios(
    agent_info=agent_info,
    scenario_count=5
)
```

### 2. Custom Evaluation Metrics
Define both deterministic computation-based metrics and custom LLM-prompted metrics:

* **Computation Metric (Agent Efficiency)**:
  ```python
  efficiency_metric_code = """
  def evaluate(instance: dict) -> float:
      turns = instance.get("intermediate_data", {}).get("turns", [])
      tool_calls = sum(len(t.get("tool_uses", [])) for t in turns)
      return 1.0 if tool_calls <= 3 else 0.5
  """
  ```

* **Custom LLM Metric (Tone & Empathy)**:
  ```python
  tone_check_metric = types.LLMMetric(
      name="tone_check",
      prompt_template="""Analyze the agent's tone:
      {response}
      Score 1.0 if polite, professional, and clear; score 0.0 otherwise."""
  )
  ```

### 3. Loss Clustering & Diagnostics
Cluster failing conversations automatically to identify systematic agent weaknesses:

```python
clusters = client.evals.generate_loss_clusters(
    evaluation_run_name=eval_run.name,
    target_metric="rubric_based_final_response_quality_v1"
)
```

### 4. Managed Remote Evaluation
Trigger an asynchronous managed evaluation job on a deployed Vertex AI Reasoning Engine:

```python
eval_run = client.evals.create_evaluation_run(
    dataset=eval_dataset,
    target_agent_engine=deployed_agent_engine_resource_name,
    metrics=eval_metrics
)
```

---

## Evaluation Metric Summary

| Metric Name | Type | Description |
| :--- | :--- | :--- |
| `tool_trajectory_avg_score` | Reference | Exact matching of tool calls, arguments, and execution sequence against ground truth. |
| `response_match_score` | Reference | Textual/semantic similarity to reference golden responses. |
| `final_response_match_v2` | LLM Judge | LLM grading of output correctness against expected reference. |
| `rubric_based_final_response_quality_v1` | LLM Judge | Multi-dimensional scoring against user-defined qualitative rubrics. |
| `hallucinations_v1` | Safety / Quality | Detects unsupported or fabricated claims not grounded in tool outputs. |
| `safety_v1` | Safety | Checks for toxic, unsafe, or non-compliant agent outputs. |
| `efficiency_metric` | Custom (Python) | Deterministic metric scoring agent tool invocation efficiency and turn counts. |
| `tone_check` | Custom (LLM) | Custom LLM judge scoring politeness, empathy, and brand voice adherence. |

---

## Best Practices for Agent Evaluation

1. **Evaluate Tool Trajectories First**: Ensure the agent selects the right tools with exact parameters before optimizing response style.
2. **Combine Deterministic and LLM Judges**: Use reference trajectory scores for strict correctness, and LLM judges for natural language quality.
3. **Incorporate User Simulation**: Static scripts don't reveal how agents handle unexpected user replies or interruptions. User simulation uncovers edge cases in multi-turn dialogues.
4. **Use Evaluation to Drive Prompt Engineering**: Iterate on system instructions by comparing before-and-after trajectory scores (e.g. fixing premature tool execution).
5. **Analyze Loss Clusters**: Group low-scoring evaluation cases to identify common failure modes across user intents.
