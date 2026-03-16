# Agent Architecture

## Overview

This project implements an AI-powered system agent CLI (`agent.py`) that answers questions by reading the project wiki, source code, and querying the live backend API. The agent has tools to navigate the file system, query the API, and an agentic loop that allows iterative tool use until it finds the answer.

## Architecture

### Data Flow

```
User Question → LLM (with tool definitions) → Tool Calls → Execute Tools → Results → LLM → Final Answer
```

### Components

1. **`agent.py`** - Main CLI entry point with agentic loop
2. **Tools** - `read_file`, `list_files`, and `query_api` for wiki navigation and API queries
3. **Configuration** (from environment variables)
   - `LLM_API_KEY` - LLM provider API key (from `.env.agent.secret`)
   - `LLM_API_BASE` - Base URL of the LLM API endpoint (from `.env.agent.secret`)
   - `LLM_MODEL` - Model name to use (from `.env.agent.secret`)
   - `LMS_API_KEY` - Backend API authentication key (from `.env.docker.secret`)
   - `AGENT_API_BASE_URL` - Backend API base URL (optional, defaults to `http://localhost:42002`)

### LLM Provider

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus`
- **Endpoint**: OpenAI-compatible `/v1/chat/completions`

## Tools

The agent has three tools registered as function-calling schemas:

### `read_file`

Reads contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git.md`)

**Security:**
- Rejects paths containing `..` (path traversal prevention)
- Rejects absolute paths
- Validates resolved path is within project directory

**Returns:** File contents as string, or error message if file doesn't exist

### `list_files`

Lists files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Security:**
- Same path validation as `read_file`

**Returns:** Newline-separated list of entry names

### `query_api`

Calls the backend API to query data or check system status.

**Parameters:**
- `method` (string, required): HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional): JSON request body for POST/PUT requests
- `auth` (boolean, optional): Whether to include authentication header (default: true)

**Authentication:**
- Uses `Authorization: Bearer <LMS_API_KEY>` header when `auth=true`
- Set `auth=false` to test unauthenticated access (e.g., checking 401 responses)

**Returns:** JSON string with `status_code` and `body`, or error message

## Agentic Loop

The agent runs an iterative loop:

1. **Send request**: User question + system prompt + tool definitions to LLM
2. **Check response**:
   - If `tool_calls` present → execute tools, append results, go to step 1
   - If no `tool_calls` → final answer found, output JSON and exit
3. **Max iterations**: Stops after 10 tool calls maximum

### Message History

The agent maintains full conversation history:
- `system`: System prompt with instructions
- `user`: User's question
- `assistant`: LLM responses (may include tool_calls)
- `tool`: Tool execution results

### System Prompt Strategy

The system prompt guides the LLM to choose the right tool based on question type:

1. **Wiki questions** (git workflows, concepts, how-to) → `read_file` on wiki/*.md files
2. **VM/SSH questions** → `read_file` on wiki/vm.md or wiki/ssh.md
3. **Source code questions** (framework, architecture) → `read_file` on backend/app/*.py or docker-compose.yml
4. **Docker/architecture questions** → `read_file` on Dockerfile, docker-compose.yml, caddy/Caddyfile
5. **Live data questions** (item count, scores) → `query_api` with auth=true
6. **API behavior questions** (status codes) → `query_api`; use auth=false for unauthenticated tests
7. **Bug diagnosis** → `query_api` to reproduce error, then `read_file` to examine source code

Key instructions:
- Provide final answer with actual content found, not just what file was read
- Handle API redirects (307) by trying path with trailing slash
- Stop calling tools once answer is found (max 10 calls)

## Output Format

```json
{
  "answer": "<final answer text>",
  "source": "wiki/<file>.md#<section-anchor>",
  "tool_calls": [
    {
      "tool": "read_file",
      "args": {"path": "wiki/git.md"},
      "result": "# Git\n\nGit is a distributed..."
    },
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/", "auth": true},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

### Fields

- **`answer`** (string): The LLM's final answer
- **`source`** (string): File reference with section anchor, or "API" for API queries
- **`tool_calls`** (array): All tool calls made during the agentic loop

## How to Run

### Prerequisites

1. Set up `.env.agent.secret` with your LLM credentials:
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit with your API key, base URL, and model
   ```

2. Ensure the backend API is running (via docker-compose)

3. Ensure the Qwen Code API is running on your VM

### Usage

```bash
uv run agent.py "Your question here"
```

### Examples

**Question about merge conflicts:**
```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**Question about item count:**
```bash
uv run agent.py "How many items are in the database?"
```

**Question about API status codes:**
```bash
uv run agent.py "What status code does /items/ return without auth?"
```

## Important Notes

- **stdout**: Only valid JSON (for piping and testing)
- **stderr**: All debug/progress messages
- **Exit code**: 0 on success, 1 on failure
- **Timeout**: 60 seconds per API call
- **Max tool calls**: 10 per question

## Testing

Run all regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

### Tests

1. **`test_agent_returns_valid_json_structure`**: Verifies basic JSON output format
2. **`test_agent_uses_read_file_for_merge_conflict_question`**: Tests tool usage for documentation lookup
3. **`test_agent_uses_list_files_for_wiki_question`**: Tests directory listing functionality
4. **`test_agent_uses_query_api_for_item_count_question`**: Tests query_api for data questions
5. **`test_agent_uses_query_api_for_status_code_question`**: Tests query_api with auth=false

## Lessons Learned from Benchmark

### Challenges Encountered

1. **Authentication Header Format**: Initially used `X-API-Key` header, but backend expects `Authorization: Bearer <API_KEY>`. Fixed by updating the header format in `query_api`.

2. **String vs Boolean for `auth` Parameter**: The LLM sometimes passes `"auth": "False"` (string) instead of `false` (boolean). Added type checking in `execute_tool` to handle both cases.

3. **System Prompt Clarity**: The agent was not providing final answers, instead describing what it would do. Updated the system prompt to emphasize providing actual content found.

4. **File Path Guidance**: The agent was looking for `backend/Dockerfile` instead of root `Dockerfile`. Added explicit path guidance in the system prompt for Docker/architecture questions.

5. **VM SSH Question**: The agent was reading `ssh.md` instead of `vm.md` for VM connection questions. Added specific guidance for VM/SSH questions in the tool selection guide.

6. **API Redirect Handling**: The agent encountered 307 redirects for `/items` vs `/items/`. Added instruction to try trailing slash on redirects.

7. **Source Extraction for Code Files**: The original regex only matched `.md` files. Updated `extract_source()` to capture `.py` files with line numbers like `backend/app/routers/analytics.py#L212`.

8. **Bug Diagnosis Tool Usage**: The agent was making multiple API calls without reading source code. Added explicit instructions to ALWAYS read `backend/app/routers/analytics.py` after reproducing an error.

9. **ETL Pipeline Path**: The agent couldn't find the ETL pipeline code. Added `backend/app/etl.py` to the system prompt with guidance about `external_id` checks for idempotency.

10. **Efficiency in Tool Calls**: The agent was wasting iterations trying multiple lab values. Added instructions to make ONE API call, then read the source code.

### Benchmark Results

**Final Score: 10/10** - All local evaluation questions pass:
- ✓ Wiki questions (branch protection, SSH connection)
- ✓ Source code questions (framework, API routers)
- ✓ API questions (status codes, item count)
- ✓ Bug diagnosis questions (completion-rate ZeroDivisionError, top-learners TypeError)
- ✓ Reasoning questions (request lifecycle, ETL idempotency)

### Final Architecture

The agent successfully answers questions across four categories:

1. **Wiki Lookup**: Uses `list_files` to discover files, then `read_file` to find answers
2. **System Facts**: Uses `read_file` on source code to find framework, ports, status codes
3. **Data Queries**: Uses `query_api` with authentication to fetch live data
4. **Bug Diagnosis**: Uses `query_api` to reproduce errors, then `read_file` to identify buggy lines

### Key Success Factors

1. **Explicit System Prompt**: Detailed tool selection guide for each question type
2. **Path Guidance**: Specific file paths for common questions (e.g., `backend/app/etl.py` for ETL)
3. **Efficiency Constraints**: Limit API calls, prioritize reading source code for bugs
4. **Source Extraction**: Robust regex to capture both `.md` and `.py` file references
5. **Final Answer Emphasis**: Clear instructions to provide actual content, not just describe actions

## Development

### Adding New Tools

To add a new tool:

1. Implement the tool function with path security validation
2. Add tool schema to `TOOLS` list
3. Update `execute_tool()` to handle the new tool
4. Update system prompt if needed

### Path Security

All tools validate paths to prevent directory traversal:
- Reject `..` in paths
- Reject absolute paths
- Verify resolved path is within project root using `Path.resolve().is_relative_to()`

### Environment Variable Handling

The agent reads all configuration from environment variables via `pydantic_settings`:
- Loads from `.env.agent.secret` and `.env.docker.secret`
- Uses sensible defaults (e.g., `AGENT_API_BASE_URL=http://localhost:42002`)
- Allows autochecker to inject different values at evaluation time
