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


def test_agent_uses_read_file_for_merge_conflict_question():
    """Test that agent uses read_file tool to answer merge conflict question."""
    result = subprocess.run(
        [sys.executable, "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    data = json.loads(result.stdout)

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert "tool_calls" in data, "Missing 'tool_calls' field"

    # Check that read_file was used
    tool_names = [call["tool"] for call in data["tool_calls"]]
    assert "read_file" in tool_names, "Expected read_file to be called"

    # Check answer mentions merge conflict concepts
    answer_lower = data["answer"].lower()
    conflict_keywords = ["conflict", "merge", "branch", "commit", "marker", "resolve"]
    has_keyword = any(kw in answer_lower for kw in conflict_keywords)
    assert has_keyword, f"Expected answer to mention merge conflict concepts, got: {data['answer']}"

    # Check answer is not empty
    assert len(data["answer"].strip()) > 0, "'answer' should not be empty"


def test_agent_uses_list_files_for_wiki_question():
    """Test that agent uses list_files tool when asked about wiki files."""
    result = subprocess.run(
        [sys.executable, "agent.py", "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    data = json.loads(result.stdout)

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert "tool_calls" in data, "Missing 'tool_calls' field"

    # Check that list_files was used
    tool_names = [call["tool"] for call in data["tool_calls"]]
    assert "list_files" in tool_names, "Expected list_files to be called"

    # Check answer is not empty
    assert len(data["answer"].strip()) > 0, "'answer' should not be empty"


def test_agent_uses_query_api_for_item_count_question():
    """Test that agent uses query_api tool when asked about database item count."""
    result = subprocess.run(
        [sys.executable, "agent.py", "How many items are currently stored in the database? Query the running API to find out."],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    data = json.loads(result.stdout)

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert "tool_calls" in data, "Missing 'tool_calls' field"

    # Check that query_api was used
    tool_names = [call["tool"] for call in data["tool_calls"]]
    assert "query_api" in tool_names, "Expected query_api to be called"

    # Check answer is not empty
    assert len(data["answer"].strip()) > 0, "'answer' should not be empty"


def test_agent_uses_query_api_for_status_code_question():
    """Test that agent uses query_api tool when asked about HTTP status codes."""
    result = subprocess.run(
        [sys.executable, "agent.py", "What HTTP status code does the API return when you request /items/ without an authentication header?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    data = json.loads(result.stdout)

    # Check required fields
    assert "answer" in data, "Missing 'answer' field"
    assert "tool_calls" in data, "Missing 'tool_calls' field"

    # Check that query_api was used
    tool_names = [call["tool"] for call in data["tool_calls"]]
    assert "query_api" in tool_names, "Expected query_api to be called"

    # Check answer mentions 401 or 403
    answer_lower = data["answer"].lower()
    assert "401" in answer_lower or "403" in answer_lower or "unauthorized" in answer_lower or "forbidden" in answer_lower, \
        f"Expected answer to mention 401/403 status code, got: {data['answer']}"

    # Check answer is not empty
    assert len(data["answer"].strip()) > 0, "'answer' should not be empty"
