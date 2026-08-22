"""Comprehensive Contractor Vetting Tools for ADK Agent.

Implements:
1. verify_contractor_license_and_insurance
2. screen_sanctions_and_debarment_lists
3. calculate_financial_risk_and_bonding
4. audit_workplace_safety_and_emr
5. fetch_past_performance_and_references
6. request_human_oversight_approval
7. finalize_contractor_vetting_dossier

Adheres strictly to:
- Comprehensive Google-style docstrings
- Highly descriptive naming
- Explicit Pydantic JSON schemas
- Guided error handling with recovery instructions
- Dual-phase Intent vs. Outcome telemetry & OpenTelemetry tracing
"""

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .schemas import (
    BondingStatus,
    FinancialRiskRequest,
    FinancialRiskResponse,
    HITLApprovalRequest,
    HITLApprovalResponse,
    HITLStatus,
    InsuranceStatus,
    LicenseStatus,
    LicenseVerificationRequest,
    LicenseVerificationResponse,
    PastPerformanceRequest,
    PastPerformanceResponse,
    PolicyDetail,
    ProjectPerformanceRecord,
    RiskLevel,
    SafetyAuditRequest,
    SafetyAuditResponse,
    SafetyCitation,
    SanctionMatch,
    SanctionsRiskTier,
    SanctionsScreeningRequest,
    SanctionsScreeningResponse,
    ToolErrorResponse,
    VettingDecision,
    VettingDossierRequest,
    VettingDossierResponse,
)
from .telemetry import PIIRedactionService, TelemetryCollector, TraceContext


# ==============================================================================
# REALISTIC MOCK ENTERPRISE DATABASE OF CONTRACTORS
# ==============================================================================

MOCK_CONTRACTORS_DB: Dict[str, Dict[str, Any]] = {
    # 1. Fully Compliant Contractor
    "APEX-INFRA-01": {
        "name": "Apex Infrastructure Solutions LLC",
        "ein": "12-3456789",
        "state": "CA",
        "license_number": "CA-LIC-984210",
        "license_status": LicenseStatus.ACTIVE,
        "license_type": "Class A - General Engineering Contractor",
        "license_expiration": "2028-11-30",
        "disciplinary_actions": False,
        "sam_active": True,
        "cage_code": "7A9K2",
        "sanctions": [],
        "dnb_paydex": 82,
        "financial_stress_score": 1,
        "working_capital": 4_500_000.0,
        "current_ratio": 2.1,
        "single_bonding_limit": 25_000_000.0,
        "aggregate_bonding_limit": 60_000_000.0,
        "surety": "Travelers Casualty and Surety Company of America",
        "bankruptcy": False,
        "emr_3yr": 0.82,
        "trir": 1.4,
        "dart": 0.6,
        "fatalities_5yr": 0,
        "citations": [],
        "safety_program": True,
        "policies": [
            {
                "policy_type": "Commercial General Liability",
                "carrier_name": "Zurich American Insurance Company",
                "am_best_rating": "A+",
                "coverage_limit_usd": 5_000_000.0,
                "expiration_date": "2027-06-30",
                "is_active": True,
                "additional_insured_endorsed": True,
            },
            {
                "policy_type": "Workers Compensation",
                "carrier_name": "Liberty Mutual Insurance",
                "am_best_rating": "A",
                "coverage_limit_usd": 1_000_000.0,
                "expiration_date": "2027-06-30",
                "is_active": True,
                "additional_insured_endorsed": True,
            },
            {
                "policy_type": "Excess / Umbrella Liability",
                "carrier_name": "Travelers Property Casualty",
                "am_best_rating": "A++",
                "coverage_limit_usd": 10_000_000.0,
                "expiration_date": "2027-06-30",
                "is_active": True,
                "additional_insured_endorsed": True,
            }
        ],
        "projects": [
            {
                "project_name": "Silicon Valley Clean Water Pipeline Replacement",
                "client_name": "Bay Area Water Authority",
                "contract_value_usd": 12_400_000.0,
                "completed_year": 2024,
                "schedule_performance": "AHEAD_OF_SCHEDULE",
                "cost_performance_index_cpi": 1.04,
                "quality_score_out_of_100": 96,
                "cpars_overall_rating": "Exceptional"
            },
            {
                "project_name": "Metro Transit Substation Seismic Retrofit",
                "client_name": "Regional Transportation District",
                "contract_value_usd": 8_200_000.0,
                "completed_year": 2023,
                "schedule_performance": "ON_TIME",
                "cost_performance_index_cpi": 1.01,
                "quality_score_out_of_100": 92,
                "cpars_overall_rating": "Very Good"
            }
        ]
    },

    # 2. High Safety Risk Contractor (Elevated EMR, OSHA Violations)
    "VORTEX-BUILD-02": {
        "name": "Vortex Industrial Builders Inc",
        "ein": "45-9876543",
        "state": "TX",
        "license_number": "TX-CON-551920",
        "license_status": LicenseStatus.ACTIVE,
        "license_type": "Commercial General Contractor",
        "license_expiration": "2027-04-15",
        "disciplinary_actions": False,
        "sam_active": True,
        "cage_code": "8B3X1",
        "sanctions": [],
        "dnb_paydex": 74,
        "financial_stress_score": 2,
        "working_capital": 1_800_000.0,
        "current_ratio": 1.4,
        "single_bonding_limit": 10_000_000.0,
        "aggregate_bonding_limit": 20_000_000.0,
        "surety": "Hartford Fire Insurance Company",
        "bankruptcy": False,
        "emr_3yr": 1.34,  # High safety risk! (>1.20 threshold)
        "trir": 4.8,
        "dart": 2.6,
        "fatalities_5yr": 0,
        "citations": [
            {
                "citation_id": "OSHA-TX-2024-8841",
                "inspection_date": "2024-03-12",
                "severity": "Serious",
                "standard_violated": "1926.501(b)(1) Fall Protection Inadequate",
                "penalty_amount_usd": 15_625.0,
                "status": "Closed"
            },
            {
                "citation_id": "OSHA-TX-2023-4109",
                "inspection_date": "2023-08-19",
                "severity": "Serious",
                "standard_violated": "1926.451 Scaffolding Safety Deficiencies",
                "penalty_amount_usd": 12_500.0,
                "status": "Closed"
            }
        ],
        "safety_program": True,
        "policies": [
            {
                "policy_type": "Commercial General Liability",
                "carrier_name": "CNA Insurance",
                "am_best_rating": "A",
                "coverage_limit_usd": 2_000_000.0,
                "expiration_date": "2026-12-31",
                "is_active": True,
                "additional_insured_endorsed": True,
            },
            {
                "policy_type": "Workers Compensation",
                "carrier_name": "Texas Mutual Insurance",
                "am_best_rating": "A",
                "coverage_limit_usd": 1_000_000.0,
                "expiration_date": "2026-12-31",
                "is_active": True,
                "additional_insured_endorsed": True,
            }
        ],
        "projects": [
            {
                "project_name": "Austin Distribution Center Expansion",
                "client_name": "Lone Star Logistics",
                "contract_value_usd": 5_500_000.0,
                "completed_year": 2024,
                "schedule_performance": "DELAYED",
                "cost_performance_index_cpi": 0.94,
                "quality_score_out_of_100": 78,
                "cpars_overall_rating": "Marginal"
            }
        ]
    },

    # 3. Sanctions / Debarred Entity (Redline Fail)
    "TITAN-DEFENSE-03": {
        "name": "Titan Heavy Engineering Group",
        "ein": "98-7654321",
        "state": "NY",
        "license_number": "NY-ENG-300119",
        "license_status": LicenseStatus.SUSPENDED,
        "license_type": "Heavy Civil & Defense Contracting",
        "license_expiration": "2025-01-01",
        "disciplinary_actions": True,
        "sam_active": False,
        "cage_code": "9D1F4",
        "sanctions": [
            {
                "list_source": "SAM.gov EPLS",
                "matched_entity": "Titan Heavy Engineering Group",
                "match_confidence": 0.99,
                "program": "Federal Debarment - Procurement Non-Responsibility",
                "effective_date": "2024-05-10",
                "details": "Entity debarred by Defense Logistics Agency due to counterfeit parts distribution."
            }
        ],
        "dnb_paydex": 42,
        "financial_stress_score": 5,
        "working_capital": -1_200_000.0,
        "current_ratio": 0.7,
        "single_bonding_limit": 0.0,
        "aggregate_bonding_limit": 0.0,
        "surety": "None (Surety cancelled due to debarment)",
        "bankruptcy": True,
        "emr_3yr": 1.58,
        "trir": 6.2,
        "dart": 4.1,
        "fatalities_5yr": 1,
        "citations": [
            {
                "citation_id": "OSHA-NY-2024-0012",
                "inspection_date": "2024-01-10",
                "severity": "Willful",
                "standard_violated": "1926.652 Trenching and Excavation Cave-in Hazard",
                "penalty_amount_usd": 145_027.0,
                "status": "Contested"
            }
        ],
        "safety_program": False,
        "policies": [],
        "projects": []
    },

    # 4. Under-Bonded / Marginal Financial Contractor (Requires HITL)
    "HORIZON-CIVIL-04": {
        "name": "Horizon Civil Builders LLC",
        "ein": "33-1122334",
        "state": "CO",
        "license_number": "CO-LIC-77412",
        "license_status": LicenseStatus.ACTIVE,
        "license_type": "Class B - Commercial Contractor",
        "license_expiration": "2027-09-30",
        "disciplinary_actions": False,
        "sam_active": True,
        "cage_code": "6M4P9",
        "sanctions": [],
        "dnb_paydex": 68,
        "financial_stress_score": 3,
        "working_capital": 650_000.0,
        "current_ratio": 1.25,
        "single_bonding_limit": 3_000_000.0,   # Limit is $3M
        "aggregate_bonding_limit": 7_000_000.0,
        "surety": "Berkshire Hathaway Specialty Insurance",
        "bankruptcy": False,
        "emr_3yr": 0.95,
        "trir": 2.2,
        "dart": 1.0,
        "fatalities_5yr": 0,
        "citations": [],
        "safety_program": True,
        "policies": [
            {
                "policy_type": "Commercial General Liability",
                "carrier_name": "Markel Insurance",
                "am_best_rating": "A",
                "coverage_limit_usd": 2_000_000.0,
                "expiration_date": "2026-10-31",
                "is_active": True,
                "additional_insured_endorsed": True,
            },
            {
                "policy_type": "Workers Compensation",
                "carrier_name": "Pinnacol Assurance",
                "am_best_rating": "A-",
                "coverage_limit_usd": 1_000_000.0,
                "expiration_date": "2026-10-31",
                "is_active": True,
                "additional_insured_endorsed": True,
            }
        ],
        "projects": [
            {
                "project_name": "Boulder County Community Health Wing",
                "client_name": "Boulder County Public Works",
                "contract_value_usd": 2_100_000.0,
                "completed_year": 2024,
                "schedule_performance": "ON_TIME",
                "cost_performance_index_cpi": 0.98,
                "quality_score_out_of_100": 88,
                "cpars_overall_rating": "Satisfactory"
            }
        ]
    }
}


# ==============================================================================
# TOOL 1: VERIFY LICENSE AND INSURANCE
# ==============================================================================

def verify_contractor_license_and_insurance(
    contractor_id: str,
    license_number: str,
    state: str,
    required_general_liability_min: float = 1_000_000.0,
    required_workers_comp_min: float = 500_000.0,
) -> Dict[str, Any]:
    """Validate a contractor's state trade license and ACORD 25 insurance policies.

    Cross-references official state contractor licensing databases and authenticated
    insurance certificates to ensure the contractor holds an active license, has no
    suspensions or disciplinary sanctions, and carries verified General Liability and
    Workers' Compensation coverage meeting client threshold minimums.

    Args:
        contractor_id: Unique contractor identifier (e.g. 'APEX-INFRA-01').
        license_number: State contractor license ID to verify.
        state: Two-letter US state postal abbreviation where license is held.
        required_general_liability_min: Minimum General Liability coverage limit required (USD).
        required_workers_comp_min: Minimum Workers' Compensation coverage required (USD).

    Returns:
        A dictionary containing license status, expiration date, disciplinary records,
        and verified insurance policies with A.M. Best ratings. If verification fails,
        returns a structured ToolErrorResponse with actionable recovery instructions.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = verify_contractor_license_and_insurance("APEX-INFRA-01", "CA-LIC-984210", "CA")
        >>> print(res["license_status"])
        'ACTIVE'
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="verify_contractor_license_and_insurance",
        intended_action=f"Verify state license '{license_number}' ({state}) and insurance for {contractor_id}",
        input_parameters={
            "contractor_id": contractor_id,
            "license_number": license_number,
            "state": state,
            "required_gl": required_general_liability_min,
            "required_wc": required_workers_comp_min,
        },
        rationale="Pillar 2 verification: ensure legal licensing and adequate liability indemnity."
    )

    with TraceContext("tool.verify_license_and_insurance", {"contractor_id": contractor_id, "state": state}):
        try:
            # Validate input arguments via Pydantic
            req = LicenseVerificationRequest(
                contractor_id=contractor_id,
                license_number=license_number,
                state=state,
                required_general_liability_min=required_general_liability_min,
                required_workers_comp_min=required_workers_comp_min,
            )

            # Match against database
            data = MOCK_CONTRACTORS_DB.get(req.contractor_id)
            if not data:
                err = ToolErrorResponse(
                    error_code="CONTRACTOR_RECORD_NOT_FOUND",
                    error_message=f"No registration found for contractor_id '{contractor_id}'.",
                    recovery_guidance="Verify the contractor ID against the procurement onboarding registry or search by company name.",
                    suggested_retry_parameters={"contractor_id": "APEX-INFRA-01"}
                ).model_dump()
                TelemetryCollector.log_outcome(
                    tool_name="verify_contractor_license_and_insurance",
                    execution_time_ms=(time.time() - start_time) * 1000,
                    status="FAILURE",
                    result_summary=err,
                    intent_id=intent_id,
                    deviation_detected=True,
                )
                return err

            policies = [PolicyDetail(**p) for p in data.get("policies", [])]
            gl_active = any(p.policy_type == "Commercial General Liability" and p.coverage_limit_usd >= req.required_general_liability_min and p.is_active for p in policies)
            wc_active = any(p.policy_type == "Workers Compensation" and p.coverage_limit_usd >= req.required_workers_comp_min and p.is_active for p in policies)

            if not policies:
                ins_status = InsuranceStatus.NOT_PROVIDED
            elif gl_active and wc_active:
                ins_status = InsuranceStatus.VALID
            else:
                ins_status = InsuranceStatus.INSUFFICIENT_LIMITS

            resp = LicenseVerificationResponse(
                contractor_id=req.contractor_id,
                license_number=data["license_number"],
                state=data["state"],
                license_status=data["license_status"],
                license_type=data["license_type"],
                license_expiration=data["license_expiration"],
                disciplinary_actions_found=data["disciplinary_actions"],
                insurance_status=ins_status,
                policies=policies,
                compliance_summary=f"License is {data['license_status'].value}. Insurance is {ins_status.value} with {len(policies)} verified policies.",
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="verify_contractor_license_and_insurance",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"license_status": resp["license_status"], "insurance_status": resp["insurance_status"]},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            err = ToolErrorResponse(
                error_code="LICENSE_VALIDATION_ERROR",
                error_message=str(ex),
                recovery_guidance="Check that license number and state format (2-letter code) match requirements, and re-execute.",
            ).model_dump()
            TelemetryCollector.log_outcome(
                tool_name="verify_contractor_license_and_insurance",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="ERROR",
                result_summary=err,
                intent_id=intent_id,
                deviation_detected=True,
            )
            return err


# ==============================================================================
# TOOL 2: SCREEN SANCTIONS AND DEBARMENT LISTS
# ==============================================================================

def screen_sanctions_and_debarment_lists(
    contractor_name: str,
    tax_id_ein: str,
    country: str = "US",
    principal_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Screen an entity and its key executives against federal sanctions and debarment registries.

    Performs comprehensive screening across SAM.gov (EPLS), OFAC Specially Designated
    Nationals (SDN), Bureau of Industry & Security (BIS) Entity List, and international
    multilateral development bank debarment lists to identify legal disqualifications.

    Args:
        contractor_name: Official legal entity name registered with tax authorities.
        tax_id_ein: 9-digit Federal Employer Identification Number ('XX-XXXXXXX' or 'XXXXXXXXX').
        country: ISO 3166-1 alpha-2 country code. Default is 'US'.
        principal_names: Optional list of names of executive officers or majority owners.

    Returns:
        A dictionary containing sanctions risk tier ('CLEAR', 'POTENTIAL_MATCH', 'DEBARRED'),
        SAM.gov active status, CAGE code, and matched records.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = screen_sanctions_and_debarment_lists("Apex Infrastructure Solutions LLC", "12-3456789")
        >>> print(res["risk_tier"])
        'CLEAR'
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="screen_sanctions_and_debarment_lists",
        intended_action=f"Screen '{contractor_name}' (EIN: {PIIRedactionService.redact_text(tax_id_ein)}) against SAM.gov & OFAC",
        input_parameters={"contractor_name": contractor_name, "tax_id_ein": tax_id_ein, "country": country},
        rationale="Pillar 1 verification: check for federal debarment and international sanctions."
    )

    with TraceContext("tool.screen_sanctions", {"contractor_name": contractor_name, "country": country}):
        try:
            req = SanctionsScreeningRequest(
                contractor_name=contractor_name,
                tax_id_ein=tax_id_ein,
                country=country,
                principal_names=principal_names,
            )

            # Match by normalized EIN or Name
            clean_ein = req.tax_id_ein.replace("-", "").strip()
            matched_entry = None
            for entry in MOCK_CONTRACTORS_DB.values():
                if entry["ein"].replace("-", "") == clean_ein or entry["name"].lower() in req.contractor_name.lower():
                    matched_entry = entry
                    break

            if not matched_entry:
                # Default clear response for unknown clean entities in sandbox
                resp = SanctionsScreeningResponse(
                    contractor_name=req.contractor_name,
                    tax_id_ein_masked=f"XX-XXX{clean_ein[-4:]}" if len(clean_ein) >= 4 else "XX-XXX0000",
                    risk_tier=SanctionsRiskTier.CLEAR,
                    sam_gov_active_registration=True,
                    cage_code="9Z001",
                    matches_found=[],
                    adjudication_guidance="Entity cleared across SAM.gov and OFAC registries. No adverse records found."
                ).model_dump()
            else:
                raw_sanctions = matched_entry.get("sanctions", [])
                sanction_objs = [SanctionMatch(**s) for s in raw_sanctions]
                if sanction_objs:
                    tier = SanctionsRiskTier.DEBARRED
                    guidance = "CRITICAL: Entity is listed on official debarment/sanctions registry. Contract award strictly PROHIBITED."
                else:
                    tier = SanctionsRiskTier.CLEAR
                    guidance = "Clear standing: active in SAM.gov without exclusions or sanctions."

                resp = SanctionsScreeningResponse(
                    contractor_name=matched_entry["name"],
                    tax_id_ein_masked=f"XX-XXX{clean_ein[-4:]}" if len(clean_ein) >= 4 else "XX-XXX0000",
                    risk_tier=tier,
                    sam_gov_active_registration=matched_entry["sam_active"],
                    cage_code=matched_entry.get("cage_code"),
                    matches_found=sanction_objs,
                    adjudication_guidance=guidance,
                ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="screen_sanctions_and_debarment_lists",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"risk_tier": resp["risk_tier"], "sam_active": resp["sam_gov_active_registration"]},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            err = ToolErrorResponse(
                error_code="SANCTIONS_SCREENING_ERROR",
                error_message=str(ex),
                recovery_guidance="Ensure EIN is valid 9-digit format and contractor name is not blank, then retry.",
            ).model_dump()
            TelemetryCollector.log_outcome(
                tool_name="screen_sanctions_and_debarment_lists",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="ERROR",
                result_summary=err,
                intent_id=intent_id,
                deviation_detected=True,
            )
            return err


# ==============================================================================
# TOOL 3: CALCULATE FINANCIAL RISK AND BONDING
# ==============================================================================

def calculate_financial_risk_and_bonding(
    contractor_id: str,
    target_project_value_usd: float,
    annual_revenue_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate commercial credit health, working capital adequacy, and surety bonding capacity.

    Assesses D&B Paydex rating, financial stress score, liquidity ratios, bankruptcy
    history, and Treasury-listed single and aggregate surety bonding limits to determine
    if the contractor has sufficient balance sheet strength to complete the project without default.

    Args:
        contractor_id: Unique contractor identifier.
        target_project_value_usd: Estimated contract value in USD for target scope.
        annual_revenue_usd: Optional reported annual revenue for scale benchmarking.

    Returns:
        A dictionary containing Paydex score, bonding capacity status ('ADEQUATE', 'INSUFFICIENT',
        'EXCEEDED'), bankruptcy history, and overall financial risk tier.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = calculate_financial_risk_and_bonding("APEX-INFRA-01", 10_000_000.0)
        >>> print(res["bonding_status"])
        'ADEQUATE'
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="calculate_financial_risk_and_bonding",
        intended_action=f"Assess financial strength and bonding for {contractor_id} on ${target_project_value_usd:,.2f} project",
        input_parameters={"contractor_id": contractor_id, "project_value": target_project_value_usd},
        rationale="Pillar 3 verification: verify solvency, working capital, and surety bonding limits."
    )

    with TraceContext("tool.calculate_financial_risk", {"contractor_id": contractor_id}):
        try:
            req = FinancialRiskRequest(
                contractor_id=contractor_id,
                target_project_value_usd=target_project_value_usd,
                annual_revenue_usd=annual_revenue_usd,
            )

            data = MOCK_CONTRACTORS_DB.get(req.contractor_id)
            if not data:
                err = ToolErrorResponse(
                    error_code="CONTRACTOR_RECORD_NOT_FOUND",
                    error_message=f"Financial records for '{contractor_id}' could not be located.",
                    recovery_guidance="Confirm contractor_id against registered database entries.",
                ).model_dump()
                return err

            single_limit = data.get("single_bonding_limit", 0.0)
            if single_limit <= 0:
                bonding_stat = BondingStatus.UNBONDED
                fin_risk = RiskLevel.CRITICAL
            elif req.target_project_value_usd > single_limit:
                bonding_stat = BondingStatus.EXCEEDED
                fin_risk = RiskLevel.HIGH
            elif req.target_project_value_usd > single_limit * 0.8:
                bonding_stat = BondingStatus.MARGINAL
                fin_risk = RiskLevel.MEDIUM
            else:
                bonding_stat = BondingStatus.ADEQUATE
                fin_risk = RiskLevel.LOW if data.get("dnb_paydex", 0) >= 75 else RiskLevel.MEDIUM

            if data.get("bankruptcy", False):
                fin_risk = RiskLevel.CRITICAL

            resp = FinancialRiskResponse(
                contractor_id=req.contractor_id,
                dnb_paydex_score=data.get("dnb_paydex", 70),
                financial_stress_score=data.get("financial_stress_score", 2),
                working_capital_usd=data.get("working_capital", 1_000_000.0),
                current_ratio=data.get("current_ratio", 1.5),
                single_project_bonding_limit_usd=single_limit,
                aggregate_bonding_limit_usd=data.get("aggregate_bonding_limit", 0.0),
                bonding_status=bonding_stat,
                bankruptcy_record_found=data.get("bankruptcy", False),
                financial_risk_level=fin_risk,
                bonding_underwriter=data.get("surety", "Unspecified"),
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="calculate_financial_risk_and_bonding",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"bonding_status": resp["bonding_status"], "financial_risk": resp["financial_risk_level"]},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            err = ToolErrorResponse(
                error_code="FINANCIAL_CALCULATION_ERROR",
                error_message=str(ex),
                recovery_guidance="Ensure target project value is a positive numerical value and retry.",
            ).model_dump()
            return err


# ==============================================================================
# TOOL 4: AUDIT WORKPLACE SAFETY AND EMR
# ==============================================================================

def audit_workplace_safety_and_emr(
    contractor_id: str,
    required_max_emr: float = 1.00,
) -> Dict[str, Any]:
    """Audit contractor workplace safety records, OSHA citations, TRIR, and Experience Modification Rate (EMR).

    Reviews historical workers' compensation risk data, 3-year rolling average EMR,
    OSHA 300 logs, DART incident rates, serious/willful OSHA violations, and safety program (IIPP/HASP)
    documentation to prevent jobsite safety liability.

    Args:
        contractor_id: Unique contractor identifier.
        required_max_emr: Maximum allowable Experience Modification Rate. Default is 1.00.

    Returns:
        A dictionary containing 3-year average EMR, EMR compliance boolean, TRIR/DART rates,
        OSHA citations list, and overall safety risk tier.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = audit_workplace_safety_and_emr("APEX-INFRA-01", 1.00)
        >>> print(res["emr_compliant"])
        True
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="audit_workplace_safety_and_emr",
        intended_action=f"Audit OSHA logs and 3-year EMR against threshold {required_max_emr:.2f} for {contractor_id}",
        input_parameters={"contractor_id": contractor_id, "required_max_emr": required_max_emr},
        rationale="Pillar 4 verification: enforce zero-fatality standards and worker safety compliance."
    )

    with TraceContext("tool.audit_safety_emr", {"contractor_id": contractor_id}):
        try:
            req = SafetyAuditRequest(contractor_id=contractor_id, required_max_emr=required_max_emr)
            data = MOCK_CONTRACTORS_DB.get(req.contractor_id)
            if not data:
                return ToolErrorResponse(
                    error_code="CONTRACTOR_RECORD_NOT_FOUND",
                    error_message=f"Safety logs for contractor '{contractor_id}' could not be located.",
                    recovery_guidance="Request Form 300A and NCCI Workers Comp EMR worksheet from contractor.",
                ).model_dump()

            emr = data.get("emr_3yr", 1.0)
            citations = [SafetyCitation(**c) for c in data.get("citations", [])]
            fatalities = data.get("fatalities_5yr", 0)

            # Determine safety risk tier
            if fatalities > 0 or any(c.severity == "Willful" for c in citations):
                safety_risk = RiskLevel.CRITICAL
            elif emr > 1.20 or any(c.severity == "Serious" for c in citations):
                safety_risk = RiskLevel.HIGH
            elif emr > 1.00:
                safety_risk = RiskLevel.MEDIUM
            else:
                safety_risk = RiskLevel.LOW

            resp = SafetyAuditResponse(
                contractor_id=req.contractor_id,
                experience_modification_rate_3yr_avg=emr,
                emr_compliant=(emr <= req.required_max_emr),
                total_recordable_incident_rate_trir=data.get("trir", 2.0),
                industry_average_trir=2.8,
                days_away_restricted_transferred_dart=data.get("dart", 1.0),
                fatalities_past_5_years=fatalities,
                osha_citations_past_3_years=citations,
                written_safety_program_verified=data.get("safety_program", True),
                safety_risk_level=safety_risk,
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="audit_workplace_safety_and_emr",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"emr": resp["experience_modification_rate_3yr_avg"], "safety_risk": resp["safety_risk_level"]},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            return ToolErrorResponse(
                error_code="SAFETY_AUDIT_ERROR",
                error_message=str(ex),
                recovery_guidance="Check parameters and ensure required_max_emr is positive.",
            ).model_dump()


# ==============================================================================
# TOOL 5: FETCH PAST PERFORMANCE AND REFERENCES
# ==============================================================================

def fetch_past_performance_and_references(
    contractor_id: str,
    min_project_similarity_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Retrieve historical project completion records, schedule/cost variance, and reference ratings.

    Evaluates past performance across public and commercial projects, assessing
    Earned Value Cost Performance Index (CPI), schedule adherence, quality ratings,
    and client rehire recommendation percentages to guarantee execution capability.

    Args:
        contractor_id: Unique contractor identifier.
        min_project_similarity_usd: Optional lower bound filter for contract value scale.

    Returns:
        A dictionary containing historical project list, average quality score (0-100),
        schedule adherence rate, and performance risk level.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = fetch_past_performance_and_references("APEX-INFRA-01")
        >>> print(res["average_quality_score"])
        94.0
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="fetch_past_performance_and_references",
        intended_action=f"Retrieve historical deliverables and references for {contractor_id}",
        input_parameters={"contractor_id": contractor_id, "min_project_similarity": min_project_similarity_usd},
        rationale="Pillar 5 verification: audit historical project execution, budget, and quality."
    )

    with TraceContext("tool.fetch_past_performance", {"contractor_id": contractor_id}):
        try:
            req = PastPerformanceRequest(contractor_id=contractor_id, min_project_similarity_usd=min_project_similarity_usd)
            data = MOCK_CONTRACTORS_DB.get(req.contractor_id)
            if not data:
                return ToolErrorResponse(
                    error_code="CONTRACTOR_RECORD_NOT_FOUND",
                    error_message=f"No performance history found for '{contractor_id}'.",
                    recovery_guidance="Check contractor ID or request customer reference package.",
                ).model_dump()

            raw_projects = data.get("projects", [])
            filtered = [
                ProjectPerformanceRecord(**p)
                for p in raw_projects
                if req.min_project_similarity_usd is None or p.get("contract_value_usd", 0) >= req.min_project_similarity_usd
            ]

            if not filtered:
                avg_quality = 0.0
                on_time_pct = 0.0
                rehire_pct = 0.0
                perf_risk = RiskLevel.HIGH
            else:
                avg_quality = sum(p.quality_score_out_of_100 for p in filtered) / len(filtered)
                on_time_pct = (sum(1 for p in filtered if p.schedule_performance != "DELAYED") / len(filtered)) * 100.0
                rehire_pct = (sum(1 for p in filtered if p.quality_score_out_of_100 >= 80) / len(filtered)) * 100.0
                perf_risk = RiskLevel.LOW if avg_quality >= 85 and on_time_pct >= 80 else RiskLevel.MEDIUM

            resp = PastPerformanceResponse(
                contractor_id=req.contractor_id,
                total_projects_reviewed=len(filtered),
                average_quality_score=round(avg_quality, 1),
                schedule_adherence_rate_pct=round(on_time_pct, 1),
                rehire_recommendation_rate_pct=round(rehire_pct, 1),
                project_records=filtered,
                performance_risk_level=perf_risk,
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="fetch_past_performance_and_references",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"projects_count": len(filtered), "avg_quality": avg_quality},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            return ToolErrorResponse(
                error_code="PAST_PERFORMANCE_ERROR",
                error_message=str(ex),
                recovery_guidance="Ensure contractor ID is valid and retry.",
            ).model_dump()


# ==============================================================================
# TOOL 6: HUMAN-IN-THE-LOOP (HITL) APPROVAL HOOK
# ==============================================================================

def request_human_oversight_approval(
    contractor_id: str,
    escalation_reason: str,
    risk_factors: List[str],
    proposed_mitigation: Optional[str] = None,
    authorized_role_required: str = "CHIEF_COMPLIANCE_OFFICER",
) -> Dict[str, Any]:
    """Trigger explicit Human-in-the-Loop (HITL) escalation when encountering high-risk or ambiguous vetting factors.

    Halts automated approval and registers a secure human review token whenever
    a contractor exhibits critical safety violations (EMR > 1.20), bonding shortfalls,
    potential sanctions name matches, or significant policy exceptions.

    Args:
        contractor_id: Unique contractor identifier.
        escalation_reason: Explicit rationale explaining why human authority is mandated.
        risk_factors: List of identified high-risk compliance or financial factors.
        proposed_mitigation: Proposed contractual or operational risk mitigations.
        authorized_role_required: Authority level needed (e.g. 'CHIEF_COMPLIANCE_OFFICER').

    Returns:
        A dictionary containing the generated escalation_token, approval status ('PENDING'),
        and instructions for the human compliance officer.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = request_human_oversight_approval(
        ...     "VORTEX-BUILD-02",
        ...     "EMR exceeds 1.20 benchmark (1.34) and OSHA serious citation found.",
        ...     ["EMR=1.34", "OSHA Serious Citation 2024"]
        ... )
        >>> print(res["approval_status"])
        'PENDING'
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="request_human_oversight_approval",
        intended_action=f"Trigger Human-in-the-Loop escalation for {contractor_id} due to: {escalation_reason}",
        input_parameters={"contractor_id": contractor_id, "escalation_reason": escalation_reason, "risk_factors": risk_factors},
        rationale="Governance rule: High-risk contractor approvals or exceptions mandate human oversight."
    )

    with TraceContext("tool.hitl_escalation", {"contractor_id": contractor_id}):
        try:
            req = HITLApprovalRequest(
                contractor_id=contractor_id,
                escalation_reason=escalation_reason,
                risk_factors=risk_factors,
                proposed_mitigation=proposed_mitigation,
                authorized_role_required=authorized_role_required,
            )

            # Register escalation via HITLManager
            from .hitl import HITLManager
            token = HITLManager.register_escalation(
                contractor_id=req.contractor_id,
                escalation_reason=req.escalation_reason,
                risk_factors=req.risk_factors,
                required_role=req.authorized_role_required,
                proposed_mitigation=req.proposed_mitigation,
            )

            resp = HITLApprovalResponse(
                escalation_token=token,
                contractor_id=req.contractor_id,
                approval_status=HITLStatus.PENDING,
                escalation_reason=req.escalation_reason,
                instructions_for_operator=f"Review risk factors: {', '.join(req.risk_factors)}. Use token {token} to authorize or reject via Human Review Panel."
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="request_human_oversight_approval",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"token": token, "status": "PENDING"},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            return ToolErrorResponse(
                error_code="HITL_ESCALATION_ERROR",
                error_message=str(ex),
                recovery_guidance="Provide explicit escalation reasons and non-empty risk factors list.",
            ).model_dump()


# ==============================================================================
# TOOL 7: FINALIZE CONTRACTOR VETTING DOSSIER
# ==============================================================================

def finalize_contractor_vetting_dossier(
    contractor_id: str,
    contractor_name: str,
    target_project_name: str,
    target_project_value_usd: float,
    decision: str,
    composite_risk_score_out_of_100: int,
    compliance_pillar_scores: Dict[str, int],
    executive_summary: str,
    mandatory_stipulations: Optional[List[str]] = None,
    human_approval_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate the official immutable contractor vetting dossier and compliance certificate.

    Produces the tamper-evident final audit certification containing composite risk
    scores across all 5 compliance pillars, legal determination, contractual stipulations,
    and a cryptographic SHA-256 integrity hash for audit trail provenance.

    Args:
        contractor_id: Unique contractor identifier.
        contractor_name: Official legal company name.
        target_project_name: Name or scope of target project.
        target_project_value_usd: Value of target procurement contract in USD.
        decision: Final determination ('APPROVED', 'CONDITIONALLY_APPROVED', 'REJECTED', 'ESCALATED_FOR_HUMAN_REVIEW').
        composite_risk_score_out_of_100: Weighted composite risk score from 0 (lowest) to 100 (critical).
        compliance_pillar_scores: Dictionary of scores (0-100) for all 5 pillars.
        executive_summary: Full compliance narrative and justification.
        mandatory_stipulations: Optional contractual covenants or risk conditions.
        human_approval_token: Optional authorization token if HITL was required.

    Returns:
        A dictionary containing dossier ID, cryptographic audit hash, certification timestamp,
        and formatted compliance certificate text.

    Raises:
        Does not raise unhandled exceptions; returns structured error payloads.

    Example:
        >>> res = finalize_contractor_vetting_dossier(
        ...     "APEX-INFRA-01", "Apex Infrastructure Solutions LLC",
        ...     "Clean Water Pipeline", 10_000_000.0, "APPROVED",
        ...     18, {"identity_sanctions": 100, "licensing_insurance": 95, "financial_bonding": 90, "safety_emr": 92, "past_performance": 94},
        ...     "Exemplary compliance across all pillars."
        ... )
        >>> print(res["final_decision"])
        'APPROVED'
    """
    start_time = time.time()
    intent_id = TelemetryCollector.log_intent(
        tool_name="finalize_contractor_vetting_dossier",
        intended_action=f"Generate final vetting dossier and certificate for {contractor_name} ({decision})",
        input_parameters={"contractor_id": contractor_id, "decision": decision, "composite_risk_score": composite_risk_score_out_of_100},
        rationale="Final Adjudication: certify contractor vetting determination and create immutable audit trail."
    )

    with TraceContext("tool.finalize_dossier", {"contractor_id": contractor_id, "decision": decision}):
        try:
            # Validate input arguments
            req = VettingDossierRequest(
                contractor_id=contractor_id,
                contractor_name=contractor_name,
                target_project_name=target_project_name,
                target_project_value_usd=target_project_value_usd,
                decision=VettingDecision(decision.upper()),
                composite_risk_score_out_of_100=composite_risk_score_out_of_100,
                compliance_pillar_scores=compliance_pillar_scores,
                executive_summary=executive_summary,
                mandatory_stipulations=mandatory_stipulations or [],
                human_approval_token=human_approval_token,
            )

            # Assign risk level
            if req.composite_risk_score_out_of_100 <= 30:
                tier = RiskLevel.LOW
            elif req.composite_risk_score_out_of_100 <= 60:
                tier = RiskLevel.MEDIUM
            elif req.composite_risk_score_out_of_100 <= 80:
                tier = RiskLevel.HIGH
            else:
                tier = RiskLevel.CRITICAL

            now_iso = datetime.now(timezone.utc).isoformat()
            dossier_id = f"DOS-{datetime.now(timezone.utc).year}-{contractor_id}-{int(time.time()) % 10000:04d}"

            # Calculate SHA-256 integrity hash
            hash_payload = f"{dossier_id}|{req.contractor_id}|{req.decision.value}|{req.composite_risk_score_out_of_100}|{now_iso}"
            audit_hash = hashlib.sha256(hash_payload.encode()).hexdigest()

            stip_text = "\n".join([f"  - {s}" for s in req.mandatory_stipulations]) if req.mandatory_stipulations else "  - None (Unconditional)"
            cert_text = (
                f"====================================================================\n"
                f"       OFFICIAL CONTRACTOR VETTING COMPLIANCE CERTIFICATE          \n"
                f"====================================================================\n"
                f"Dossier ID:           {dossier_id}\n"
                f"Contractor:           {req.contractor_name} ({req.contractor_id})\n"
                f"Target Scope:         {req.target_project_name} (${req.target_project_value_usd:,.2f})\n"
                f"Final Determination:  {req.decision.value}\n"
                f"Composite Risk:       {req.composite_risk_score_out_of_100}/100 ({tier.value} RISK)\n"
                f"Pillar Breakdown:\n"
                f"  * Identity & Sanctions:     {req.compliance_pillar_scores.get('identity_sanctions', 'N/A')}/100\n"
                f"  * Licensing & Insurance:    {req.compliance_pillar_scores.get('licensing_insurance', 'N/A')}/100\n"
                f"  * Financial & Bonding:      {req.compliance_pillar_scores.get('financial_bonding', 'N/A')}/100\n"
                f"  * Safety & EMR Compliance:  {req.compliance_pillar_scores.get('safety_emr', 'N/A')}/100\n"
                f"  * Past Performance:         {req.compliance_pillar_scores.get('past_performance', 'N/A')}/100\n"
                f"Mandatory Stipulations:\n{stip_text}\n"
                f"Audit Hash (SHA-256): {audit_hash}\n"
                f"Certified At:         {now_iso}\n"
                f"===================================================================="
            )

            resp = VettingDossierResponse(
                dossier_id=dossier_id,
                contractor_id=req.contractor_id,
                contractor_name=req.contractor_name,
                final_decision=req.decision,
                composite_risk_score=req.composite_risk_score_out_of_100,
                composite_risk_level=tier,
                certification_timestamp=now_iso,
                audit_hash=audit_hash,
                certificate_text=cert_text,
            ).model_dump()

            TelemetryCollector.log_outcome(
                tool_name="finalize_contractor_vetting_dossier",
                execution_time_ms=(time.time() - start_time) * 1000,
                status="SUCCESS",
                result_summary={"dossier_id": dossier_id, "final_decision": resp["final_decision"]},
                intent_id=intent_id,
            )
            return resp

        except Exception as ex:
            return ToolErrorResponse(
                error_code="DOSSIER_FINALIZATION_ERROR",
                error_message=str(ex),
                recovery_guidance="Verify all 5 pillar scores (0-100) and decision enum value ('APPROVED', 'CONDITIONALLY_APPROVED', 'REJECTED', 'ESCALATED_FOR_HUMAN_REVIEW').",
            ).model_dump()
