"""Integration test — spins up the real server.py over stdio and drives it.

No GitHub or Anthropic credentials required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import client as local_client  # noqa: E402


def _text(result_contents) -> str:
    return "\n".join(getattr(c, "text", "") or "" for c in result_contents)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    out = tmp_path / "output"
    monkeypatch.setenv("FYP_OUTPUT_DIR", str(out))
    yield {"FYP_OUTPUT_DIR": str(out), "PATH": os.environ.get("PATH", "")}


@pytest.mark.asyncio
async def test_capability_discovery(isolated_env):
    async with local_client.open_local_server(env=isolated_env) as session:
        caps = await local_client.list_capabilities(session)
        tool_names = {t.name for t in caps["tools"]}
        resource_uris = {str(r.uri) for r in caps["resources"]}
        prompt_names = {p.name for p in caps["prompts"]}

        assert "save_meeting_summary" in tool_names
        assert "fyp://project/brief" in resource_uris
        assert "fyp://project/guidelines" in resource_uris
        assert "prepare_supervisor_meeting" in prompt_names


@pytest.mark.asyncio
async def test_read_both_resources(isolated_env):
    async with local_client.open_local_server(env=isolated_env) as session:
        brief = await local_client.read_resource(session, "fyp://project/brief")
        guidelines = await local_client.read_resource(session, "fyp://project/guidelines")
        assert "Library" in _text(brief.contents)
        assert "Supervisor" in _text(guidelines.contents)


@pytest.mark.asyncio
async def test_prompt_with_arguments(isolated_env):
    async with local_client.open_local_server(env=isolated_env) as session:
        p = await local_client.get_prompt(
            session, "prepare_supervisor_meeting", {"duration_minutes": "30"}
        )
        text = "\n".join(
            getattr(m.content, "text", "") or "" for m in p.messages
        )
        assert "30-minute" in text
        for marker in ("1.", "2.", "3.", "4."):
            assert marker in text


@pytest.mark.asyncio
async def test_save_and_read_back(isolated_env, tmp_path):
    async with local_client.open_local_server(env=isolated_env) as session:
        summary = "## Test meeting summary\n- item"
        result = await local_client.call_tool(
            session, "save_meeting_summary", {"summary": summary}
        )
        text = _text(result.content)
        assert "ok" in text.lower() or "meeting_summary.md" in text

        saved = Path(isolated_env["FYP_OUTPUT_DIR"]) / "meeting_summary.md"
        assert saved.exists()
        assert saved.read_text(encoding="utf-8") == summary
