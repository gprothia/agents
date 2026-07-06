"""Benefits & Payroll MCP server.

Read-only, but intentionally returns sensitive PII (SSN, bank last-4, salary)
in raw responses. This is the server that demonstrates Agent Gateway's
CONTENT_AUTHZ extension: Model Armor + Sensitive Data Protection intercepts
the response in-flight and redacts/deidentifies SSNs before the agent (and
therefore the user in Gemini Enterprise) ever sees them.
"""

import os
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "benefits-payroll",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    stateless_http=True,
)

PAYROLL = {
    "E1001": {
        "name": "Priya Sharma",
        "ssn": "543-21-9876",          # <-- redacted in flight by Model Armor/SDP
        "base_salary_usd": 198000,
        "pay_frequency": "semi-monthly",
        "bank_account_last4": "4821",
        "last_payslip": {
            "period": "2026-06-01 to 2026-06-15",
            "gross": 8250.00,
            "net": 5612.34,
            "deductions": {"federal_tax": 1650.00, "state_tax": 618.66, "401k": 660.00, "medical": 209.00},
        },
    },
    "E1002": {
        "name": "Marcus Webb",
        "ssn": "512-44-3310",
        "base_salary_usd": 142000,
        "pay_frequency": "semi-monthly",
        "bank_account_last4": "9042",
        "last_payslip": {
            "period": "2026-06-01 to 2026-06-15",
            "gross": 5916.67,
            "net": 4188.90,
            "deductions": {"federal_tax": 1120.00, "state_tax": 0.0, "401k": 473.33, "medical": 134.44},
        },
    },
}

BENEFITS = {
    "E1001": {"medical_plan": "PPO Gold", "dental": "Delta Premier", "vision": "VSP Choice",
              "401k_match": "100% of first 4%", "hsa_balance_usd": 3120.50, "pto_balance_days": 12.5},
    "E1002": {"medical_plan": "HMO Standard", "dental": "Delta Basic", "vision": "None",
              "401k_match": "100% of first 4%", "hsa_balance_usd": 0.0, "pto_balance_days": 6.0},
}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_payslip(employee_id: str) -> dict:
    """Return the most recent payslip for an employee, including gross/net pay
    and deductions. Response contains sensitive payroll PII."""
    rec = PAYROLL.get(employee_id)
    if not rec:
        return {"error": f"No payroll record for '{employee_id}'."}
    return rec


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_benefits_summary(employee_id: str) -> dict:
    """Return current benefits enrollment, 401k match, HSA balance and PTO balance."""
    rec = BENEFITS.get(employee_id)
    if not rec:
        return {"error": f"No benefits record for '{employee_id}'."}
    return rec


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
