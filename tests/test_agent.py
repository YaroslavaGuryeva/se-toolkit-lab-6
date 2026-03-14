"""Regression tests for agent.py CLI."""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_returns_valid_json_structure():
    """Test that agent.py outputs valid JSON with required fields."""
    # Run agent.py with a simple question
    result = subprocess.run(
        [sys.executable, "agent.py", "What is Python?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    data = json.loads(result.stdout)

    # Check required fields exist
    assert "answer" in data, "Missing 'answer' field in output"
    assert "tool_calls" in data, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(data["answer"], str), "'answer' should be a string"
    assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"

    # Check answer is not empty
    assert len(data["answer"].strip()) > 0, "'answer' should not be empty"
