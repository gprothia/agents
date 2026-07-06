"""HR Actions MCP server.

WRITE tools (readOnlyHint=False / destructiveHint on the risky one).
This is the server you use to demonstrate identity-based tool governance:
grant the askHR agent iap.egressor on this server WITH the CEL condition
  api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true
and every tool here returns 403 PermissionDenied through Agent Gateway,
while the two read-only servers keep working.
"""

import os
import uuid
from datetime import date
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "hr-actions",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    stateless_http=True,
)

PTO_REQUESTS: dict[str, dict] = {}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def submit_pto_request(employee_id: str, start_date: str, end_date: str, reason: str = "") -> dict:
    """Submit a paid-time-off request for approval. WRITE operation."""
    req_id = f"PTO-{uuid.uuid4().hex[:8].upper()}"
    PTO_REQUESTS[req_id] = {
        "request_id": req_id,
        "employee_id": employee_id,
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason,
        "status": "PENDING_MANAGER_APPROVAL",
        "submitted_on": date.today().isoformat(),
    }
    return PTO_REQUESTS[req_id]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
def update_bank_details(employee_id: str, routing_number: str, account_number: str) -> dict:
    """Update the direct-deposit bank account for payroll. WRITE + destructive.
    Prime target for prompt-injection-driven payroll fraud — exactly the kind
    of tool Agent Gateway policies should deny to a general-purpose HR agent."""
    return {
        "employee_id": employee_id,
        "status": "UPDATED",
        "account_last4": account_number[-4:],
        "effective": "next pay cycle",
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
def file_hr_case(employee_id: str, category: str, description: str) -> dict:
    """Open an HR case (grievance, accommodation, payroll dispute). WRITE operation."""
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    return {"case_id": case_id, "employee_id": employee_id, "category": category,
            "status": "OPEN", "opened_on": date.today().isoformat()}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
