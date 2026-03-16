# Task 1 Plan: Call an LLM from Code

## LLM Provider Configuration

- **Provider**: Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus`
- **API Base URL**: `http://10.93.26.23:42005/v1`
- **Authentication**: API key stored in `.env.agent.secret` (not hardcoded)

## Agent Architecture

### Input/Output Flow

```
Command line argument → agent.py → HTTP POST to LLM API → Parse response → JSON to stdout
```

### Components

1. **Configuration Loading**
   - Use `pydantic-settings` to load environment variables from `.env.agent.secret`
   - Required settings: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

2. **Command-Line Interface**
   - Read question from `sys.argv[1]`
   - Validate that a question was provided

3. **LLM Client**
   - Use `httpx` to make synchronous POST request to `/v1/chat/completions`
   - Request format (OpenAI-compatible):
     ```json
     {
       "model": "qwen3-coder-plus",
       "messages": [{"role": "user", "content": "<question>"}]
     }
     ```
   - Headers: `Content-Type: application/json`, `Authorization: Bearer <API_KEY>`

4. **Response Processing**
   - Extract `choices[0].message.content` from LLM response
   - Build output JSON: `{"answer": "<content>", "tool_calls": []}`
   - Output to stdout as single-line JSON

5. **Error Handling**
   - Catch HTTP errors and LLM API errors
   - Print debug info to stderr
   - Exit with non-zero code on failure

### Output Rules

- **stdout**: Only valid JSON (for piping/testing)
- **stderr**: All debug/progress messages
- **Exit code**: 0 on success, non-zero on failure
- **Timeout**: 60 seconds max for API response

## Test Strategy

One regression test (`tests/test_agent.py` already exists):
- Run `agent.py` as subprocess with a simple question
- Parse stdout as JSON
- Verify `answer` and `tool_calls` fields exist with correct types
