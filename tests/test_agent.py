#!/usr/bin/env python3
"""Regression tests for agent.py.

These tests run agent.py as a subprocess and verify:
1. The output is valid JSON
2. The 'answer' field is present and non-empty
3. The 'tool_calls' field is present and is an array
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent
AGENT_PATH = PROJECT_ROOT / "agent.py"


def run_agent(question: str, timeout: int = 60) -> tuple[dict, str, str]:
    """Run agent.py with the given question.

    Args:
        question: The question to ask the agent.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (parsed_json, stdout, stderr)

    Raises:
        AssertionError: If the agent fails or output is invalid.
    """
    result = subprocess.run(
        [sys.executable, str(AGENT_PATH), question],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=PROJECT_ROOT,
    )

    return result.stdout, result.stderr, result.returncode


class TestAgentOutput:
    """Tests for agent.py output format and content."""

    def test_agent_returns_valid_json(self):
        """Test that agent.py outputs valid JSON."""
        stdout, stderr, returncode = run_agent("What is 2+2?")

        assert returncode == 0, f"Agent exited with code {returncode}:\n{stderr}"
        assert stdout.strip(), "Agent produced no output"

        # Should be valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Agent output is not valid JSON: {stdout[:200]}\nError: {e}")

    def test_agent_returns_answer_field(self):
        """Test that agent.py returns an 'answer' field."""
        stdout, stderr, returncode = run_agent("What is the capital of France?")

        assert returncode == 0, f"Agent exited with code {returncode}:\n{stderr}"

        data = json.loads(stdout)

        assert "answer" in data, "Missing 'answer' field in output"
        assert data["answer"], "'answer' field is empty"
        assert isinstance(data["answer"], str), "'answer' should be a string"

    def test_agent_returns_tool_calls_field(self):
        """Test that agent.py returns a 'tool_calls' field as an array."""
        stdout, stderr, returncode = run_agent("What does API stand for?")

        assert returncode == 0, f"Agent exited with code {returncode}:\n{stderr}"

        data = json.loads(stdout)

        assert "tool_calls" in data, "Missing 'tool_calls' field in output"
        assert isinstance(data["tool_calls"], list), "'tool_calls' should be an array"

    def test_agent_answer_is_reasonable(self):
        """Test that the agent's answer contains expected content."""
        stdout, stderr, returncode = run_agent("What is 2+2?")

        assert returncode == 0, f"Agent exited with code {returncode}:\n{stderr}"

        data = json.loads(stdout)
        answer = data["answer"].lower()

        # The answer should contain "4" or "four"
        assert "4" in answer or "four" in answer, (
            f"Answer should contain '4' or 'four'. Got: {data['answer']}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
