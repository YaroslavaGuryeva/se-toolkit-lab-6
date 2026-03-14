# Agent Architecture

## Overview

This agent is a CLI program that answers questions by calling a Large Language Model (LLM) with tool-calling capabilities. It implements an agentic loop that can use three types of tools:
- **`list_files`/`read_file`** - for exploring wiki documentation and source code
- **`query_api`** - for interacting with the live backend API to get real-time system data

## LLM Provider

**Provider:** Qwen Code API  
**Model:** `qwen3-coder-plus`  
**API Format:** OpenAI-compatible chat completions with function calling (`/v1/chat/completions`)

## Architecture

```
User question ──▶ Initialize messages (system + user)
│
▼
Call LLM with tools
│
▼
┌─── Does response have tool_calls?
│ │
│ Yes │ No
│ ▼
│ Extract answer & source
│ │
│ ▼
│ Format JSON output
│ │
│ ▼
│ Exit with result
│
▼
For each tool_call:

Execute tool with arguments

Record in tool_calls_history

Append tool result as message
│
▼
Continue loop (max 10 iterations)
```


## Components

### `agent.py`

The main CLI entry point with:

1. **Multi-source configuration loading** — reads both `.env.agent.secret` (LLM config) and `.env.docker.secret` (LMS API key)
2. **Agentic Loop** — iterates up to 10 times, calling LLM and executing tools
3. **Three Tools** — `list_files`, `read_file`, and `query_api`
4. **Security Validation** — path traversal prevention for both file system and API calls
5. **Conversation Management** — maintains message history with tool responses
6. **Output Formatting** — produces JSON with answer, source (optional), and tool call history

## Tools

### 1. `list_files`

Lists files and directories at a given path to discover project structure.

| Property | Description |
|----------|-------------|
| **Description** | List files and directories at a given path |
| **Parameters** | `path` (string): Relative directory path from project root |
| **Returns** | Newline-separated listing of entries, or error message |
| **Use Cases** | Discovering wiki files, finding API routers, exploring project structure |

### 2. `read_file`

Reads a file from the project repository to examine code, configuration, or documentation.

| Property | Description |
|----------|-------------|
| **Description** | Read a file from the project repository |
| **Parameters** | `path` (string): Relative file path from project root |
| **Returns** | File contents (truncated at 10,000 chars), or error message |
| **Use Cases** | Reading wiki documentation, analyzing source code, examining config files |

### 3. `query_api` (New in Task 3)

Sends HTTP requests to the live backend API to get real-time system data.

| Property | Description |
|----------|-------------|
| **Description** | Send HTTP requests to the backend API |
| **Parameters** | `method` (string): GET/POST/PUT/DELETE<br>`path` (string): API path with query params<br>`body` (string, optional): JSON request body |
| **Returns** | JSON string with `status_code` and `body` fields |
| **Authentication** | Bearer token using `LMS_API_KEY` from `.env.docker.secret` |
| **Base URL** | `AGENT_API_BASE_URL` (defaults to `http://localhost:42002`) |
| **Use Cases** | Getting item counts, testing endpoints, observing error responses |

## System Prompt Strategy

The system prompt teaches the LLM when to use each tool:

- **Wiki/Code Questions** → Use `list_files` + `read_file` to find and read relevant files
- **Live System Data** → Use `query_api` to get real-time information
- **Bug Diagnosis** → First `query_api` to see error, then `read_file` to find the bug in source

The prompt emphasizes systematic exploration and proper tool selection based on question type.

## Environment Variables

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for authentication | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for API queries (optional) | Environment |

**Important**: The agent reads both configuration files to get all required variables. The autochecker injects its own values, so no values are hardcoded.

## Output Format

The agent outputs a single JSON line to stdout. Source is now optional (empty string for API-only questions):

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [{\"id\": 1, ...}]}"
    }
  ]
}
```

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Example output
{"answer": "REST stands for Representational State Transfer.", "tool_calls": []}
```

## Error Handling

- Missing `.env.agent.secret` → exits with error message to stderr
- Missing environment variables → exits with configuration error
- LLM API failure → exits with HTTP error details
- Timeout (60s) → exits with timeout message

## Tests

Two new regression tests verify the system-aware capabilities:

- Framework question → expects read_file on backend/app/main.py
- Item count question → expects query_api with GET /items/

## Extension Points (Future Tasks)

- **Task 2:** Add tools (e.g., `read_file`, `query_api`) and populate `tool_calls`
- **Task 3:** Implement the agentic loop (plan → act → observe → repeat)
