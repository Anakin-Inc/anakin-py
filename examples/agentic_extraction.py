"""
Anakin Python SDK — agentic search with structured output.

Demonstrates the full multi-stage AI pipeline: prompt → web search →
content extraction → structured JSON matching a user-supplied schema.

Costs ~10 credits per call. Takes 1–5 minutes.

Run:
    ANAKIN_API_KEY=ak-... python examples/agentic_extraction.py
"""

from __future__ import annotations

import json
import os

from anakin import Anakin


# A JSON schema describing the structured data we want extracted.
# The agentic pipeline will infer how to populate it from web sources.
SCHEMA = {
    "type": "object",
    "properties": {
        "tools": {
            "type": "array",
            "description": "Popular open-source HTTP libraries for Python",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "stars": {"type": "number"},
                    "primary_use_case": {"type": "string"},
                },
                "required": ["name", "primary_use_case"],
            },
        }
    },
    "required": ["tools"],
}


def main() -> None:
    if not os.environ.get("ANAKIN_API_KEY"):
        raise SystemExit("Set ANAKIN_API_KEY in your environment first.")

    with Anakin(poll_timeout=600.0) as client:
        result = client.agentic_search(
            prompt=(
                "List the top open-source HTTP libraries for Python with their "
                "GitHub star counts and what each is best at."
            ),
            schema=SCHEMA,
        )
        print(f"status={result.status}  duration_ms={result.duration_ms}")
        if result.generated_json:
            if result.generated_json.summary:
                print("\nSummary:")
                print(result.generated_json.summary)
            if result.generated_json.structured_data:
                print("\nStructured data:")
                print(json.dumps(result.generated_json.structured_data, indent=2))


if __name__ == "__main__":
    main()
