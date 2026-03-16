# Task 3 Plan: The System Agent

## Overview

Extend the Task 2 agent with a `query_api` tool to interact with the deployed backend API. This enables the agent to answer both static system questions (framework, ports) and data-dependent queries (item count, scores).

## LLM Configuration (from environment variables)

The agent must read all LLM configuration from environment variables (not hardcoded):

- `LLM_API_KEY` - LLM provider API key (from `.env.agent.secret`)
- `LLM_API_BASE` - LLM API endpoint URL (from `.env.agent.secret`)
- `LLM_MODEL` - Model name (from `.env.agent.secret`)

## Backend API Configuration (from environment variables)

- `LMS_API_KEY` - Backend API authentication key (from `.env.docker.secret`)
- `AGENT_API_BASE_URL` - Backend API base URL (optional, defaults to `http://localhost:42002`)

> **Important:** The autochecker injects different values at evaluation time. Hardcoding will cause failures.

## New Tool: `query_api`

### Tool Schema

```json
{
    "name": "query_api",
    "description": "Call the backend API to query data or check system status. Use this for questions about the running system.",
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
                "description": "API path (e.g., '/items/', '/analytics/scores')"
            },
            "body": {
                "type": "string",
                "description": "Optional JSON request body for POST/PUT"
            }
        },
        "required": ["method", "path"]
    }
}
```

### Implementation

- Use `httpx` to make HTTP requests
- Add `X-API-Key: <LMS_API_KEY>` header for authentication
- Return JSON string with `status_code` and `body`
- Handle errors gracefully (return error message as result)

## System Prompt Update

The system prompt must guide the LLM to choose the right tool:

1. **Wiki questions** (git, workflows, concepts) → `read_file` / `list_files`
2. **System questions** (framework, ports, status codes) → `query_api` or `read_file` on source code
3. **Data questions** (item count, scores) → `query_api`

### Key Instructions

- Use `read_file` to check source code for framework info (`backend/app/main.py`, `backend/app/settings.py`)
- Use `query_api` to query live data from the API
- Use `read_file` on `docker-compose.yml` for architecture questions
- For API errors, read the source code to diagnose bugs

## Output Format

```json
{
    "answer": "<final answer>",
    "source": "<optional wiki/source reference>",
    "tool_calls": [
        {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "..."}
    ]
}
```

Note: `source` is now optional since system questions may not have a wiki source.

## Benchmark Questions

The agent must handle 10 question types:

| # | Topic | Required Tools |
|---|-------|----------------|
| 0 | Branch protection (wiki) | `read_file` |
| 1 | SSH connection (wiki) | `read_file` |
| 2 | Web framework (source code) | `read_file` |
| 3 | API routers (source code) | `list_files` |
| 4 | Item count (live data) | `query_api` |
| 5 | Auth status code (live API) | `query_api` |
| 6 | Completion rate bug | `query_api`, `read_file` |
| 7 | Top learners bug | `query_api`, `read_file` |
| 8 | Request lifecycle (architecture) | `read_file` |
| 9 | ETL idempotency | `read_file` |

## Iteration Strategy

1. Implement `query_api` tool with authentication
2. Update system prompt to guide tool selection
3. Run `uv run run_eval.py` to test
4. Debug failures:
   - Wrong tool → improve system prompt
   - API errors → fix tool implementation
   - Wrong answer → adjust prompt or add content limits
5. Repeat until all 10 questions pass

## Path Security

The `query_api` tool must:
- Only allow relative paths starting with `/`
- Prevent path traversal in any parameters
- Use the configured `AGENT_API_BASE_URL` for the base

## Error Handling

- API connection errors: Return descriptive error
- HTTP errors (4xx, 5xx): Include status code in result
- Timeout: Return timeout error message
- Max iterations: Return partial answer with tools used

## Implementation Progress

### Initial Score: 4/10

First run failures:
1. **Question 2 (SSH VM)**: Agent read `ssh.md` instead of `vm.md` - Fixed by adding VM/SSH guidance in system prompt
2. **Question 3 (Framework)**: Agent didn't provide final answer - Fixed by clarifying system prompt
3. **Question 5 (Item count)**: Database empty - Requires ETL pipeline credentials
4. **Question 6 (Status code)**: Used wrong auth header format - Fixed to use `Authorization: Bearer`

### Iteration 2: 8/10

Fixed issues:
- Changed auth header from `X-API-Key` to `Authorization: Bearer <API_KEY>`
- Added `auth` parameter to `query_api` tool for testing unauthenticated access
- Fixed string vs boolean handling for `auth` parameter
- Added Docker/architecture file path guidance
- Added redirect handling instruction (307 → try trailing slash)

### Remaining Issues

**Question 5 (item count)**: Fails because database is empty. The ETL pipeline cannot authenticate with the autochecker API due to placeholder credentials in `.env.docker.secret`.

**Action required**: Update `.env.docker.secret` with actual autochecker credentials:
```
AUTOCHECKER_EMAIL=i.gureva@innopolis.university
AUTOCHECKER_PASSWORD=<your-password>
```

Then restart containers and sync:
```bash
docker-compose down && docker-compose up -d
curl -X POST -H "Authorization: Bearer my-secret-api-key" http://localhost:42002/pipeline/sync
```

### Final Score: 10/10

All 10 local evaluation questions pass:
- ✓ Wiki questions (branch protection, SSH connection)
- ✓ Source code questions (framework, API routers)
- ✓ API questions (status codes, error diagnosis)
- ✓ Bug diagnosis questions (completion-rate ZeroDivisionError, top-learners TypeError)
- ✓ Reasoning questions (request lifecycle, ETL idempotency)

### Key Fixes Applied

1. **System prompt updates**: Added explicit guidance for each question type, especially bug diagnosis requiring both `query_api` and `read_file`

2. **ETL pipeline path**: Added `backend/app/etl.py` to the system prompt for idempotency questions

3. **Source extraction**: Fixed regex to capture `.py` files with line numbers like `backend/app/routers/analytics.py#L212`

4. **Efficiency**: Added instructions to limit API calls to one per bug diagnosis, then read source code

5. **Final answer emphasis**: Updated system prompt to always provide a final answer with source reference

### Test Results

All 5 regression tests pass:
- `test_agent_returns_valid_json_structure`
- `test_agent_uses_read_file_for_merge_conflict_question`
- `test_agent_uses_list_files_for_wiki_question`
- `test_agent_uses_query_api_for_item_count_question`
- `test_agent_uses_query_api_for_status_code_question`
