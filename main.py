"""FYP Assistant — terminal host.

Shows a plain numbered menu, orchestrates MCP calls, optionally hands the
collected material to Claude. Every MCP call is preceded by a labelled line
(e.g. `[resources/read] fyp://project/brief`) so students can see the real
protocol calls being made.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack

from dotenv import load_dotenv

import client as local_client
import github_client as gh
import llm_service

load_dotenv()

BRIEF_URI = "fyp://project/brief"
GUIDELINES_URI = "fyp://project/guidelines"
PROMPT_NAME = "prepare_supervisor_meeting"
SAVE_TOOL = "save_meeting_summary"


def label(call: str, detail: str = "") -> None:
    print(f"\n[{call}] {detail}".rstrip())


def confirm(question: str) -> bool:
    return input(f"{question} [y/N]: ").strip().lower() == "y"


def _resource_text(read_result) -> str:
    parts = []
    for c in read_result.contents:
        if getattr(c, "text", None):
            parts.append(c.text)
    return "\n".join(parts)


def _tool_result_text(call_result) -> str:
    parts = []
    for c in call_result.content:
        if getattr(c, "text", None):
            parts.append(c.text)
    return "\n".join(parts) or "(no text content)"


def _parse_issues(text: str):
    try:
        data = json.loads(text)
    except Exception:
        return None
    if isinstance(data, dict) and "issues" in data:
        return data["issues"]
    if isinstance(data, list):
        return data
    return None


async def menu_explore(local, gh_session):
    label("tools/list, resources/list, prompts/list", "local server")
    caps = await local_client.list_capabilities(local)
    print(f"  tools:     {[t.name for t in caps['tools']]}")
    print(f"  resources: {[r.uri.__str__() for r in caps['resources']]}")
    print(f"  prompts:   {[p.name for p in caps['prompts']]}")

    if gh_session is not None:
        label("tools/list", "GitHub server")
        tools = await gh.inspect_tools(gh_session)
        print(f"  tools ({len(tools)}): showing first 10")
        for t in tools[:10]:
            print(f"    - {t.name}")
    else:
        print("\n  (GitHub server not configured — skipping)")


async def menu_read_resources(local):
    for uri in (BRIEF_URI, GUIDELINES_URI):
        label("resources/read", uri)
        r = await local_client.read_resource(local, uri)
        text = _resource_text(r)
        print("---")
        print(text)
        print("---")


async def menu_view_prompt(local):
    raw = input("Meeting duration in minutes [30]: ").strip() or "30"
    try:
        duration = int(raw)
    except ValueError:
        print("Not a number, using 30.")
        duration = 30
    label("prompts/get", f"{PROMPT_NAME}(duration_minutes={duration})")
    p = await local_client.get_prompt(local, PROMPT_NAME, {"duration_minutes": str(duration)})
    for m in p.messages:
        content = m.content
        text = getattr(content, "text", None) or str(content)
        print(f"[{m.role}]\n{text}")
    print("\n(Note: this only returned a template. No AI response was generated.)")


async def menu_list_github(gh_session):
    if gh_session is None:
        print("GitHub is not configured. Set GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_OWNER, GITHUB_REPO.")
        return None
    label("tools/call", f"{gh.TOOL_MAP['list']}({os.environ['GITHUB_OWNER']}/{os.environ['GITHUB_REPO']})")
    result = await gh.list_repo_issues(gh_session)
    text = _tool_result_text(result)
    print(text)
    return text


async def menu_prepare_summary(local, gh_session, state):
    if not llm_service.llm_configured():
        print("OPENAI_API_KEY is not set — cannot generate a summary.")
        return

    raw = input("Meeting duration in minutes [30]: ").strip() or "30"
    try:
        duration = int(raw)
    except ValueError:
        duration = 30

    label("resources/read", BRIEF_URI)
    brief = _resource_text(await local_client.read_resource(local, BRIEF_URI))
    label("resources/read", GUIDELINES_URI)
    guidelines = _resource_text(await local_client.read_resource(local, GUIDELINES_URI))
    label("prompts/get", f"{PROMPT_NAME}(duration_minutes={duration})")
    prompt_result = await local_client.get_prompt(local, PROMPT_NAME, {"duration_minutes": str(duration)})
    template_parts = []
    for m in prompt_result.messages:
        t = getattr(m.content, "text", None)
        if t:
            template_parts.append(t)
    template = "\n".join(template_parts)

    issues_payload = None
    if gh_session is not None:
        label("tools/call", f"{gh.TOOL_MAP['list']} (for meeting context)")
        try:
            result = await gh.list_repo_issues(gh_session)
            text = _tool_result_text(result)
            issues_payload = _parse_issues(text) or text
        except Exception as e:
            print(f"GitHub call failed ({e}); continuing without task list.")
    else:
        print("(GitHub not configured — summary will note 'GitHub progress unavailable'.)")

    print("\nCalling the LLM... (this is a direct OpenAI API call, not an MCP call)")
    summary = llm_service.summarise_for_supervisor(
        brief_md=brief,
        guidelines_md=guidelines,
        prompt_template=template,
        issues=issues_payload,
        duration_minutes=duration,
    )
    print("---")
    print(summary)
    print("---")
    state["last_summary"] = summary


async def menu_save_summary(local, state):
    summary = state.get("last_summary")
    if not summary:
        print("No summary in memory. Options: generate one via option 5, or paste sample text.")
        if confirm("Enter sample summary text now?"):
            summary = input("Summary text: ").strip()
            if not summary:
                print("Empty — nothing to save.")
                return
        else:
            return
    if not confirm("Save this summary to output/meeting_summary.md (overwriting)?"):
        print("Cancelled.")
        return
    label("tools/call", f"{SAVE_TOOL}(summary=<{len(summary)} chars>)")
    result = await local_client.call_tool(local, SAVE_TOOL, {"summary": summary})
    print(_tool_result_text(result))


async def menu_create_issue(gh_session):
    if gh_session is None:
        print("GitHub is not configured.")
        return
    title = input("Issue title: ").strip()
    if not title:
        print("Title required.")
        return
    body = input("Issue body (optional): ").strip()
    print(f"About to create issue in {os.environ['GITHUB_OWNER']}/{os.environ['GITHUB_REPO']}: {title!r}")
    if not confirm("Create this issue?"):
        print("Cancelled.")
        return
    label("tools/call", f"{gh.TOOL_MAP['create']}(title={title!r})")
    result = await gh.create_repo_issue(gh_session, title, body)
    print(_tool_result_text(result))


MENU = """
FYP Assistant — MCP demo
  1. Explore server capabilities
  2. Read project resources
  3. View the meeting prompt
  4. List GitHub tasks
  5. Prepare a meeting summary with the LLM
  6. Save the last generated summary
  7. Create a GitHub task
  0. Exit
"""


async def run() -> None:
    state: dict = {}
    async with AsyncExitStack() as stack:
        local = await stack.enter_async_context(local_client.open_local_server())
        print("Local MCP server connected.")

        gh_session = None
        if gh.github_configured():
            try:
                gh_session = await stack.enter_async_context(gh.open_github_server())
                print(f"GitHub MCP server connected ({os.environ['GITHUB_OWNER']}/{os.environ['GITHUB_REPO']}).")
            except Exception as e:
                print(f"Could not start GitHub MCP server: {e}")
        else:
            print("GitHub not configured — options 4 and 7 will be disabled.")

        if not llm_service.llm_configured():
            print("OPENAI_API_KEY not set — option 5 will be disabled.")

        while True:
            print(MENU)
            choice = input("Choose: ").strip()
            try:
                if choice == "1":
                    await menu_explore(local, gh_session)
                elif choice == "2":
                    await menu_read_resources(local)
                elif choice == "3":
                    await menu_view_prompt(local)
                elif choice == "4":
                    await menu_list_github(gh_session)
                elif choice == "5":
                    await menu_prepare_summary(local, gh_session, state)
                elif choice == "6":
                    await menu_save_summary(local, state)
                elif choice == "7":
                    await menu_create_issue(gh_session)
                elif choice == "0":
                    print("Bye.")
                    return
                else:
                    print("Unknown option.")
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
