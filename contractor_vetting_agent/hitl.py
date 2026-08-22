"""Human-in-the-Loop (HITL) Governance & Code Stop Framework.

Enforces mandatory human authorization for high-stakes decisions:
- Critical safety exceptions (EMR > 1.20)
- Potential sanctions/debarment name match overrides
- Single-project bonding limit exceptions
- Final contract certification for High Risk tier contractors
"""

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
from .schemas import HITLStatus
from .telemetry import get_structured_logger

logger = get_structured_logger("contractor_vetting.hitl")


class PendingEscalation:
    """Represents an active human-in-the-loop escalation awaiting review."""

    def __init__(
        self,
        token: str,
        contractor_id: str,
        escalation_reason: str,
        risk_factors: List[str],
        required_role: str = "CHIEF_COMPLIANCE_OFFICER",
        proposed_mitigation: Optional[str] = None,
    ):
        self.token = token
        self.contractor_id = contractor_id
        self.escalation_reason = escalation_reason
        self.risk_factors = risk_factors
        self.required_role = required_role
        self.proposed_mitigation = proposed_mitigation
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.status = HITLStatus.PENDING
        self.reviewed_by: Optional[str] = None
        self.review_timestamp: Optional[str] = None
        self.decision_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "contractor_id": self.contractor_id,
            "escalation_reason": self.escalation_reason,
            "risk_factors": self.risk_factors,
            "required_role": self.required_role,
            "proposed_mitigation": self.proposed_mitigation,
            "created_at": self.created_at,
            "status": self.status.value,
            "reviewed_by": self.reviewed_by,
            "review_timestamp": self.review_timestamp,
            "decision_notes": self.decision_notes,
        }


class HITLManager:
    """Manages Human-in-the-Loop escalation registry and authorization validation."""

    _escalations: Dict[str, PendingEscalation] = {}

    @classmethod
    def register_escalation(
        cls,
        contractor_id: str,
        escalation_reason: str,
        risk_factors: List[str],
        required_role: str = "CHIEF_COMPLIANCE_OFFICER",
        proposed_mitigation: Optional[str] = None,
    ) -> str:
        """Register a new human code-stop and return an escalation token."""
        raw = f"{contractor_id}:{escalation_reason}:{datetime.now(timezone.utc).isoformat()}"
        token = f"HITL-AUTH-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"

        escalation = PendingEscalation(
            token=token,
            contractor_id=contractor_id,
            escalation_reason=escalation_reason,
            risk_factors=risk_factors,
            required_role=required_role,
            proposed_mitigation=proposed_mitigation,
        )
        cls._escalations[token] = escalation
        logger.warning(
            f"HITL Code-Stop Registered: {token} for {contractor_id} (Reason: {escalation_reason})",
            extra={"contractor_id": contractor_id, "token": token, "required_role": required_role}
        )
        return token

    @classmethod
    def get_escalation(cls, token: str) -> Optional[PendingEscalation]:
        """Retrieve escalation by token."""
        return cls._escalations.get(token)

    @classmethod
    def authorize_escalation(
        cls,
        token: str,
        reviewer_name: str,
        reviewer_role: str,
        approved: bool,
        notes: str,
    ) -> Dict[str, Any]:
        """Human reviewer submits determination for pending escalation."""
        esc = cls._escalations.get(token)
        if not esc:
            return {"status": "error", "message": f"Invalid or expired escalation token '{token}'."}

        if reviewer_role != esc.required_role and reviewer_role != "SYSTEM_ADMINISTRATOR":
            return {
                "status": "error",
                "message": f"Reviewer role '{reviewer_role}' lacks authority. Required role is '{esc.required_role}'."
            }

        esc.status = HITLStatus.APPROVED if approved else HITLStatus.REJECTED
        esc.reviewed_by = f"{reviewer_name} ({reviewer_role})"
        esc.review_timestamp = datetime.now(timezone.utc).isoformat()
        esc.decision_notes = notes

        logger.info(
            f"HITL Determination Submitted: {token} -> {esc.status.value} by {reviewer_name}",
            extra={"token": token, "status": esc.status.value, "reviewed_by": esc.reviewed_by}
        )

        return {
            "status": "success",
            "token": token,
            "approval_status": esc.status.value,
            "reviewed_by": esc.reviewed_by,
            "review_timestamp": esc.review_timestamp,
        }

    @classmethod
    def verify_token_validity(cls, token: Optional[str]) -> bool:
        """Verify whether an escalation token is valid and approved by a human."""
        if not token:
            return False
        esc = cls._escalations.get(token)
        if not esc:
            return False
        return esc.status == HITLStatus.APPROVED
