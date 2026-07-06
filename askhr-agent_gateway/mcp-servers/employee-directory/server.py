"""Employee Directory MCP server.

Read-only HR lookup tools. Every tool carries readOnlyHint=True so that
Agent Gateway can publish mcp.tool.isReadOnly=true to IAP CEL conditions,
letting you write policies like "this agent may only call read-only tools".
"""

import os
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "employee-directory",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8080)),
    stateless_http=True,
)

# --- Mock HR data store (replace with Workday/SAP/BambooHR API calls) ---
EMPLOYEES = {
    "E1001": {
        "employee_id": "E1001",
        "name": "Priya Sharma",
        "title": "Senior Software Engineer",
        "department": "Platform Engineering",
        "manager_id": "E1004",
        "location": "Sunnyvale, CA",
        "email": "priya.sharma@example.com",
        "hire_date": "2021-03-15",
    },
    "E1002": {
        "employee_id": "E1002",
        "name": "Marcus Webb",
        "title": "HR Business Partner",
        "department": "People Operations",
        "manager_id": "E1005",
        "location": "Austin, TX",
        "email": "marcus.webb@example.com",
        "hire_date": "2019-08-01",
    },
    "E1004": {
        "employee_id": "E1004",
        "name": "Dana Okafor",
        "title": "Engineering Manager",
        "department": "Platform Engineering",
        "manager_id": "E1005",
        "location": "Sunnyvale, CA",
        "email": "dana.okafor@example.com",
        "hire_date": "2018-01-10",
    },
    "E1005": {
        "employee_id": "E1005",
        "name": "Luis Herrera",
        "title": "VP, Engineering & People",
        "department": "Executive",
        "manager_id": None,
        "location": "Sunnyvale, CA",
        "email": "luis.herrera@example.com",
        "hire_date": "2015-06-22",
    },
}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def lookup_employee(query: str) -> dict:
    """Look up an employee by ID, name, or email. Returns directory profile
    (name, title, department, manager, location). No compensation data."""
    q = query.strip().lower()
    for emp in EMPLOYEES.values():
        if q in (emp["employee_id"].lower(), emp["name"].lower(), emp["email"].lower()):
            return emp
    matches = [e for e in EMPLOYEES.values() if q in e["name"].lower()]
    if matches:
        return {"matches": matches}
    return {"error": f"No employee found matching '{query}'."}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_org_chart(employee_id: str) -> dict:
    """Return the reporting chain (up) and direct reports (down) for an employee."""
    emp = EMPLOYEES.get(employee_id)
    if not emp:
        return {"error": f"Unknown employee_id '{employee_id}'."}
    chain, cursor = [], emp
    while cursor and cursor.get("manager_id"):
        cursor = EMPLOYEES.get(cursor["manager_id"])
        if cursor:
            chain.append({"employee_id": cursor["employee_id"], "name": cursor["name"], "title": cursor["title"]})
    reports = [
        {"employee_id": e["employee_id"], "name": e["name"], "title": e["title"]}
        for e in EMPLOYEES.values()
        if e.get("manager_id") == employee_id
    ]
    return {"employee": emp["name"], "reporting_chain": chain, "direct_reports": reports}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def search_hr_policies(topic: str) -> dict:
    """Search company HR policy summaries (PTO, parental leave, remote work, expenses)."""
    policies = {
        "pto": "Employees accrue 20 days of PTO per year, capped at 30 days. Requests over 10 consecutive days need VP approval.",
        "parental leave": "16 weeks fully paid for all new parents, usable within 12 months of birth or adoption.",
        "remote work": "Hybrid policy: minimum 2 in-office days per week. Fully-remote requires director approval.",
        "expenses": "Reimbursable within 30 days via the expenses portal. Meals capped at $75/day when traveling.",
    }
    t = topic.strip().lower()
    hits = {k: v for k, v in policies.items() if t in k or k in t}
    return hits or {"error": f"No policy found for '{topic}'.", "available_topics": list(policies)}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
