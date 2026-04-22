"""
main.py
-------
CLI entrypoint for the Banking Onboarding / KYC Multi-Agent System.

Usage:
    # Run an application from a JSON file
    python main.py sample_applications/application_individual_001.json

    # Run an application from a JSON string
    python main.py '{"application_id": "APP-001", "full_name": "Jane Doe", ...}'

    # Run a free-text application description
    python main.py "I'd like to open a personal checking account. My name is Jane Doe..."

The pipeline runs synchronously and prints a structured onboarding decision to stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure Unicode output works correctly on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from banking_agent.configs.logging_config import configure as _configure_logging
_configure_logging()

from banking_agent.agent import banking_onboarding_agent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_application_input(arg: str) -> str:
    """
    Accept a file path, a JSON string, or plain-text description.
    Returns the raw string that will be sent as the user message to the pipeline.
    """
    path = Path(arg)
    if path.exists() and path.suffix == ".json":
        return path.read_text(encoding="utf-8")
    return arg


def _pretty_print_result(state: dict) -> None:
    """Print a concise summary of the pipeline result."""
    final = state.get("final_decision")
    if final:
        try:
            data = json.loads(final) if isinstance(final, str) else final
            print("\n" + "=" * 65)
            print("BANKING ONBOARDING / KYC DECISION")
            print("=" * 65)
            print(f"Application ID  : {data.get('application_id', 'N/A')}")
            print(f"Status          : {data.get('overall_status', 'N/A').upper().replace('_', ' ')}")
            print(f"Risk Level      : {data.get('risk_level', 'N/A').upper()}")
            print(f"Account Type    : {data.get('account_type', 'N/A')}")

            missing = data.get("missing_docs", [])
            if missing:
                print(f"Missing Docs    : {', '.join(missing)}")

            mismatches = data.get("identity_mismatches", [])
            if mismatches:
                print("ID Mismatches   :")
                for m in mismatches:
                    print(f"  - {m}")

            aml_flags = data.get("aml_flags", [])
            if aml_flags:
                print("AML Flags       :")
                for f in aml_flags:
                    print(f"  - {f}")

            next_steps = data.get("next_steps", [])
            if next_steps:
                print("Next Steps      :")
                for step in next_steps:
                    print(f"  • {step}")

            print(f"\nSummary: {data.get('summary', '')}")
            print(f"\nCompliance Notes: {data.get('compliance_notes', 'N/A')}")
            print(f"Audit Log Key   : {data.get('audit_key', 'N/A')}")
            print("=" * 65 + "\n")
        except Exception:
            print("\nFinal decision (raw):")
            print(final)
    else:
        print("\n[WARNING] No final_decision found in session state.")
        print("Session state keys:", list(state.keys()))


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------


async def run_pipeline(application_input: str) -> dict:
    """
    Execute the full onboarding KYC pipeline for a single application.

    Args:
        application_input: Raw application data — JSON string, file path, or free-text.

    Returns:
        The final session state dict after the pipeline completes.
    """
    session_id = "session_" + str(hash(application_input) % 10**9)

    print(f"\nRunning Banking Onboarding / KYC Pipeline...")
    print(f"Session ID: {session_id}\n")

    return await banking_onboarding_agent.process_application(
        application_input=application_input,
        session_id=session_id,
        user_id="onboarding_officer",
    )


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python main.py <path/to/application.json>\n"
            "  python main.py '<json string>'\n"
            "  python main.py 'Free-text application description...'\n"
        )
        sys.exit(1)

    raw_input = _load_application_input(sys.argv[1])
    final_state = asyncio.run(run_pipeline(raw_input))
    _pretty_print_result(final_state)


if __name__ == "__main__":
    main()
