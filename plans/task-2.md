# Task 2: Agentic Loop Plan

## Overview

Build an agentic loop that allows the LLM to use tools (`read_file`, `list_files`) to find answers in the project documentation.

## LLM Provider

- **Provider:** Qwen Code API
- **Model:** `qwen3-coder-plus`
- **API:** OpenAI-compatible chat completions with function calling

---

## Tool Definitions

### `read_file`

**Purpose:** Read the contents of a file from the project repository.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read the contents of a file from the project repository.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path in the project repository.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki'). Defaults to '.'"
      }
    },
    "required": ["path"]
  }
}
```

---

## Agentic Loop Design

### Message Flow

```
1. User question → messages = [{"role": "user", "content": question}]
2. Call LLM with messages + tools
3. If LLM returns tool_calls:
   - Execute each tool
   - Append tool results as {"role": "tool", ...}
   - Go to step 2
4. If LLM returns text (no tool_calls):
   - Parse JSON for answer + source
   - Return final output
```

### Message History Example

After 2 tool calls, the message list looks like:

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "How do you resolve a merge conflict?"},
    {"role": "assistant", "tool_calls": [{"id": "call_1", "name": "list_files", "arguments": {"path": "wiki"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "git-workflow.md\nREADME.md"},
    {"role": "assistant", "tool_calls": [{"id": "call_2", "name": "read_file", "arguments": {"path": "wiki/git-workflow.md"}}]},
    {"role": "tool", "tool_call_id": "call_2", "content": "# Git Workflow\n..."},
]
```

### Loop Limit

- Maximum **10 iterations** (tool call cycles)
- If limit reached: return partial answer with all tool_calls made so far

---

## System Prompt

```
You are a helpful assistant that answers questions using the project documentation.

Strategy:
1. Use list_files to discover wiki files
2. Use read_file to read relevant files
3. Always include a source reference (file path + section anchor like: wiki/git-workflow.md#resolving-merge-conflicts)

Respond in JSON format:
{
  "answer": "your answer here",
  "source": "wiki/filename.md#section-anchor"
}

If you need to use tools, respond with tool_calls. If you have the answer, respond with JSON in your message content.
```

---

## Path Security

### Problem

Prevent reading files outside the project directory (e.g., `../../../etc/passwd`).

### Solution

```python
from pathlib import Path

def is_safe_path(path: str) -> bool:
    """Check if path is within project root."""
    # Resolve to absolute path
    full_path = (Path.cwd() / path).resolve()
    # Check it's within project root
    return str(full_path).startswith(str(Path.cwd().resolve()))
```

**Usage:** Each tool validates the path before reading/listing.

---

## Output Format

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

**Fields:**
- `answer` (string, required): The final answer
- `source` (string, required): Wiki section reference
- `tool_calls` (array, required): All tool calls made during the loop

---

## Implementation Steps

1. Define tool schemas (Python dicts)
2. Implement `read_file` and `list_files` functions with path validation
3. Implement the agentic loop:
   - Call LLM with messages + tools
   - Parse tool_calls from response
   - Execute tools, collect results
   - Append tool messages to history
   - Repeat until no tool_calls or max iterations
4. Parse final JSON answer from LLM
5. Build output with answer, source, and tool_calls

---

## Error Handling

- **File not found:** Tool returns error message, LLM decides next step
- **Invalid path:** Tool returns error, LLM tries different path
- **LLM timeout:** Exit with error message
- **JSON parse failure:** Return error in answer field

---

## Testing Strategy

**Test 1:** "How do you resolve a merge conflict?"
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2:** "What files are in the wiki?"
- Expected: `list_files` in tool_calls
