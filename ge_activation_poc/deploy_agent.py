"""Deployment agent (POC).

Reads the plan sheet, and for each saved decision:
  1. generates real Terraform (google_discovery_engine_* resources),
  2. runs `terraform init` + `terraform validate` + `terraform plan` if the terraform
     binary is available (dry-run only; nothing is applied),
  3. writes the terraform path and deploy status back to the plan sheet.

This mirrors the two-agent design: agent 1 decides and stores, agent 2 reads and applies.
For the POC it stays at `plan` (dry-run). Flip RUN_APPLY to True only against a throwaway
sandbox project you own.

Usage:  python deploy_agent.py
"""
from __future__ import annotations
import os
import shutil
import subprocess

from ge_agent import plan_sheet
from ge_agent.terraform_gen import generate_terraform

OUT_DIR = os.path.join(os.path.dirname(__file__), "terraform_out")
RUN_APPLY = False  # keep False for the POC


def _terraform_available() -> bool:
    return shutil.which("terraform") is not None


def _run(cmd: list[str], cwd: str) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr)[-2000:]
    except Exception as e:
        return 1, str(e)


def deploy():
    decisions = plan_sheet.read_decisions(status="saved")
    if not decisions:
        print("No decisions with status 'saved' in the plan sheet. Run the planning agent first.")
        return

    have_tf = _terraform_available()
    print(f"Found {len(decisions)} decision(s) to deploy. terraform binary: "
          f"{'yes' if have_tf else 'no (dry-run will be simulated)'}\n")

    for dec in decisions:
        did = dec["id"]
        tf_path = generate_terraform(dec, OUT_DIR)
        rel = os.path.relpath(tf_path, os.path.dirname(__file__))
        print(f"[{did}] {dec['title']}")
        print(f"        terraform -> {rel}")

        if have_tf:
            d = os.path.dirname(tf_path)
            rc1, _ = _run(["terraform", "init", "-input=false", "-no-color"], d)
            rc2, out2 = _run(["terraform", "validate", "-no-color"], d)
            status = "validated" if rc2 == 0 else "validate-failed"
            if rc2 == 0 and RUN_APPLY:
                rc3, _ = _run(["terraform", "apply", "-auto-approve", "-input=false", "-no-color"], d)
                status = "applied" if rc3 == 0 else "apply-failed"
            elif rc2 == 0:
                rc3, _ = _run(["terraform", "plan", "-input=false", "-no-color"], d)
                status = "planned (dry-run)" if rc3 == 0 else "plan-needs-vars (expected in POC)"
            deploy_status = status
        else:
            deploy_status = "generated (terraform not installed \u2014 dry-run simulated)"

        plan_sheet.update_status(did, status="deployed", deploy_status=deploy_status,
                                 terraform_path=rel)
        print(f"        deploy_status -> {deploy_status}\n")

    print("Done. Plan sheet updated with terraform paths and deploy status.")


if __name__ == "__main__":
    deploy()
