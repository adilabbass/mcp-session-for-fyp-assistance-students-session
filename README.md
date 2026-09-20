# FYP Assistant

A tiny Python app for **teaching Model Context Protocol (MCP)** during a live
session. The scenario is a student team working on a **Library Management
System** for their final-year project (FYP), asking:

> "Read our project requirements and help us prepare for tomorrow's
> supervisor meeting."

You can drive the same MCP server two different ways:

1. **The included terminal app** (`main.py`) — you play the host. It calls
   OpenAI directly for the summary step. Good for showing the raw MCP calls.
2. **The Claude desktop app** — Claude plays the host. It discovers the
   server's resources / prompts / tools and decides when to use them. No
   extra code needed on your side.

## Architecture

```
                Option A: our terminal host
                +--------------------------+
                |   main.py  (the host)    |
                |  numbered terminal menu  |
                +-----+--------+-----------+
                      |        |
       MCP over stdio |        | direct HTTPS (OpenAI SDK)
                      |        |
     +----------------+        +----------------+
     |                                          |
+----v-----------+                          +---v----------------+
| client.py      |                          | llm_service.py     |
| (MCP client)   |                          | (OpenAI client)    |
+----+-----------+                          +----+---------------+
     |                                           |
     v                                           v
+----------------+                          +----------------+
| server.py      |                          |  OpenAI API    |
| (local MCP     |                          |                |
|  server)       |                          |                |
+----------------+                          +----------------+


                Option B: Claude desktop is the host
                +---------------------------+
                |   Claude desktop app      |
                |  (host + MCP client)      |
                +-----+---------------------+
                      |
       MCP over stdio |
                      v
              +----------------+
              | server.py      |
              +----------------+
```

- **Host** — orchestrates and (optionally) talks to a model.
- **MCP client** — speaks the MCP protocol to one server over stdio.
- **MCP server** — advertises resources, prompts and tools.

## MCP primitives at a glance

| Primitive | What it is | Who invokes it | Example in this app |
|-----------|------------|----------------|----------------------|
| Resource  | Read-only content the server offers, addressed by URI | The host / user | `fyp://project/brief` |
| Prompt    | A reusable message template the server offers          | The host / user | `prepare_supervisor_meeting(duration_minutes)` |
| Tool      | A function the server can execute (side effects OK)    | The host, and models when connected | `save_meeting_summary(summary)` |

**Note:** retrieving a prompt (`prompts/get`) **does not** call a model. It
returns a template. In our terminal host, the template plus the collected
context is separately handed to OpenAI. In Claude desktop, Claude decides
what to do with it.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env      # fill in what you have; blanks are OK
uv run python main.py
```

Or with plain pip:

```bash
pip install -e .
pip install pytest pytest-asyncio
python main.py
```

### Environment variables

| Variable                        | Needed for                    | Notes                                    |
|---------------------------------|-------------------------------|------------------------------------------|
| `OPENAI_API_KEY`                | Menu option 4 (LLM summary)   | Options 1–3, 5 work without              |
| `OPENAI_MODEL`                  | Optional model override       | Default `gpt-4o-mini`                    |
| `FYP_OUTPUT_DIR`                | Where `save_meeting_summary` writes | Default `output/`                  |

## Option A — Try it in 5 minutes (terminal host)

1. `uv run python main.py`
2. Pick **1** — see the real `tools/list`, `resources/list`, `prompts/list` results.
3. Pick **2** — read both resources by URI.
4. Pick **3** — retrieve the prompt with `duration_minutes=30`. **Point out:
   no LLM ran here.**
5. Pick **4** — the host reads two resources, gets the prompt, and hands
   everything to OpenAI in one call.
6. Pick **5** — save the generated summary with a `tools/call`.

Every prompt in the terminal shows a `[method]` label so students can see the
protocol call that is about to happen.

## Option B — Connect the server to the Claude desktop app

Claude desktop can act as an MCP host itself. Point it at our `server.py`
and Claude will discover the same resources, prompts and tools that our
terminal app uses.

### 1. Find the config file

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Create the file if it does not exist.

### 2. Add the server

Edit the file so it contains something like this. Adjust the absolute paths
to match where you cloned this repo and where your Python lives.

```json
{
  "mcpServers": {
    "fyp-assistant": {
      "command": "python",
      "args": [
        "D:\\Sahiwal Tech Community\\MCP Session\\fyp-assistant\\server.py"
      ],
      "env": {
        "FYP_OUTPUT_DIR": "D:\\Sahiwal Tech Community\\MCP Session\\fyp-assistant\\output"
      }
    }
  }
}
```

Tips:

- On Windows, JSON backslashes must be escaped (`\\`).
- If `python` is not on Claude desktop's PATH, use the absolute path to your
  Python executable (e.g. `"C:\\Users\\hp\\...\\python.exe"`), or use `uv`:
  `"command": "uv"`, `"args": ["run", "--project", "D:\\...\\fyp-assistant", "python", "server.py"]`.

### 3. Restart Claude desktop and try it

Fully quit Claude (from the tray / menu bar), then reopen it. You should see
a small tools icon in the composer. Try prompts like:

- *"Read the FYP project brief and guidelines."* → Claude calls
  `resources/read` on both `fyp://project/*` URIs.
- *"Use the prepare_supervisor_meeting prompt for a 30 minute meeting."* →
  Claude fetches the template via `prompts/get`, then writes the summary
  itself using the resource content.
- *"Save that as my meeting summary."* → Claude calls
  `save_meeting_summary`. It will ask for your confirmation because it is a
  destructive tool.

This is the **agentic** path: Claude chooses which tools/resources/prompts
to use. The terminal app in this repo does the same job with a fixed,
host-controlled sequence — useful for teaching what is actually happening
under the hood.

### Troubleshooting the Claude desktop connection

- Nothing shows up → check the log at
  `%APPDATA%\Claude\logs\mcp*.log` (Windows) or
  `~/Library/Logs/Claude/mcp*.log` (macOS). Usually it's a wrong path or
  Python not being on PATH.
- Server "failed to start" → run the same command in a terminal and see
  what it prints on stderr.
- Tools appear but calls fail → make sure the paths in `env` exist and are
  writable by the Claude app.

## Tests

```bash
uv run pytest -q
```

The single test file starts the real local MCP server over stdio and verifies:

- Capability discovery (tools, resources, prompts).
- Reading both resources.
- Retrieving the prompt with arguments.
- Saving and reading back a summary in an isolated `tmp_path`.

OpenAI and the Claude desktop path are **not** covered by automated
tests — they need real credentials or a running app.

## Explore with MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run python server.py
```

## What this app deliberately isn't

- No autonomous agent loop inside `main.py`. Menu option 4 is a fixed
  sequence: the host chooses which MCP calls to make and only then calls the
  LLM to summarise. (Claude desktop, of course, decides for itself — that's
  the whole point of using it as the host.)
- No database, ORM, web UI, Docker, or DI framework.
- No custom JSON-RPC — everything goes through the official MCP SDK.

## Docs used

- MCP Python SDK — <https://github.com/modelcontextprotocol/python-sdk>
- MCP specification — <https://modelcontextprotocol.io>
- Claude desktop MCP config — <https://modelcontextprotocol.io/quickstart/user>
- OpenAI Python SDK — <https://github.com/openai/openai-python>
