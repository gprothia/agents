"""Run the whole pipeline WITHOUT the LLM, so you can see it end-to-end immediately.

This scripts the discovery answers a user would give, then exercises the real tools:
grounding -> recommendation (pros/cons) -> save to plan sheet -> A2UI surface. Then run
`python deploy_agent.py` to turn the plan sheet into Terraform.

Usage:  python run_simulated.py
"""
from __future__ import annotations
import json
import os

from ge_agent import recommend, plan_sheet, a2ui

PLAN = plan_sheet.PLAN_PATH


def show_rec(rec: dict):
    print(f"  Recommend: {rec['title']}")
    print(f"    {rec['summary']}   (one-way: {'YES' if rec['one_way'] else 'no'})")
    print("    Pros:")
    for p in rec["pros"]:
        print(f"      + {p}")
    print("    Watch-outs:")
    for w in rec["watchouts"]:
        print(f"      ! {w}")
    print(f"    Source: {rec['source_url']}")


def main():
    # start clean so re-runs are readable
    if os.path.exists(PLAN):
        os.remove(PLAN)

    print("=" * 70)
    print("SIMULATED DISCOVERY -> RECOMMENDATION -> DECISION  (no LLM)")
    print("=" * 70)

    # ---- Area 1: Infrastructure (one-way; do first) --------------------
    print("\n[Infrastructure]  answers: residency=eu, encryption=cmek")
    infra = recommend.recommend_infra_config(residency="eu", encryption="cmek")
    show_rec(infra)
    saved1 = plan_sheet.save_decision(infra)
    print(f"  -> approved & saved as {saved1['id']}")

    # ---- Area 2: App setup --------------------------------------------
    print("\n[App setup]  answers: audience=all_employees, capability=search_summarize")
    app = recommend.recommend_app_config(audience="all_employees", capability="search_summarize")
    show_rec(app)
    saved2 = plan_sheet.save_decision(app)
    print(f"  -> approved & saved as {saved2['id']}")

    # ---- Area 3: Gmail connector (guided, depends on infra) -----------
    print("\n[Gmail connector]  answers: all_users, messages+attachments, with_actions, daily")
    gmail = recommend.recommend_connector_config(
        scope="all_users", index_what="messages_attachments", actions="with_actions", sync="daily")
    show_rec(gmail)
    print("    Prerequisites the agent walks through (must be confirmed before saving):")
    for pre in gmail.get("prerequisites", []):
        print(f"      - {pre}")
    print("    [user confirms prerequisites and approves]")
    saved3 = plan_sheet.save_decision(gmail)
    print(f"  -> approved & saved as {saved3['id']}")

    # ---- Show one A2UI surface (what a client would render) -----------
    print("\n" + "-" * 70)
    print("A2UI recommendation surface for the infra decision (JSONL):")
    print("-" * 70)
    print(a2ui.to_jsonl(a2ui.recommendation_surface(infra)))

    # ---- Plan sheet summary -------------------------------------------
    print("\n" + "-" * 70)
    print(f"Plan sheet written: {PLAN}")
    for d in plan_sheet.read_decisions():
        print(f"  {d['id']}  {d['area']:5}  {d['title']:38}  status={d['status']}")
    print("-" * 70)
    print("\nNext:  python deploy_agent.py   (generates Terraform from the plan sheet)")


if __name__ == "__main__":
    main()
