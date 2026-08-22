"""Strict Pydantic schemas and enums for Contractor Vetting Agent.

Defines input/output schemas, type validations, field constraints, enums,
and guided error responses adhering to strict typing and validation standards.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# ENUMS
# ==============================================================================

class LicenseStatus(str, Enum):
    """Status of contractor state license."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    NOT_FOUND = "NOT_FOUND"


class InsuranceStatus(str, Enum):
    """Status of contractor insurance policy."""
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    INSUFFICIENT_LIMITS = "INSUFFICIENT_LIMITS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    NOT_PROVIDED = "NOT_PROVIDED"


class SanctionsRiskTier(str, Enum):
    """Risk tier from sanctions and debarment screening."""
    CLEAR = "CLEAR"
    POTENTIAL_MATCH = "POTENTIAL_MATCH"
    CONFIRMED_SANCTIONED = "CONFIRMED_SANCTIONED"
    DEBARRED = "DEBARRED"


class RiskLevel(str, Enum):
    """Overall calculated risk level."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BondingStatus(str, Enum):
    """Status of contractor surety bonding capacity."""
    ADEQUATE = "ADEQUATE"
    MARGINAL = "MARGINAL"
    INSUFFICIENT = "INSUFFICIENT"
    EXCEEDED = "EXCEEDED"
    UNBONDED = "UNBONDED"


class VettingDecision(str, Enum):
    """Final determination for contractor vetting."""
    APPROVED = "APPROVED"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    REJECTED = "REJECTED"
    ESCALATED_FOR_HUMAN_REVIEW = "ESCALATED_FOR_HUMAN_REVIEW"


class HITLStatus(str, Enum):
    """Status of Human-in-the-Loop approval."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# ==============================================================================
# GUIDED ERROR HANDLING SCHEMA
# ==============================================================================

class ToolErrorResponse(BaseModel):
    """Structured error model returning guided recovery instructions to LLMs."""
    status: str = Field(default="error", description="Always 'error' when an operation fails.")
    error_code: str = Field(..., description="Machine-readable unique error code (e.g. INVALID_EIN_FORMAT).")
    error_message: str = Field(..., description="Human-readable description of what went wrong.")
    recovery_guidance: str = Field(..., description="Actionable step-by-step instructions for the LLM to recover.")
    suggested_retry_parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Recommended parameter corrections or fallback values for subsequent attempts."
    )


# ==============================================================================
# TOOL 1: LICENSE & INSURANCE SCHEMAS
# ==============================================================================

class LicenseVerificationRequest(BaseModel):
    """Request schema for validating contractor license and insurance."""
    contractor_id: str = Field(..., description="Unique contractor ID or slug (e.g. 'APEX-INFRA-01').")
    license_number: str = Field(..., description="State contractor license number.", min_length=3, max_length=30)
    state: str = Field(..., description="Two-letter US state code (e.g. 'CA', 'TX', 'NY').", min_length=2, max_length=2)
    required_general_liability_min: float = Field(
        default=1_000_000.0,
        description="Minimum required General Liability coverage per occurrence in USD.",
        ge=100_000.0
    )
    required_workers_comp_min: float = Field(
        default=500_000.0,
        description="Minimum required Workers Compensation coverage in USD.",
        ge=100_000.0
    )

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.upper().strip()


class PolicyDetail(BaseModel):
    """Details of a single insurance policy."""
    policy_type: str = Field(..., description="Type of policy (General Liability, Workers Comp, Umbrella).")
    carrier_name: str = Field(..., description="Underwriting insurance carrier name.")
    am_best_rating: str = Field(..., description="A.M. Best Financial Strength Rating (e.g. 'A+', 'A-').")
    coverage_limit_usd: float = Field(..., description="Coverage limit per occurrence in USD.")
    expiration_date: str = Field(..., description="Policy expiration date in YYYY-MM-DD format.")
    is_active: bool = Field(..., description="Whether the policy is currently active.")
    additional_insured_endorsed: bool = Field(..., description="Whether client is named as Additional Insured.")


class LicenseVerificationResponse(BaseModel):
    """Response schema for license and insurance verification."""
    status: str = Field(default="success", description="Result status ('success' or 'error').")
    contractor_id: str = Field(..., description="Contractor identifier.")
    license_number: str = Field(..., description="Verified license number.")
    state: str = Field(..., description="State of licensure.")
    license_status: LicenseStatus = Field(..., description="Current license status.")
    license_type: str = Field(..., description="Classification (e.g. 'General Building Contractor Class A').")
    license_expiration: str = Field(..., description="License expiration date in YYYY-MM-DD.")
    disciplinary_actions_found: bool = Field(..., description="Whether state disciplinary records exist.")
    insurance_status: InsuranceStatus = Field(..., description="Overall insurance compliance status.")
    policies: List[PolicyDetail] = Field(default_factory=list, description="Verified insurance policies.")
    compliance_summary: str = Field(..., description="Concise summary of compliance findings.")


# ==============================================================================
# TOOL 2: SANCTIONS & DEBARMENT SCHEMAS
# ==============================================================================

class SanctionsScreeningRequest(BaseModel):
    """Request schema for screening contractor against sanctions and debarment lists."""
    contractor_name: str = Field(..., description="Official legal entity name.", min_length=2)
    tax_id_ein: str = Field(..., description="Federal Employer Identification Number formatted as 'XX-XXXXXXX' or 9 digits.")
    country: str = Field(default="US", description="Two-letter ISO country code.", min_length=2, max_length=2)
    principal_names: Optional[List[str]] = Field(
        default=None,
        description="List of key officers, owners, or principals to screen alongside the entity."
    )

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        return v.upper().strip()


class SanctionMatch(BaseModel):
    """Details of a potential or confirmed sanctions list match."""
    list_source: str = Field(..., description="Source database (e.g. 'SAM.gov EPLS', 'OFAC SDN', 'World Bank Debarment').")
    matched_entity: str = Field(..., description="Name or identifier matched in list.")
    match_confidence: float = Field(..., description="Confidence score from 0.0 to 1.0.", ge=0.0, le=1.0)
    program: str = Field(..., description="Sanctions program or exclusion authority.")
    effective_date: str = Field(..., description="Date exclusion took effect.")
    details: str = Field(..., description="Narrative description of the exclusion.")


class SanctionsScreeningResponse(BaseModel):
    """Response schema for sanctions and debarment screening."""
    status: str = Field(default="success", description="Result status ('success' or 'error').")
    contractor_name: str = Field(..., description="Entity name screened.")
    tax_id_ein_masked: str = Field(..., description="Masked Tax ID (e.g. 'XX-XXX1234') for PII safety.")
    risk_tier: SanctionsRiskTier = Field(..., description="Assessed sanctions risk tier.")
    sam_gov_active_registration: bool = Field(..., description="Whether active in SAM.gov registry.")
    cage_code: Optional[str] = Field(default=None, description="Commercial and Government Entity (CAGE) Code if available.")
    matches_found: List[SanctionMatch] = Field(default_factory=list, description="List of match records.")
    adjudication_guidance: str = Field(..., description="Recommended compliance action.")


# ==============================================================================
# TOOL 3: FINANCIAL RISK & BONDING SCHEMAS
# ==============================================================================

class FinancialRiskRequest(BaseModel):
    """Request schema for evaluating contractor financial stability and bonding capacity."""
    contractor_id: str = Field(..., description="Unique contractor ID.")
    target_project_value_usd: float = Field(..., description="Estimated contract value for target project.", gt=0.0)
    annual_revenue_usd: Optional[float] = Field(default=None, description="Reported trailing twelve-month revenue.", gt=0.0)


class FinancialRiskResponse(BaseModel):
    """Response schema for financial health and bonding capacity."""
    status: str = Field(default="success", description="Result status ('success' or 'error').")
    contractor_id: str = Field(..., description="Contractor ID.")
    dnb_paydex_score: int = Field(..., description="Dun & Bradstreet Paydex credit score (0-100).", ge=0, le=100)
    financial_stress_score: int = Field(..., description="Financial Stress Score class (1-5, 1 is lowest risk).", ge=1, le=5)
    working_capital_usd: float = Field(..., description="Calculated working capital in USD.")
    current_ratio: float = Field(..., description="Current assets divided by current liabilities.")
    single_project_bonding_limit_usd: float = Field(..., description="Surety maximum bonding capacity for single project.")
    aggregate_bonding_limit_usd: float = Field(..., description="Surety maximum aggregate bonding capacity.")
    bonding_status: BondingStatus = Field(..., description="Adequacy of bonding for target project value.")
    bankruptcy_record_found: bool = Field(..., description="Whether bankruptcy filings were discovered in past 7 years.")
    financial_risk_level: RiskLevel = Field(..., description="Overall financial risk classification.")
    bonding_underwriter: str = Field(..., description="Treasury-listed surety underwriter name.")


# ==============================================================================
# TOOL 4: SAFETY & EMR AUDIT SCHEMAS
# ==============================================================================

class SafetyAuditRequest(BaseModel):
    """Request schema for auditing workplace safety and Experience Modification Rate."""
    contractor_id: str = Field(..., description="Contractor ID.")
    required_max_emr: float = Field(
        default=1.00,
        description="Maximum allowable Experience Modification Rate (standard industry benchmark is 1.00).",
        gt=0.0,
        le=3.0
    )


class SafetyCitation(BaseModel):
    """OSHA or regulatory safety citation record."""
    citation_id: str = Field(..., description="OSHA inspection or citation identifier.")
    inspection_date: str = Field(..., description="Date of inspection.")
    severity: str = Field(..., description="Severity classification ('Other-than-Serious', 'Serious', 'Willful', 'Repeat').")
    standard_violated: str = Field(..., description="OSHA CFR standard violated (e.g. '1926.501(b)(1) Fall Protection').")
    penalty_amount_usd: float = Field(..., description="Assessed penalty in USD.")
    status: str = Field(..., description="Status ('Closed', 'Contested', 'Open').")


class SafetyAuditResponse(BaseModel):
    """Response schema for safety metrics and EMR audit."""
    status: str = Field(default="success", description="Result status ('success' or 'error').")
    contractor_id: str = Field(..., description="Contractor ID.")
    experience_modification_rate_3yr_avg: float = Field(..., description="3-year rolling average EMR.")
    emr_compliant: bool = Field(..., description="Whether EMR meets or exceeds requirement.")
    total_recordable_incident_rate_trir: float = Field(..., description="TRIR per 100 full-time workers.")
    industry_average_trir: float = Field(default=2.8, description="BLS benchmark TRIR for industry NAICS.")
    days_away_restricted_transferred_dart: float = Field(..., description="DART incident rate.")
    fatalities_past_5_years: int = Field(..., description="Workplace fatalities recorded in last 5 years.", ge=0)
    osha_citations_past_3_years: List[SafetyCitation] = Field(default_factory=list, description="OSHA citations.")
    written_safety_program_verified: bool = Field(..., description="Whether verified written IIPP/HASP is on file.")
    safety_risk_level: RiskLevel = Field(..., description="Safety risk classification.")


# ==============================================================================
# TOOL 5: PAST PERFORMANCE & REFERENCES SCHEMAS
# ==============================================================================

class PastPerformanceRequest(BaseModel):
    """Request schema for retrieving past performance and reference surveys."""
    contractor_id: str = Field(..., description="Contractor identifier.")
    min_project_similarity_usd: Optional[float] = Field(
        default=None,
        description="Filter for past projects of comparable scale."
    )


class ProjectPerformanceRecord(BaseModel):
    """Evaluation record of a completed project."""
    project_name: str = Field(..., description="Project title.")
    client_name: str = Field(..., description="Client or owner organization.")
    contract_value_usd: float = Field(..., description="Final project value.")
    completed_year: int = Field(..., description="Year of substantial completion.")
    schedule_performance: str = Field(..., description="Schedule rating ('ON_TIME', 'AHEAD_OF_SCHEDULE', 'DELAYED').")
    cost_performance_index_cpi: float = Field(..., description="Earned value CPI (>1.0 is under budget).")
    quality_score_out_of_100: int = Field(..., description="Client satisfaction score (0-100).", ge=0, le=100)
    cpars_overall_rating: str = Field(..., description="CPARS equivalent rating ('Exceptional', 'Very Good', 'Satisfactory', 'Marginal', 'Unsatisfactory').")


class PastPerformanceResponse(BaseModel):
    """Response schema for past project performance history."""
    status: str = Field(default="success", description="Result status ('success' or 'error').")
    contractor_id: str = Field(..., description="Contractor ID.")
    total_projects_reviewed: int = Field(..., description="Number of past projects audited.")
    average_quality_score: float = Field(..., description="Aggregate quality score (0-100).")
    schedule_adherence_rate_pct: float = Field(..., description="Percentage of projects completed on time.")
    rehire_recommendation_rate_pct: float = Field(..., description="Percentage of past clients willing to rehire.")
    project_records: List[ProjectPerformanceRecord] = Field(default_factory=list, description="Historical projects.")
    performance_risk_level: RiskLevel = Field(..., description="Past performance risk classification.")


# ==============================================================================
# TOOL 6: HUMAN-IN-THE-LOOP (HITL) HOOK SCHEMAS
# ==============================================================================

class HITLApprovalRequest(BaseModel):
    """Request schema for initiating Human-in-the-Loop escalation."""
    contractor_id: str = Field(..., description="Contractor ID.")
    escalation_reason: str = Field(..., description="Explicit rationale triggering mandatory human review.")
    risk_factors: List[str] = Field(..., description="List of identified high-risk factors.")
    proposed_mitigation: Optional[str] = Field(default=None, description="Proposed risk mitigation terms.")
    authorized_role_required: str = Field(
        default="CHIEF_COMPLIANCE_OFFICER",
        description="Required approver authority role."
    )


class HITLApprovalResponse(BaseModel):
    """Response schema from HITL escalation initiation."""
    status: str = Field(default="success", description="Result status.")
    escalation_token: str = Field(..., description="Unique opaque token tracking this pending human review.")
    contractor_id: str = Field(..., description="Contractor ID.")
    approval_status: HITLStatus = Field(default=HITLStatus.PENDING, description="Current approval status.")
    escalation_reason: str = Field(..., description="Reason for escalation.")
    instructions_for_operator: str = Field(..., description="Next steps for human reviewer.")


# ==============================================================================
# TOOL 7: FINAL VETTING DOSSIER SCHEMAS
# ==============================================================================

class VettingDossierRequest(BaseModel):
    """Request schema for finalizing contractor vetting dossier and certificate."""
    contractor_id: str = Field(..., description="Contractor ID.")
    contractor_name: str = Field(..., description="Official legal name.")
    target_project_name: str = Field(..., description="Target project scope.")
    target_project_value_usd: float = Field(..., description="Target contract value in USD.")
    decision: VettingDecision = Field(..., description="Final vetting decision determination.")
    composite_risk_score_out_of_100: int = Field(
        ...,
        description="Composite risk score (0-100, where <=30 is Low, 31-60 is Medium, >60 is High).",
        ge=0,
        le=100
    )
    compliance_pillar_scores: Dict[str, int] = Field(
        ...,
        description="Scores out of 100 for each of the 5 pillars: identity_sanctions, licensing_insurance, financial_bonding, safety_emr, past_performance."
    )
    executive_summary: str = Field(..., description="Executive compliance narrative and justification.")
    mandatory_stipulations: List[str] = Field(
        default_factory=list,
        description="Contractual conditions or mandatory risk mitigation clauses."
    )
    human_approval_token: Optional[str] = Field(
        default=None,
        description="Approval token if decision required human sign-off."
    )


class VettingDossierResponse(BaseModel):
    """Response schema containing official certified vetting dossier."""
    status: str = Field(default="success", description="Result status.")
    dossier_id: str = Field(..., description="Unique immutable dossier certification ID (e.g. 'DOS-2026-APEX-0982').")
    contractor_id: str = Field(..., description="Contractor ID.")
    contractor_name: str = Field(..., description="Contractor name.")
    final_decision: VettingDecision = Field(..., description="Certified vetting decision.")
    composite_risk_score: int = Field(..., description="Composite risk score.")
    composite_risk_level: RiskLevel = Field(..., description="Risk tier.")
    certification_timestamp: str = Field(..., description="ISO-8601 timestamp of certification.")
    audit_hash: str = Field(..., description="Cryptographic SHA-256 integrity hash of audit record.")
    certificate_text: str = Field(..., description="Full text compliance certificate.")
