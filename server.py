"""FYP Assistant — local MCP server.

Exposes two resources (the project brief and supervisor guidelines), one prompt
(a meeting-prep template) and one tool (save the meeting summary to a fixed
file). Speaks MCP over stdio, so stdout is reserved for framing and all
logging goes to stderr.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[server] %(message)s")
log = logging.getLogger("fyp.server")

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
BRIEF_FILE = DATA_DIR / "project_brief.md"
GUIDELINES_FILE = DATA_DIR / "supervisor_guidelines.md"

SUMMARY_FILENAME = "meeting_summary.md"


def output_dir() -> Path:
    return Path(os.environ.get("FYP_OUTPUT_DIR") or (HERE / "output"))


mcp = MCPServer("FYP Assistant")


@mcp.resource("fyp://project/brief", mime_type="text/markdown")
def project_brief() -> str:
    """The Library Management System project brief."""
    return BRIEF_FILE.read_text(encoding="utf-8")


@mcp.resource("fyp://project/guidelines", mime_type="text/markdown")
def project_guidelines() -> str:
    """Supervisor expectations and assessment criteria."""
    return GUIDELINES_FILE.read_text(encoding="utf-8")


@mcp.prompt(description="Template message to structure a supervisor meeting.")
def prepare_supervisor_meeting(duration_minutes: str) -> str:
    """Return a reusable meeting-prep template.

    The template asks the caller (the host) to supply evidence and GitHub task
    information itself — this prompt does not fetch anything or call a model.

    MCP prompt arguments are strings on the wire, so we parse here.
    """
    try:
        minutes = int(duration_minutes)
    except (TypeError, ValueError):
        minutes = 30
    return (
        f"You are helping a student team prepare for a {minutes}-minute "
        "supervisor meeting for their final-year project.\n\n"
        "Using the project brief, supervisor guidelines and the current GitHub "
        "issues provided by the host, produce a concise meeting note with these "
        "four numbered sections:\n\n"
        "1. Progress — what was completed, each item supported by the supplied "
        "evidence (a closed issue, a demo, a merged PR). Do not invent progress.\n"
        "2. Pending work and blockers — open issues, in-progress work, anything "
        "waiting on the supervisor or another team.\n"
        "3. Questions for the supervisor — specific decisions or feedback the "
        "team needs, framed so the supervisor can answer briefly.\n"
        "4. Suggested next steps — a short ordered list of what the team plans "
        "to do before the next meeting.\n\n"
        "Keep the whole note under one page. If GitHub information is missing, "
        'say so explicitly under section 1 as "GitHub progress unavailable" '
        "rather than guessing."
    )


@mcp.tool(description="Save a meeting summary to output/meeting_summary.md (overwrites any previous summary).")
def save_meeting_summary(summary: str) -> dict:
    """Save the summary to a fixed local file.

    Note: this replaces the previous summary. Arbitrary paths are not accepted
    — the file is always written to `<FYP_OUTPUT_DIR>/meeting_summary.md`.
    """
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SUMMARY_FILENAME
    path.write_text(summary, encoding="utf-8")
    log.info("wrote %s (%d chars)", path, len(summary))
    return {"ok": True, "path": str(path)}


@mcp.tool(description="List previously saved meeting summaries in the output directory, newest first.")
def list_meeting_summaries() -> dict:
    """Return metadata for every file in the output directory."""
    out_dir = output_dir()
    if not out_dir.exists():
        return {"count": 0, "summaries": []}
    entries = []
    for p in out_dir.iterdir():
        if p.is_file():
            stat = p.stat()
            entries.append({
                "name": p.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })
    entries.sort(key=lambda e: e["modified"], reverse=True)
    return {"count": len(entries), "summaries": entries}


@mcp.tool(description="Case-insensitive search across the project brief and supervisor guidelines. Returns matching lines with source and line number.")
def search_project_brief(query: str) -> dict:
    """Search the two project resources for a substring."""
    if not query or not query.strip():
        return {"query": query, "matches": [], "error": "query must not be empty"}
    needle = query.lower()
    matches = []
    for label, path in (("brief", BRIEF_FILE), ("guidelines", GUIDELINES_FILE)):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if needle in line.lower():
                matches.append({"source": label, "line": lineno, "text": line.strip()})
    return {"query": query, "match_count": len(matches), "matches": matches}


@mcp.tool(description="Estimate FYP progress from completed vs total tasks and weeks remaining. Returns percent done, required weekly velocity, and an on-track verdict.")
def estimate_progress(done_tasks: int, total_tasks: int, weeks_left: int) -> dict:
    """Pure computation — no I/O, no external calls."""
    if total_tasks <= 0:
        return {"error": "total_tasks must be greater than zero"}
    if done_tasks < 0 or weeks_left < 0:
        return {"error": "done_tasks and weeks_left must be non-negative"}
    remaining = max(total_tasks - done_tasks, 0)
    percent_done = round(done_tasks / total_tasks * 100, 1)
    required_velocity = round(remaining / weeks_left, 2) if weeks_left > 0 else None
    if percent_done >= 100:
        verdict = "complete"
    elif weeks_left == 0:
        verdict = "overdue"
    elif required_velocity is not None and required_velocity <= 3:
        verdict = "on_track"
    elif required_velocity is not None and required_velocity <= 6:
        verdict = "tight"
    else:
        verdict = "at_risk"
    return {
        "percent_done": percent_done,
        "remaining_tasks": remaining,
        "required_tasks_per_week": required_velocity,
        "verdict": verdict,
    }


if __name__ == "__main__":
    log.info("starting FYP Assistant MCP server over stdio")
    mcp.run(transport="stdio")
