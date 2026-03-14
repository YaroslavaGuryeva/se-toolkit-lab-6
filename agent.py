
## Updated agent.py with query_api Tool

```python
#!/usr/bin/env python3
"""CLI agent that answers questions using an LLM with tool calling and API access.

Usage:
    uv run agent.py "How many items are in the database?"

Output (JSON to stdout):
    {
        "answer": "There are 120 items in the database.",
        "source": "",  # Optional for API questions
        "tool_calls": [...]
    }

All debug/logging output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import asyncio
import urllib.parse

import httpx


# Constants
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent.absolute()


def _load_env():
    """Load environment variables from .env.agent.secret and .env.docker.secret."""
    # Load .env.agent.secret (LLM config)
    agent_env_file = Path(".env.agent.secret")
    if not agent_env_file.exists():
        print(f"Error: {agent_env_file} not found. Copy .env.agent.example to .env.agent.secret and configure it.", file=sys.stderr)
        sys.exit(1)

    for line in agent_env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

    # Load .env.docker.secret (LMS API key)
    docker_env_file = Path(".env.docker.secret")
    if docker_env_file.exists():
        for line in docker_env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_llm_config() -> tuple[str, str, str]:
    """Get LLM configuration from environment variables."""
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL", "")

    if not all([api_key, api_base, model]):
        print(
            "Error: Missing LLM configuration. Set LLM_API_KEY, LLM_API_BASE, and LLM_MODEL in .env.agent.secret.",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key, api_base, model


def _get_api_config() -> tuple[str, str]:
    """Get API configuration for query_api tool."""
    lms_api_key = os.environ.get("LMS_API_KEY", "")
    api_base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")

    if not lms_api_key:
        print(
            "Warning: LMS_API_KEY not found in environment. API queries may fail.",
            file=sys.stderr,
        )

    return lms_api_key, api_base_url


def _get_tool_schemas() -> List[Dict[str, Any]]:
    """Return the tool schemas for function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given path to discover project structure",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki', 'backend', 'backend/app/api')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the project repository to examine code, configuration, or documentation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py', 'docker-compose.yml')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Send HTTP requests to the live backend API to get real-time system data, test endpoints, or observe error responses",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "DELETE"],
                            "description": "HTTP method for the request (GET for retrieving data, POST for creating, etc.)"
                        },
                        "path": {
                            "type": "string",
                            "description": "API path including query parameters (e.g., '/items/', '/analytics/completion-rate?lab=lab-99', '/items/42')"
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST/PUT requests (e.g., '{\"name\": \"new item\"}')"
                        }
                    },
                    "required": ["method", "path"]
                }
            }
        }
    ]


def _get_system_prompt() -> str:
    """Return the system prompt for the LLM."""
    return """
You are a system-aware assistant with access to:
1. Wiki documentation (via list_files/read_file in the 'wiki/' directory)
2. Source code and configuration files (via read_file in any project directory)
3. Live API data (via query_api to the running backend)

TOOL SELECTION GUIDE:
- Use list_files/read_file for:
  * Documentation questions about the project (wiki/*.md)
  * Code analysis to understand implementation details
  * Reading configuration files (docker-compose.yml, Dockerfile, etc.)
  * Finding the source of bugs after seeing API errors

- Use query_api for:
  * Getting live system data (item counts, database contents)
  * Testing API behavior and status codes
  * Observing error responses from endpoints
  * Verifying API functionality

ANSWER FORMAT:
1. For wiki/code questions: Include source with format wiki/filename.md#section
2. For API questions: Source is optional (can be empty string)
3. Always provide clear, concise answers based on the data you find

DIAGNOSIS WORKFLOW:
When asked about bugs or errors:
1. First, use query_api to see what error the endpoint returns
2. Then, use read_file to examine the relevant source code
3. Explain both the error and the bug in your answer

Always explore systematically. If you need more information, call additional tools.
"""


def _safe_path_resolve(relative_path: str) -> Optional[Path]:
    """Safely resolve a relative path to ensure it's within project root.
    
    Returns:
        Path object if safe, None if path attempts directory traversal
    """
    # Block obvious directory traversal
    if ".." in relative_path.split("/") or ".." in relative_path.split("\\"):
        return None
    
    # Resolve to absolute path
    target_path = (PROJECT_ROOT / relative_path).resolve()
    
    # Check if the resolved path is still within project root
    try:
        target_path.relative_to(PROJECT_ROOT)
        return target_path
    except ValueError:
        return None


def _safe_url_join(base: str, path: str) -> Optional[str]:
    """Safely join base URL and path, preventing path traversal.
    
    Returns:
        Full URL string if safe, None if path attempts traversal
    """
    # Block path traversal in API paths
    if ".." in path.split("/") or ".." in path.split("\\"):
        return None
    
    # Remove leading slash if present for urljoin
    if path.startswith("/"):
        path = path[1:]
    
    # Use urllib.parse.urljoin to properly handle base URLs with/without trailing slashes
    full_url = urllib.parse.urljoin(base.rstrip("/") + "/", path)
    return full_url


async def _execute_tool(tool_call: Dict[str, Any]) -> str:
    """Execute a tool call and return the result.
    
    Args:
        tool_call: Dictionary with 'name' and 'arguments' keys
        
    Returns:
        String result of the tool execution
    """
    name = tool_call["name"]
    args = tool_call["arguments"]
    
    if name == "list_files":
        path = args.get("path", "")
        print(f"  Executing list_files('{path}')", file=sys.stderr)
        
        safe_path = _safe_path_resolve(path)
        if not safe_path:
            return f"Error: Invalid path '{path}' - directory traversal not allowed"
        
        if not safe_path.exists():
            return f"Error: Path '{path}' does not exist"
        
        if not safe_path.is_dir():
            return f"Error: Path '{path}' is not a directory"
        
        try:
            entries = sorted([str(p.relative_to(safe_path)) for p in safe_path.iterdir()])
            return "\n".join(entries)
        except Exception as e:
            return f"Error listing directory: {str(e)}"
    
    elif name == "read_file":
        path = args.get("path", "")
        print(f"  Executing read_file('{path}')", file=sys.stderr)
        
        safe_path = _safe_path_resolve(path)
        if not safe_path:
            return f"Error: Invalid path '{path}' - directory traversal not allowed"
        
        if not safe_path.exists():
            return f"Error: File '{path}' does not exist"
        
        if not safe_path.is_file():
            return f"Error: Path '{path}' is not a file"
        
        try:
            # Read file with size limit to prevent token overflow
            content = safe_path.read_text(encoding="utf-8")
            if len(content) > 10000:
                content = content[:10000] + "\n... (content truncated due to length)"
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    elif name == "query_api":
        method = args.get("method", "GET").upper()
        path = args.get("path", "")
        body = args.get("body")
        
        print(f"  Executing query_api({method}, '{path}')", file=sys.stderr)
        
        # Get API configuration
        lms_api_key, api_base_url = _get_api_config()
        
        # Validate path
        if ".." in path:
            return json.dumps({
                "status_code": 400,
                "body": {"error": "Invalid path - directory traversal not allowed"}
            })
        
        # Construct full URL safely
        full_url = _safe_url_join(api_base_url, path)
        if not full_url:
            return json.dumps({
                "status_code": 400,
                "body": {"error": "Invalid URL construction"}
            })
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json"
        }
        if lms_api_key:
            headers["Authorization"] = f"Bearer {lms_api_key}"
        
        # Prepare request
        request_kwargs = {
            "method": method,
            "url": full_url,
            "headers": headers,
            "timeout": 30.0
        }
        
        if body and method in ["POST", "PUT"]:
            try:
                # Validate JSON body
                json.loads(body)
                request_kwargs["content"] = body.encode("utf-8")
            except json.JSONDecodeError:
                return json.dumps({
                    "status_code": 400,
                    "body": {"error": f"Invalid JSON body: {body}"}
                })
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(**request_kwargs)
                
                # Try to parse response as JSON, fall back to text
                try:
                    body_content = response.json()
                except:
                    body_content = response.text
                
                # Truncate large responses
                if isinstance(body_content, str) and len(body_content) > 5000:
                    body_content = body_content[:5000] + "... (truncated)"
                elif isinstance(body_content, dict) and len(json.dumps(body_content)) > 5000:
                    body_content = {"truncated": True, "message": "Response too large"}
                
                return json.dumps({
                    "status_code": response.status_code,
                    "body": body_content
                })
                
        except httpx.TimeoutException:
            return json.dumps({
                "status_code": 408,
                "body": {"error": "Request timeout"}
            })
        except httpx.ConnectionError:
            return json.dumps({
                "status_code": 503,
                "body": {"error": f"Cannot connect to API at {api_base_url}"}
            })
        except Exception as e:
            return json.dumps({
                "status_code": 500,
                "body": {"error": f"Unexpected error: {str(e)}"}
            })
    
    else:
        return f"Error: Unknown tool '{name}'"


def _extract_answer_and_source(content: str) -> Tuple[str, str]:
    """Extract answer and source from LLM response.
    
    Assumes the LLM may include source in format: wiki/filename.md#section
    Source is optional (can be empty string).
    """
    if content is None:
        return "", ""
    
    lines = content.strip().split("\n")
    answer_lines = []
    source = ""
    
    for line in lines:
        # Look for source pattern
        if "wiki/" in line and ".md#" in line:
            # Extract just the source part
            words = line.split()
            for word in words:
                if "wiki/" in word and ".md#" in word:
                    source = word.strip(".,:;\"'()[]{}")
                    break
            else:
                answer_lines.append(line)
        else:
            answer_lines.append(line)
    
    answer = "\n".join(answer_lines).strip()
    if not source and answer:
        # Try to find source in the whole content
        import re
        match = re.search(r'(wiki/[a-zA-Z0-9_\-/]+\.md#[a-zA-Z0-9\-]+)', content)
        if match:
            source = match.group(1)
    
    return answer, source


async def _call_llm_with_tools(
    messages: List[Dict[str, Any]], 
    api_key: str, 
    api_base: str, 
    model: str
) -> Dict[str, Any]:
    """Call the LLM with tool schemas and return the response."""
    url = f"{api_base.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "tools": _get_tool_schemas(),
        "tool_choice": "auto",
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


async def _agentic_loop(question: str, api_key: str, api_base: str, model: str) -> Dict[str, Any]:
    """Run the agentic loop to answer a question using tools.
    
    Returns:
        Dictionary with answer, source, and tool_calls fields
    """
    # Initialize conversation
    messages = [
        {"role": "system", "content": _get_system_prompt()},
        {"role": "user", "content": question}
    ]
    
    tool_calls_history = []
    iteration = 0
    
    while iteration < MAX_TOOL_CALLS:
        iteration += 1
        print(f"\n--- Iteration {iteration}/{MAX_TOOL_CALLS} ---", file=sys.stderr)
        
        # Call LLM
        response_data = await _call_llm_with_tools(messages, api_key, api_base, model)
        
        # Extract the assistant's message
        try:
            choice = response_data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError) as e:
            print(f"Error: Unexpected LLM response format: {response_data}", file=sys.stderr)
            sys.exit(1)
        
        # Handle content field (can be None when tool_calls present)
        content = message.get("content")
        if content is None:
            content = ""
        
        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": content})
        
        # Check for tool calls
        tool_calls = message.get("tool_calls", [])
        
        if not tool_calls:
            # No tool calls - this is the final answer
            print("  LLM provided final answer (no tool calls)", file=sys.stderr)
            answer, source = _extract_answer_and_source(content)
            
            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_history
            }
        
        # Execute tool calls
        print(f"  LLM requested {len(tool_calls)} tool call(s)", file=sys.stderr)
        for tc in tool_calls:
            function = tc.get("function", {})
            tool_name = function.get("name")
            tool_args = json.loads(function.get("arguments", "{}"))
            tool_call_id = tc.get("id")
            
            # Execute the tool
            result = await _execute_tool({"name": tool_name, "arguments": tool_args})
            
            # Record in history
            tool_calls_history.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result
            })
            
            # Add tool response to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result
            })
            
            print(f"  Tool {tool_name} executed, result length: {len(result)} chars", file=sys.stderr)
    
    # Max iterations reached - use last assistant message
    print(f"\nWarning: Reached maximum of {MAX_TOOL_CALLS} tool calls", file=sys.stderr)
    
    # Find the last assistant message
    last_assistant = None
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            last_assistant = msg
            break
    
    if last_assistant:
        content = last_assistant.get("content", "")
        answer, source = _extract_answer_and_source(content)
    else:
        answer = "Unable to find answer after maximum iterations"
        source = ""
    
    return {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls_history
    }


def main():
    """Main entry point."""
    # Check command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    _load_env()
    api_key, api_base, model = _get_llm_config()

    print(f"Starting agentic loop with model '{model}'...", file=sys.stderr)
    print(f"Question: {question}", file=sys.stderr)
    
    # Log API config for debugging (without exposing keys)
    lms_key, api_url = _get_api_config()
    print(f"API base URL: {api_url}", file=sys.stderr)
    print(f"LMS_API_KEY present: {'Yes' if lms_key else 'No'}", file=sys.stderr)

    # Run the agentic loop
    result = asyncio.run(_agentic_loop(question, api_key, api_base, model))

    # Output JSON to stdout (single line)
    print(json.dumps(result))


if __name__ == "__main__":
    main()