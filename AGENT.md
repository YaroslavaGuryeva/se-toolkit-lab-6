# Agent Architecture

## Overview

This agent is a CLI program that answers questions by calling a Large Language Model (LLM). It forms the foundation for the agentic system that will be extended with tools and an agentic loop in later tasks.

## LLM Provider

**Provider:** Qwen Code API  
**Model:** `qwen3-coder-plus`  
**API Format:** OpenAI-compatible chat completions (`/v1/chat/completions`)

Qwen Code provides 1000 free requests per day, works from Russia, and requires no credit card.

## Architecture

```
User question (CLI arg)
         ↓
   agent.py parses input
         ↓
   Load .env.agent.secret
         ↓
   HTTP POST to LLM API
         ↓
   Parse LLM response
         ↓
   JSON output to stdout
```

## Components

### `agent.py`

The main CLI entry point with:

1. **Agentic Loop** — iterates up to 10 times, calling LLM and executing tools
2. **Tool Execution** — safely executes `list_files` and `read_file` tools
3. **Conversation Management** — maintains message history with tool responses
4. **Output Formatting** — produces JSON with answer, source, and tool call history

## Tools

### 1. `list_files`

Lists files and directories at a given path.

| Property | Description |
|----------|-------------|
| **Description** | List files and directories at a given path |
| **Parameters** | `path` (string): Relative directory path from project root |
| **Returns** | Newline-separated listing of entries, or error message |
| **Security** | Blocks paths containing `..`; ensures path is within project root |

### 2. `read_file`

Reads a file from the project repository.

| Property | Description |
|----------|-------------|
| **Description** | Read a file from the project repository |
| **Parameters** | `path` (string): Relative file path from project root |
| **Returns** | File contents as string, or error message |
| **Security** | Blocks paths containing `..`; ensures path is within project root; only reads files |

## System Prompt Strategy

The system prompt instructs the LLM to:

1. **Explore first** — use `list_files` to discover relevant wiki files
2. **Read specific files** — use `read_file` to find answers
3. **Include source** — format answers with source references like `wiki/filename.md#section`
4. **Be concise** — provide direct answers without extra explanation

## Output Format

The agent outputs a single JSON line to stdout:

```
json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\nadvanced-topics.md\n"
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n## Resolving Merge Conflicts\nWhen you encounter a merge conflict..."
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

## Extension Points (Future Tasks)

- **Task 2:** Add tools (e.g., `read_file`, `query_api`) and populate `tool_calls`
- **Task 3:** Implement the agentic loop (plan → act → observe → repeat)
