#!/usr/bin/env python3
"""CLI agent that answers questions using an LLM.

Usage:
    uv run agent.py "What does REST stand for?"

Output (JSON to stdout):
    {"answer": "Representational State Transfer.", "tool_calls": []}

All debug/logging output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


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


async def _call_llm(question: str, api_key: str, api_base: str, model: str) -> str:
    """Call the LLM and return the answer string."""
    url = f"{api_base.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # System prompt instructs the LLM to respond concisely
    system_prompt = (
        "You are a helpful assistant. Answer the question concisely and accurately. "
        "Respond with only the answer, no extra explanation."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    # Extract the assistant's response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"Error: Unexpected LLM response format: {data}", file=sys.stderr)
        sys.exit(1)

    return answer


def main():
    """Main entry point."""
    import asyncio

    # Check command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    _load_env()
    api_key, api_base, model = _get_llm_config()

    print(f"Calling LLM with model '{model}'...", file=sys.stderr)

    # Call LLM and get answer
    answer = asyncio.run(_call_llm(question, api_key, api_base, model))

    # Build structured output
    output = {
        "answer": answer.strip(),
        "tool_calls": [],
    }

    # Output JSON to stdout (single line)
    print(json.dumps(output))


if __name__ == "__main__":
    main()
