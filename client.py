"""Local MCP client — connects to our own server.py over stdio.

Thin wrappers around ClientSession so main.py can stay readable. Each helper
maps one-to-one to an MCP call and is named accordingly.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_SCRIPT = Path(__file__).resolve().parent / "server.py"


@asynccontextmanager
async def open_local_server(env: dict[str, str] | None = None):
    """Spawn `python server.py` and yield an initialised ClientSession."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def list_capabilities(session: ClientSession) -> dict[str, Any]:
    tools = await session.list_tools()
    resources = await session.list_resources()
    prompts = await session.list_prompts()
    return {"tools": tools.tools, "resources": resources.resources, "prompts": prompts.prompts}


async def read_resource(session: ClientSession, uri: str):
    return await session.read_resource(uri)


async def get_prompt(session: ClientSession, name: str, arguments: dict[str, Any] | None = None):
    return await session.get_prompt(name, arguments or {})


async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any] | None = None):
    return await session.call_tool(name, arguments or {})
