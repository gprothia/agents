"""CLI Runner for testing the ComponentIQ Datasheet Finder Agent locally."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google.genai import types

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from datasheet_finder_agent.agent import app

load_dotenv()

async def main():
    print("=" * 65)
    print(" ⚡ ComponentIQ - Electrical Component Datasheet Finder (CLI)")
    print("=" * 65)
    print("Enter a component part number or query (e.g. 'stm32f407', 'MAX232|PE', 'LM317 reg').\n")

    session_service = InMemorySessionService()
    session_id = "datasheet_cli_session"
    user_id = "cli_user"
    app_name = app.name

    await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

    runner = Runner(app=app, session_service=session_service)

    # Single-prompt invocation if command line arguments passed
    if len(sys.argv) > 1:
        user_prompt = " ".join(sys.argv[1:])
        print(f"[User]: {user_prompt}\n")
        new_msg = types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])
        print("[ComponentIQ]:")
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_msg):
            if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        print(part.text, end="", flush=True)
        print("\n")
        return

    # REPL loop
    while True:
        try:
            user_input = input("Component IQ > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting ComponentIQ. Goodbye!")
                break

            print("\nResolving part number, searching Google & downloading PDF...")
            new_msg = types.Content(role="user", parts=[types.Part.from_text(text=user_input)])
            async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_msg):
                if hasattr(event, "content") and event.content and hasattr(event.content, "parts"):
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            print(part.text, end="", flush=True)
            print("\n" + "-" * 65)
        except KeyboardInterrupt:
            print("\nSession interrupted. Exiting.")
            break
        except Exception as e:
            print(f"\nError executing search: {e}\n")

if __name__ == "__main__":
    asyncio.run(main())
