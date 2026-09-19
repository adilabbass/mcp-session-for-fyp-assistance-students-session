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

from dotenv import load_dotenv

import github_client as gh

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[server] %(message)s")
log = logging.getLogger("fyp.server")

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
BRIEF_FILE = DATA_DIR / "project_brief.md"
GUIDELINES_FILE = DATA_DIR / "supervisor_guidelines.md"

SUMMARY_FILENAME = "meeting_summary.md"
SUMMARY_PREFIX = "meeting_summary_"
SUMMARY_SUFFIX = ".md"


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


@mcp.tool(description="Save a meeting summary to output/meeting_summary_YYYY-MM-DD_HH-MM-SS.md. The timestamp is generated automatically; each save creates a new file.")
def save_meeting_summary(summary: str) -> dict:
    """Save the summary to a timestamped file so past summaries are retrievable."""
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{SUMMARY_PREFIX}{stamp}{SUMMARY_SUFFIX}"
    path.write_text(summary, encoding="utf-8")
    log.info("wrote %s (%d chars)", path, len(summary))
    return {"ok": True, "path": str(path), "timestamp": now.isoformat(timespec="seconds")}


@mcp.tool(description="Fetch previously saved meeting summaries for a given date (YYYY-MM-DD). Returns the latest summary from that date, plus a count if multiple exist.")
def get_meeting_summary_by_date(date: str) -> dict:
    """Return the newest summary saved on the given date."""
    try:
        iso_date = datetime.strptime(date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return {"ok": False, "error": "date must be YYYY-MM-DD"}
    out_dir = output_dir()
    if not out_dir.exists():
        return {"ok": False, "error": f"no summary saved for {iso_date}", "date": iso_date}
    matches = sorted(out_dir.glob(f"{SUMMARY_PREFIX}{iso_date}*{SUMMARY_SUFFIX}"))
    if not matches:
        return {"ok": False, "error": f"no summary saved for {iso_date}", "date": iso_date}
    latest = matches[-1]
    return {
        "ok": True,
        "date": iso_date,
        "match_count": len(matches),
        "path": str(latest),
        "summary": latest.read_text(encoding="utf-8"),
    }


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


@mcp.tool(description="Update the local project brief by replacing 'old_text' with 'new_text'. Exact, case-sensitive match. Fails if 'old_text' is not found. Replaces every occurrence.")
def update_project_brief(old_text: str, new_text: str) -> dict:
    """In-place edit of data/project_brief.md."""
    if not old_text:
        return {"ok": False, "error": "old_text must not be empty"}
    content = BRIEF_FILE.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        return {"ok": False, "error": "old_text not found in project brief"}
    updated = content.replace(old_text, new_text)
    BRIEF_FILE.write_text(updated, encoding="utf-8")
    log.info("updated %s (%d replacement%s)", BRIEF_FILE, count, "" if count == 1 else "s")
    return {"ok": True, "path": str(BRIEF_FILE), "replacements": count}


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


def _tool_text(result) -> str:
    return "\n".join(getattr(c, "text", "") or "" for c in result.content)


@mcp.tool(description="List issues from the configured GitHub repo (env: GITHUB_OWNER, GITHUB_REPO, GITHUB_PERSONAL_ACCESS_TOKEN). state='open'|'closed'|'all'.")
async def github_list_issues(state: str = "open") -> dict:
    """Proxy to the external github-mcp-server via github_client."""
    if not gh.github_configured():
        return {"ok": False, "error": "GitHub env vars missing (GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_OWNER, GITHUB_REPO)"}
    try:
        async with gh.open_github_server() as session:
            result = await gh.list_repo_issues(session, state=state)
            return {"ok": True, "state": state, "raw": _tool_text(result)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool(description="Create a new issue in the configured GitHub repo. 'title' is required; 'body' is the issue description (optional).")
async def create_github_issue(title: str, body: str = "") -> dict:
    """Create an issue in owner/repo (both fixed by env)."""
    if not gh.github_configured():
        return {"ok": False, "error": "GitHub env vars missing (GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_OWNER, GITHUB_REPO)"}
    if not title.strip():
        return {"ok": False, "error": "title must not be empty"}
    try:
        async with gh.open_github_server() as session:
            result = await gh.create_repo_issue(session, title=title, body=body)
            return {"ok": True, "title": title, "raw": _tool_text(result)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool(description="Update an existing issue by number. Only fields you pass are changed; omit the others. state='open'|'closed'.")
async def update_github_issue(
    issue_number: int,
    title: str = "",
    body: str = "",
    state: str = "",
) -> dict:
    """Update the given issue and return the API response."""
    if not gh.github_configured():
        return {"ok": False, "error": "GitHub env vars missing (GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_OWNER, GITHUB_REPO)"}
    if issue_number <= 0:
        return {"ok": False, "error": "issue_number must be a positive integer"}
    if not (title or body or state):
        return {"ok": False, "error": "provide at least one field to update: title, body, or state"}
    if state and state not in {"open", "closed"}:
        return {"ok": False, "error": "state must be 'open' or 'closed'"}
    try:
        async with gh.open_github_server() as session:
            result = await gh.update_repo_issue(
                session, issue_number=issue_number, title=title, body=body, state=state,
            )
            return {"ok": True, "issue_number": issue_number, "raw": _tool_text(result)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    log.info("starting FYP Assistant MCP server over stdio")
    mcp.run(transport="stdio")
