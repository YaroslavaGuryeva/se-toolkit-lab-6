# Task 2 Plan: The Documentation Agent

## Overview

Extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop that allows the LLM to iteratively query the wiki documentation.

## LLM Configuration

- **Provider**: Qwen Code API (same as Task 1)
- **Model**: `qwen3-coder-plus`
- **API Base**: `http://10.93.26.23:42005/v1`

## Tool Definitions

### Tool Schema Format

Use OpenAI-compatible function calling schema. Each tool has:
- `name`: Tool identifier
- `description`: What the tool does
- `parameters`: JSON Schema for arguments

### `read_file` Tool

```python
{
    "name": "read_file",
    "description": "Read contents of a file from the project repository",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path from project root"}
        },
        "required": ["path"]
    }
}
```

**Implementation:**
- Validate path doesn't contain `..` or start with `/`
- Use `Path.cwd() / path` to resolve absolute path
- Check resolved path is within project directory
- Return file contents or error message

### `list_files` Tool

```python
{
    "name": "list_files",
    "description": "List files and directories at a given path",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path from project root"}
        },
        "required": ["path"]
    }
}
```

**Implementation:**
- Same path security validation as `read_file`
- Return newline-separated list of entries

## Agentic Loop

### Message Flow

1. **Initial request**: Send user question + system prompt + tool definitions
2. **LLM response**: Check for `tool_calls` in response
3. **If tool calls exist**:
   - Execute each tool with provided arguments
   - Append tool results as `{"role": "tool", ...}` messages
   - Send back to LLM for next iteration
4. **If no tool calls**: LLM has final answer → extract and return

### Loop Limits

- **Maximum iterations**: 10 tool calls total
- **Message history**: Maintain full conversation for context

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover wiki structure
2. Use `read_file` to find relevant information
3. Include the source file path in the final answer
4. Stop calling tools once the answer is found

## Output Format

```json
{
    "answer": "<final answer text>",
    "source": "wiki/<file>.md#<section-anchor>",
    "tool_calls": [
        {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
        {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
    ]
}
```

## Path Security

Prevent directory traversal attacks:
1. Reject paths containing `..`
2. Reject absolute paths (starting with `/`)
3. Resolve path and verify it's within project root using `Path.resolve().is_relative_to()`

## Test Strategy

Two new regression tests:
1. **Merge conflict question**: `"How do you resolve a merge conflict?"`
   - Expects `read_file` in tool_calls
   - Expects `wiki/git-workflow.md` in source
2. **Wiki listing question**: `"What files are in the wiki?"`
   - Expects `list_files` in tool_calls

## Error Handling

- File not found: Return error message as tool result
- Path traversal attempt: Return security error
- LLM API error: Exit with error code
- Max iterations reached: Return partial answer with tools used
