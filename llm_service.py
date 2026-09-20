"""One function: ask the LLM (OpenAI) to turn MCP-collected material into a summary.

Kept deliberately dumb — the model does not choose tools. The host has already
fetched the resources and the prompt template via MCP; this function only
formats them into a single user message and returns the reply text.

This module is completely separate from anything MCP-related. MCP clients
talk to MCP servers; this file talks to the OpenAI HTTP API. The host wires
the two together.
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "gpt-4o-mini"


class MissingCredentials(RuntimeError):
    pass


def llm_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def summarise_for_supervisor(
    brief_md: str,
    guidelines_md: str,
    prompt_template: str,
    duration_minutes: int,
) -> str:
    """Call OpenAI once with everything the host collected via MCP."""
    if not llm_configured():
        raise MissingCredentials("OPENAI_API_KEY is not set")

    # Imported lazily so the module is safe to import without the SDK installed.
    from openai import OpenAI

    user_message = (
        f"{prompt_template}\n\n"
        f"Meeting duration: {duration_minutes} minutes.\n\n"
        "=== PROJECT BRIEF ===\n"
        f"{brief_md}\n\n"
        "=== SUPERVISOR GUIDELINES ===\n"
        f"{guidelines_md}\n"
    )

    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": user_message}],
    )
    return (resp.choices[0].message.content or "").strip()
