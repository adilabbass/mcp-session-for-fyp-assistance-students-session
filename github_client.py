"""GitHub MCP client — talks to the official github-mcp-server over stdio.

Only two operations are exposed: listing issues in the configured repo and
creating an issue in the configured repo. Any other target is rejected.

The mapping to real tool names is kept in TOOL_MAP so it can be adjusted in
one place if the installed binary uses different names — the host calls
`inspect_tools()` on start-up to log the actual `tools/list` output for the
demo.
"""

from __future__ import annotations

import os
import shlex
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Verified against https://github.com/github/github-mcp-server. If your build
# exposes different tool names, edit here.
TOOL_MAP = {
    "list": "list_issues",
    "create": "issue_write",
    "update": "issue_write",
}


class GitHubNotConfigured(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise GitHubNotConfigured(f"{name} is not set")
    return value


def github_configured() -> bool:
    return all(os.environ.get(k) for k in ("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"))


@asynccontextmanager
async def open_github_server():
    """Spawn the GitHub MCP server and yield an initialised ClientSession."""
    token = _require_env("GITHUB_PERSONAL_ACCESS_TOKEN")
    command = os.environ.get("GITHUB_MCP_COMMAND", "github-mcp-server")
    args = shlex.split(os.environ.get("GITHUB_MCP_ARGS", "stdio"))

    env = os.environ.copy()
    env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token

    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _configured_repo() -> tuple[str, str]:
    return _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")


def _check_target(owner: str, repo: str) -> None:
    want_owner, want_repo = _configured_repo()
    if (owner, repo) != (want_owner, want_repo):
        raise ValueError(
            f"Refusing GitHub call for {owner}/{repo}; only {want_owner}/{want_repo} is allowed."
        )


async def inspect_tools(session: ClientSession) -> list[Any]:
    """List every tool the GitHub server actually exposes — useful for the demo."""
    result = await session.list_tools()
    return result.tools


async def list_repo_issues(session: ClientSession, state: str = "open") -> Any:
    owner, repo = _configured_repo()
    _check_target(owner, repo)
    return await session.call_tool(
        TOOL_MAP["list"],
        {"owner": owner, "repo": repo, "state": state},
    )


async def create_repo_issue(session: ClientSession, title: str, body: str = "") -> Any:
    owner, repo = _configured_repo()
    _check_target(owner, repo)
    return await session.call_tool(
        TOOL_MAP["create"],
        {"owner": owner, "repo": repo, "method": "create", "title": title, "body": body},
    )


async def update_repo_issue(
    session: ClientSession,
    issue_number: int,
    title: str = "",
    body: str = "",
    state: str = "",
) -> Any:
    owner, repo = _configured_repo()
    _check_target(owner, repo)
    args: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "method": "update",
        "issue_number": issue_number,
    }
    if title:
        args["title"] = title
    if body:
        args["body"] = body
    if state:
        args["state"] = state
    return await session.call_tool(TOOL_MAP["update"], args)
