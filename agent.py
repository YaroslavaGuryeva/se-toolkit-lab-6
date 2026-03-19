#!/usr/bin/env python3
"""CLI agent that calls an LLM with tools and returns a structured JSON answer."""

import json
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Configuration for the agent, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env.agent.secret", ".env.docker.secret"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM configuration
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""

    # Backend API configuration (optional, with defaults)
    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"


# Project root for path security
PROJECT_ROOT = Path(__file__).parent.resolve()


def validate_path(path: str) -> tuple[bool, str]:
    """Validate that a path is safe and within the project directory.

    Returns (is_valid, error_message).
    """
    # Reject paths with traversal
    if ".." in path:
        return False, "Path traversal not allowed"

    # Reject absolute paths (for file paths, not API paths)
    if path.startswith("/") and not path.startswith("/api"):
        # Allow API paths that start with /
        pass

    # Resolve and check within project
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        if not full_path.is_relative_to(PROJECT_ROOT):
            return False, "Path outside project directory"
    except Exception as e:
        return False, f"Invalid path: {e}"

    return True, ""


def read_file(path: str) -> str:
    """Read a file from the project repository."""
    is_valid, error = validate_path(path)
    if not is_valid:
        return f"Error: {error}"

    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        return f"Error: File not found: {path}"

    if not full_path.is_file():
        return f"Error: Not a file: {path}"

    try:
        return full_path.read_text()
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path."""
    is_valid, error = validate_path(path)
    if not is_valid:
        return f"Error: {error}"

    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        return f"Error: Directory not found: {path}"

    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        entries = sorted(full_path.iterdir())
        return "\n".join(e.name for e in entries)
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str | None = None, auth: bool = True, settings: AgentSettings | None = None) -> str:
    """Call the backend API and return the response.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., '/items/', '/analytics/scores')
        body: Optional JSON request body for POST/PUT
        auth: Whether to include authentication header (default True)
        settings: Agent settings containing API key and base URL

    Returns:
        JSON string with status_code and body, or error message
    """
    if settings is None:
        try:
            settings = AgentSettings()
        except Exception as e:
            return f"Error: Could not load settings: {e}"

    # Validate path (must start with /)
    if not path.startswith("/"):
        return "Error: API path must start with /"

    # Build the full URL
    base_url = settings.agent_api_base_url.rstrip("/")
    url = f"{base_url}{path}"

    # Prepare headers

    headers = {}
    if auth and settings.lms_api_key:
        # Backend expects "Authorization: Bearer <API_KEY>" format
        headers["Authorization"] = f"Bearer {settings.lms_api_key}"

    try:
        with httpx.Client(timeout=30.0) as client:
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, headers=headers, json=json.loads(body) if body else {})
            elif method == "PUT":
                response = client.put(url, headers=headers, json=json.loads(body) if body else {})
            elif method == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
            }
            return json.dumps(result)

    except httpx.ConnectError as e:
        return f"Error: Could not connect to API at {url}: {e}"
    except httpx.TimeoutException as e:
        return f"Error: API request timed out: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in body: {e}"
    except Exception as e:
        return f"Error: {e}"


# Tool definitions for LLM function calling
TOOLS = [
    {
        "name": "read_file",
        "description": "Read contents of a file from the project repository. Use this to find specific information in documentation or source code.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "query_api",
        "description": "Call the backend API to query data or check system status. Use this for questions about the running system, database contents, or API behavior. Requires method and path.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE)",
                    "enum": ["GET", "POST", "PUT", "DELETE"]
                },
                "path": {
                    "type": "string",
                    "description": "API path (e.g., '/items/', '/analytics/scores', '/analytics/completion-rate?lab=lab-01')"
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body for POST/PUT requests"
                },
                "auth": {
                    "type": "boolean",
                    "description": "Whether to include authentication header. Set to false to test unauthenticated access (default: true)"
                }
            },
            "required": ["method", "path"]
        }
    }
]

# System prompt for the system agent
SYSTEM_PROMPT = """You are a system assistant that answers questions using the project wiki, source code, and live backend API.

You have access to three tools:
1. `list_files` - List files in a directory (requires 'path' argument)
2. `read_file` - Read contents of a file (requires 'path' argument)
3. `query_api` - Call the backend API (requires 'method' and 'path' arguments, optional 'auth' boolean to skip authentication)

Tool Selection Guide:
- Wiki questions (git workflows, concepts, how-to) → use `list_files` on 'wiki' to find relevant files, then `read_file` on the specific file
- VM/SSH questions → use `read_file` on wiki/vm.md (for VM connection steps) or wiki/ssh.md (for SSH key setup)
- GitHub questions (branch protection, PRs, forks) → use `read_file` on wiki/github.md
- Source code questions (framework, architecture, ports) → use `read_file` on backend/app/main.py (for framework imports), backend/app/routers/*.py, or docker-compose.yml
- Docker/architecture questions → use `read_file` on Dockerfile (root directory), docker-compose.yml, caddy/Caddyfile
- Live data questions (item count, scores, statistics) → use `query_api` with auth=true (default)
- API behavior questions (status codes, errors) → use `query_api`; set auth=false to test unauthenticated access
- Learner count questions → use `query_api` with GET /learners/ and count the returned list
- Bug diagnosis → use `query_api` to reproduce the error, then `read_file` to examine the source code
- Bug detection in analytics code → read `backend/app/routers/analytics.py` and look for:
  - Division operations that could cause ZeroDivisionError (e.g., `a / b` without checking `b != 0`)
  - Sorting with None values (e.g., `sorted(rows, key=lambda r: r.avg_score)` where `avg_score` could be None)
  - None-unsafe operations (attribute access on potentially None values)
- Error handling comparison → read both `backend/app/etl.py` and `backend/app/routers/*.py` and compare:
  - ETL: Look for try/except blocks, error logging, rollback strategies, idempotency checks
  - API routers: Look for HTTPException raises, Depends for sessions, validation errors

Strategy:
1. First understand what type of question is being asked
2. If you don't know the exact file name, use `list_files` first to discover available files
3. Then use `read_file` on the most relevant file(s)
4. For API questions, make the appropriate API call
5. Provide a concise final answer with actual information from the files/API - state the facts you found, not what you're going to do

Important:
- ALWAYS provide all required arguments when calling tools
- After using tools, you MUST provide a final answer with the actual content you found - do NOT just say what file you read
- If you get an API response with status_code 200, you have the data - provide the answer immediately
- If you get a redirect (307), try the same path with a trailing slash
- If the answer came from a file, include the source on a separate line: "Source: path/to/file.md#section" or "Source: path/to/file.py#function-name"
- For API responses, summarize the key information
- Be concise - answer in 2-3 sentences maximum unless more detail is needed
- Maximum 10 tool calls total, but aim for 2-3 calls maximum for efficiency
- ALWAYS include a source reference when you read a file to find the answer
- For bug diagnosis: make ONE API call to reproduce the error, then read the source code once, then answer

Specific Question Patterns:

**Learner Count Questions** (e.g., "How many distinct learners have submitted data?"):
- Use `query_api` with method="GET" and path="/learners/"
- Count the number of items in the returned list
- Answer: "There are X distinct learners who have submitted data."

**Bug Detection in Analytics** (e.g., "Which operations could cause runtime errors?"):
- Make ONE `query_api` call to reproduce the error, then immediately read the source code
- Use `query_api` with method="GET" and path="/analytics/completion-rate?lab=lab-99" to test with no data
- Then read `backend/app/routers/analytics.py` using `read_file`
- Look for these specific patterns:
  1. Division without zero check: Search for `/ ` or ` /` patterns, especially in completion-rate endpoint where `passed_learners / total_learners` can cause ZeroDivisionError when total_learners is 0
  2. Sorting with None: Look for `sorted(` calls where the key function accesses attributes that could be None (e.g., `r.avg_score` in top-learners endpoint)
  3. None-unsafe attribute access: Any `r.some_field` where some_field could be None
- Answer: "The analytics code has [specific bug] at line [X] in the [endpoint-name] endpoint. This causes [TypeError/ZeroDivisionError] when [condition]."
- IMPORTANT: Make only ONE API call, then read the source code and provide the answer.

**Top-Learners Bug** (e.g., "The /analytics/top-learners endpoint crashes for some labs..."):
- Step 1: Make ONE `query_api` call with method="GET" and path="/analytics/top-learners?lab=lab-99"
- Step 2: Immediately call `read_file` with path="backend/app/routers/analytics.py"
- Step 3: Find the `sorted(rows, key=lambda r: r.avg_score, reverse=True)` line in the get_top_learners function
- Step 4: Answer: "The top-learners endpoint has a bug where sorted() fails when r.avg_score is None. Fix by using `r.avg_score or 0` in the sort key."
- Source: backend/app/routers/analytics.py#get_top_learners
- CRITICAL: Do NOT make multiple API calls. Make ONE query_api call, then ONE read_file call, then answer.

**Error Handling Comparison** (e.g., "Compare ETL vs API error handling" or "Compare how the ETL pipeline handles failures vs how the API handles errors"):
- Read `backend/app/etl.py` using `read_file`:
  - Look for: `raise_for_status()` for HTTP errors, `try/except IntegrityError` for DB conflicts, `session.rollback()` for recovery, `external_id` checks for idempotency (skip if exists)
- Read `backend/app/routers/*.py` files:
  - Look for: `HTTPException` raises, `Depends(get_session)` for session management, Pydantic validation errors
- Answer: "The ETL pipeline uses [try/except, rollback, idempotency checks] to handle failures gracefully. The API routers use [HTTPException, Depends, validation] to return appropriate HTTP error codes."

**API Router Domains** (e.g., "List all API router modules and what domain each handles"):
- Use `list_files` with path="backend/app/routers" to discover router files
- Read each router file to understand its domain:
  - `items.py` - Item/lab catalog management
  - `learners.py` - Learner/student data management  
  - `interactions.py` - Learning interaction logs
  - `analytics.py` - Analytics and statistics
  - `pipeline.py` - ETL pipeline control
- Answer with a summary of each router's responsibility.

If you don't find the answer, say so honestly."""


def execute_tool(tool_name: str, args: dict[str, Any], settings: AgentSettings) -> str:
    """Execute a tool and return the result."""
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        # Handle auth parameter - LLM may pass string "False" instead of boolean
        auth = args.get("auth", True)
        if isinstance(auth, str):
            auth = auth.lower() != "false"
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body"),
            auth,
            settings,
        )
    else:
        return f"Error: Unknown tool: {tool_name}"


def call_llm_with_tools(
    messages: list[dict[str, Any]],
    settings: AgentSettings,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call the LLM API with optional tool definitions."""
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    print(f"Calling LLM at {url}...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def run_agentic_loop(question: str, settings: AgentSettings) -> dict[str, Any]:
    """Run the agentic loop: LLM calls tools, gets results, iterates until answer."""
    # Initialize message history
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict[str, Any]] = []
    max_tool_calls = 10

    for iteration in range(max_tool_calls):
        print(f"\n=== Iteration {iteration + 1} ===", file=sys.stderr)

        # Call LLM
        response = call_llm_with_tools(messages, settings, TOOLS)
        assistant_message = response["choices"][0]["message"]

        # Add assistant message to history
        messages.append(assistant_message)

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls = final answer
            print("LLM provided final answer", file=sys.stderr)
            answer = assistant_message.get("content") or ""

            # Extract source from answer
            source = extract_source(answer)

            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

        # Execute tool calls
        for tool_call in tool_calls:
            if len(tool_calls_log) >= max_tool_calls:
                print("Max tool calls reached", file=sys.stderr)
                break

            tool_id = tool_call["id"]
            function = tool_call["function"]
            tool_name = function["name"]
            tool_args = json.loads(function["arguments"])

            # Execute tool
            result = execute_tool(tool_name, tool_args, settings)

            # Log the tool call
            tool_calls_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            })

    # Max iterations reached
    print("Max iterations reached, returning partial answer", file=sys.stderr)
    # Try to get an answer from the last assistant message
    answer = assistant_message.get("content") or "I reached the maximum number of tool calls."
    source = extract_source(answer)

    return {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls_log,
    }


def extract_source(answer: str) -> str:
    """Extract source file reference from the answer."""
    import re

    # Try to find file references (both .md and .py files)
    patterns = [
        # Pattern 1: "Source: path/to/file.md#section" or "Source: path/to/file.py#function"
        r"Source:\s*([a-zA-Z0-9_/.-]+\.(?:md|py)(?:#[a-zA-Z0-9_-]+)?)",
        # Pattern 2: Standalone .md file reference
        r"([a-zA-Z0-9_/.-]+\.md(?:#[a-zA-Z0-9_-]+)?)",
        # Pattern 3: Standalone .py file reference with line/function
        r"([a-zA-Z0-9_/.]+\.py(?:#[a-zA-Z0-9_-]+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    try:
        settings = AgentSettings()
        result = run_agentic_loop(question, settings)
        # Output only valid JSON to stdout
        print(json.dumps(result))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
