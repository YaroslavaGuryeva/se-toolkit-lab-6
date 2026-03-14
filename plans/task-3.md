# Task 3: System-Aware Agent with API Integration - Implementation Plan

## New Tool: `query_api`

### Tool Schema (OpenAI Function Calling Format)

```json
{
  "name": "query_api",
  "description": "Send HTTP requests to the backend API to get live system data",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "enum": ["GET", "POST", "PUT", "DELETE"],
        "description": "HTTP method for the request"
      },
      "path": {
        "type": "string",
        "description": "API path (e.g., /items/, /analytics/completion-rate?lab=lab-99)"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
``` 

## Implementation Details

Authentication: Use LMS_API_KEY from environment (via Bearer token)

Base URL: AGENT_API_BASE_URL (defaults to http://localhost:42002)

Error Handling: Return structured JSON with status_code and body

Security: Validate URLs to prevent SSRF (only allow configured base URL)

## System Prompt Strategy Update

The system prompt needs to teach the LLM when to use each tool:

python
system_prompt = """
You are a system-aware assistant with access to:
1. Wiki documentation (via list_files/read_file)
2. Source code (via read_file)
3. Live API data (via query_api)

Tool selection guide:
- Use list_files/read_file for: documentation questions, code analysis, configuration files
- Use query_api for: live system data, item counts, API behavior, error responses

When answering:
1. For wiki questions: read files and cite source with wiki/filename.md#section
2. For code questions: read source files and explain the implementation
3. For API questions: query the endpoint and interpret the response
4. For bug diagnosis: query API first to see error, then read source to find the bug

Always include the source for wiki/code answers. For API answers, source is optional.
"""

## Iteration Strategy

First pass: Implement basic query_api tool with authentication

Second pass: Fix parameter handling and error responses

Third pass: Improve tool descriptions based on benchmark failures

Fourth pass: Handle edge cases (null content, large responses)

## Security Considerations

- Use _safe_url_join() to prevent path traversal in API paths
- Validate that requests only go to configured base URL
- Never expose authentication keys in responses
- Limit response size to prevent token overflow