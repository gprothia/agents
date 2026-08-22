"""Interactive Local CLI Runner & Multi-Scenario Demonstration Harness.

Demonstrates end-to-end multi-pillar contractor vetting workflows:
1. Fully Compliant Contractor (Apex Infrastructure) -> Certified APPROVAL
2. High Safety Risk Contractor (Vortex Builders) -> HITL Code-Stop & Conditional Review
3. Sanctioned Debarred Entity (Titan Defense) -> Immediate Redline REJECTION
4. Under-Bonded Contractor (Horizon Civil) -> Bonding Limit Code-Stop & Mitigation
"""

import argparse
import json
import sys
import uuid
from typing import Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from .agent import app, root_agent
from .hitl import HITLManager
from .memory import compactor
from .storage import storage
from .telemetry import get_structured_logger

logger = get_structured_logger("contractor_vetting.runner")


def run_vetting_demo(contractor_id: str = "APEX-INFRA-01", project_value: float = 10_000_000.0) -> None:
    """Run an automated end-to-end contractor vetting workflow demonstration."""
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    print("\n" + "=" * 80)
    print(f"🚀 STARTING CONTRACTOR VETTING AUDIT: {contractor_id} (Target Contract: ${project_value:,.2f})")
    print(f"Session ID: {session_id}")
    print("=" * 80 + "\n")

    # Initialize session in persistent store
    storage.create_or_get_session(session_id=session_id, contractor_id=contractor_id)

    # Instantiate ADK Runner with InMemory / Database session service
    session_service = InMemorySessionService()
    runner = Runner(
        app=app,
        session_service=session_service,
        auto_create_session=True,
    )

    prompt = (
        f"Please execute a full 5-pillar contractor vetting audit on prospective contractor '{contractor_id}' "
        f"for a target project contract valued at ${project_value:,.2f}. "
        f"Systematically verify: "
        f"1. Identity & SAM.gov/OFAC Sanctions\n"
        f"2. State Licensure & ACORD 25 Insurance\n"
        f"3. Financial Solvency & Surety Bonding Capacity\n"
        f"4. Workplace Safety & 3-Year Rolling EMR\n"
        f"5. Past Project Delivery Performance & Reference History.\n"
        f"If any high risk or exceptions occur, initiate human oversight. Otherwise, finalize the official dossier."
    )

    print(f"📥 Submitting Audit Request:\n{prompt}\n")
    storage.save_turn(session_id=session_id, role="user", content=prompt)

    try:
        # Note: In offline/sandbox mode without Vertex AI credentials, this demonstrates
        # the deterministic tool execution pipeline and schema validation.
        print("⚙️  Executing 5-Pillar Vetting Protocol...")
        from .tools import (
            audit_workplace_safety_and_emr,
            calculate_financial_risk_and_bonding,
            fetch_past_performance_and_references,
            finalize_contractor_vetting_dossier,
            request_human_oversight_approval,
            screen_sanctions_and_debarment_lists,
            verify_contractor_license_and_insurance,
        )

        # 1. Sanctions Screening
        print("\n[Pillar 1/5] Screening SAM.gov & OFAC Sanctions...")
        sanc = screen_sanctions_and_debarment_lists(contractor_id, "12-3456789")
        print(f"  -> Sanctions Risk Tier: {sanc.get('risk_tier')}")

        # 2. License & Insurance
        print("\n[Pillar 2/5] Validating State Licensure & Insurance...")
        lic = verify_contractor_license_and_insurance(contractor_id, "CA-LIC-984210", "CA")
        print(f"  -> License Status: {lic.get('license_status')}, Insurance Status: {lic.get('insurance_status')}")

        # 3. Financial & Bonding
        print("\n[Pillar 3/5] Assessing Financial Strength & Bonding Limits...")
        fin = calculate_financial_risk_and_bonding(contractor_id, project_value)
        print(f"  -> Financial Risk: {fin.get('financial_risk_level')}, Bonding Status: {fin.get('bonding_status')}")

        # 4. Workplace Safety & EMR
        print("\n[Pillar 4/5] Auditing OSHA Logs & Experience Modification Rate...")
        safety = audit_workplace_safety_and_emr(contractor_id, required_max_emr=1.00)
        print(f"  -> Safety Risk: {safety.get('safety_risk_level')}, 3-Yr EMR: {safety.get('experience_modification_rate_3yr_avg')}")

        # 5. Past Performance
        print("\n[Pillar 5/5] Auditing Historical Deliverables & Quality Scores...")
        perf = fetch_past_performance_and_references(contractor_id)
        print(f"  -> Performance Risk: {perf.get('performance_risk_level')}, Avg Quality: {perf.get('average_quality_score')}/100")

        # Adjudication Logic
        print("\n[Adjudication] Synthesizing 5-Pillar Findings...")
        is_debarred = sanc.get("risk_tier") in ["CONFIRMED_SANCTIONED", "DEBARRED"]
        has_safety_flag = safety.get("safety_risk_level") in ["HIGH", "CRITICAL"]
        bonding_exceeded = fin.get("bonding_status") in ["EXCEEDED", "UNBONDED"]

        if is_debarred:
            decision = "REJECTED"
            risk_score = 95
            summary = "Contractor is listed on federal debarment registries. Award is prohibited."
            token = None
        elif has_safety_flag or bonding_exceeded:
            print("\n⚠️  HIGH RISK DETECTED: Triggering Human-in-the-Loop (HITL) Code-Stop...")
            reasons = []
            if has_safety_flag:
                reasons.append(f"EMR ({safety.get('experience_modification_rate_3yr_avg')}) exceeds 1.00 benchmark")
            if bonding_exceeded:
                reasons.append(f"Project value (${project_value:,.2f}) exceeds bonding limit")

            hitl_res = request_human_oversight_approval(
                contractor_id=contractor_id,
                escalation_reason="; ".join(reasons),
                risk_factors=reasons,
            )
            token = hitl_res.get("escalation_token")
            print(f"  -> Generated Escalation Token: {token}")
            print(f"  -> Status: PENDING HUMAN AUTHORIZATION")

            # Simulate human officer review and conditional sign-off
            print("\n👤 Chief Compliance Officer reviews and provides signed authorization...")
            HITLManager.authorize_escalation(
                token=token,
                reviewer_name="Dr. Eleanor Vance",
                reviewer_role="CHIEF_COMPLIANCE_OFFICER",
                approved=True,
                notes="Approved under mandatory enhanced safety supervision and secondary surety rider.",
            )

            decision = "CONDITIONALLY_APPROVED"
            risk_score = 48
            summary = "Conditionally approved subject to designated safety mitigation covenants and signed CCO waiver."
        else:
            decision = "APPROVED"
            risk_score = 15
            summary = "Exemplary compliance across all 5 pillars. Low risk profile."
            token = None

        # Final Dossier Certification
        print(f"\n📜 Finalizing Official Vetting Dossier ({decision})...")
        dossier = finalize_contractor_vetting_dossier(
            contractor_id=contractor_id,
            contractor_name=sanc.get("contractor_name", contractor_id),
            target_project_name="Regional Infrastructure Modernization",
            target_project_value_usd=project_value,
            decision=decision,
            composite_risk_score_out_of_100=risk_score,
            compliance_pillar_scores={
                "identity_sanctions": 100 if not is_debarred else 0,
                "licensing_insurance": 95 if lic.get("license_status") == "ACTIVE" else 20,
                "financial_bonding": 90 if not bonding_exceeded else 40,
                "safety_emr": 92 if not has_safety_flag else 45,
                "past_performance": 94,
            },
            executive_summary=summary,
            mandatory_stipulations=["Mandatory quarterly safety log re-audit"] if decision == "CONDITIONALLY_APPROVED" else [],
            human_approval_token=token,
        )

        print("\n" + dossier.get("certificate_text", ""))
        print("\n✅ Vetting workflow completed successfully. Audit record persisted in database.\n")

    except Exception as ex:
        print(f"\n❌ Error during runner execution: {ex}")
        logger.error("Runner execution failed", exc_info=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Contractor Vetting Enterprise Agent Runner")
    parser.add_argument("--contractor", default="APEX-INFRA-01", help="Contractor ID (APEX-INFRA-01, VORTEX-BUILD-02, TITAN-DEFENSE-03, HORIZON-CIVIL-04)")
    parser.add_argument("--value", type=float, default=10_000_000.0, help="Target project value in USD")
    args = parser.parse_args()

    run_vetting_demo(contractor_id=args.contractor, project_value=args.value)


if __name__ == "__main__":
    main()
