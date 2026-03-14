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

The main CLI entry point with the following responsibilities:

1. **Argument parsing** — reads the question from `sys.argv[1]`
2. **Environment loading** — reads `.env.agent.secret` for LLM credentials
3. **LLM invocation** — makes an async HTTP request to the LLM API
4. **Response formatting** — wraps the LLM's answer in a structured JSON format

### Environment Configuration (`.env.agent.secret`)

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for authentication |
| `LLM_API_BASE` | Base URL of the LLM API (e.g., `http://vm-ip:port/v1`) |
| `LLM_MODEL` | Model name (e.g., `qwen3-coder-plus`) |

## Output Format

The agent outputs a single JSON line to stdout:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's answer to the question |
| `tool_calls` | array | Empty for Task 1; will contain tool invocations in Task 2+ |

All debug and progress output goes to **stderr** to keep stdout clean for JSON parsing.

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Example output
{"answer": "REST stands for Representational State Transfer.", "tool_calls": []}
```

## Setup

1. Copy the environment template:
   ```bash
   cp .env.agent.example .env.agent.secret
   ```

2. Edit `.env.agent.secret` and fill in your credentials:
   ```
   LLM_API_KEY=your-api-key-here
   LLM_API_BASE=http://your-vm-ip:port/v1
   LLM_MODEL=qwen3-coder-plus
   ```

3. Run the agent:
   ```bash
   uv run agent.py "Your question here"
   ```

## Error Handling

- Missing `.env.agent.secret` → exits with error message to stderr
- Missing environment variables → exits with configuration error
- LLM API failure → exits with HTTP error details
- Timeout (60s) → exits with timeout message

## Extension Points (Future Tasks)

- **Task 2:** Add tools (e.g., `read_file`, `query_api`) and populate `tool_calls`
- **Task 3:** Implement the agentic loop (plan → act → observe → repeat)
