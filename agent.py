
## 2. Updated agent.py with Agentic Loop

```python
#!/usr/bin/env python3
"""CLI agent that answers questions using an LLM with tool calling.

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output (JSON to stdout):
    {
        "answer": "Edit the conflicting file, choose which changes to keep...",
        "source": "wiki/git-workflow.md#resolving-merge-conflicts",
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

import httpx


# Constants
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent.absolute()


def _load_env():
    """Load environment variables from .env.agent.secret."""
    env_file = Path(".env.agent.secret")
    if not env_file.exists():
        print(f"Error: {env_file} not found. Copy .env.agent.example to .env.agent.secret and configure it.", file=sys.stderr)
        sys.exit(1)

    for line in env_file.read_text().splitlines():
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


def _get_tool_schemas() -> List[Dict[str, Any]]:
    """Return the tool schemas for function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root"
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
                "description": "Read a file from the project repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative file path from project root"
                        }
                    },
                    "required": ["path"]
                }
            }
        }
    ]


def _get_system_prompt() -> str:
    """Return the system prompt for the LLM."""
    return """
You are a documentation assistant with access to a wiki repository.
Your goal is to answer questions using the wiki files.

Available tools:
- list_files(path): List contents of a directory
- read_file(path): Read contents of a file

Instructions:
1. First, use list_files to discover relevant wiki files
2. Then use read_file to read specific files and find the answer
3. When answering, include the source reference as:
   wiki/filename.md#section-name
   (Use the exact file path and a relevant section anchor)

Always explore the wiki structure before answering. If you need more information,
call additional tools. When you have the complete answer, respond with it directly.
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
            return safe_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    else:
        return f"Error: Unknown tool '{name}'"


def _extract_answer_and_source(content: str) -> Tuple[str, str]:
    """Extract answer and source from LLM response.
    
    Assumes the LLM includes source in format: wiki/filename.md#section
    If no source found, defaults to empty string.
    """
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
    messages: List[Dict[str, str]], 
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
        
        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": message.get("content", "")})
        
        # Check for tool calls
        tool_calls = message.get("tool_calls", [])
        
        if not tool_calls:
            # No tool calls - this is the final answer
            print("  LLM provided final answer (no tool calls)", file=sys.stderr)
            content = message.get("content", "")
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

    # Run the agentic loop
    result = asyncio.run(_agentic_loop(question, api_key, api_base, model))

    # Output JSON to stdout (single line)
    print(json.dumps(result))


if __name__ == "__main__":
    main()