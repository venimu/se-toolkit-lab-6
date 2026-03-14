#!/usr/bin/env python3
"""Agent CLI that answers questions using an LLM via OpenRouter API.

Usage:
    uv run agent.py "What does REST stand for?"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx


def load_env(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}
    if not env_path.exists():
        return env_vars

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env_vars[key] = value

    return env_vars


def get_llm_config() -> tuple[str, str, str]:
    """Load LLM configuration from .env.agent.secret.

    Returns:
        Tuple of (api_key, api_base, model)

    Raises:
        SystemExit: If required configuration is missing.
    """
    project_root = Path(__file__).parent
    env_path = project_root / ".env.agent.secret"

    env_vars = load_env(env_path)

    api_key = env_vars.get("LLM_API_KEY", "").strip()
    api_base = env_vars.get("LLM_API_BASE", "").strip()
    model = env_vars.get("LLM_MODEL", "").strip()

    if not api_key:
        print("Error: LLM_API_KEY not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not api_base:
        print("Error: LLM_API_BASE not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not model:
        print("Error: LLM_MODEL not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return api_key, api_base, model


def call_llm(question: str, api_key: str, api_base: str, model: str, timeout: int = 60) -> str:
    """Call the LLM API and get a response.

    Args:
        question: The user's question.
        api_key: API key for authentication.
        api_base: Base URL of the API.
        model: Model name to use.
        timeout: Request timeout in seconds.

    Returns:
        The LLM's response text.

    Raises:
        SystemExit: If the API call fails.
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": question}
        ],
    }

    print(f"Calling LLM API at {url}...", file=sys.stderr)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        print(f"Error: API request timed out after {timeout} seconds", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error: HTTP request failed: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text[:500]}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from API", file=sys.stderr)
        sys.exit(1)

    # Extract the answer from the response
    try:
        choices = data.get("choices", [])
        if not choices:
            print("Error: No choices in API response", file=sys.stderr)
            sys.exit(1)

        answer = choices[0].get("message", {}).get("content", "")
        if not answer:
            print("Error: Empty message in API response", file=sys.stderr)
            sys.exit(1)

        return answer
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error: Failed to parse API response: {e}", file=sys.stderr)
        print(f"Response: {data}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point for the agent CLI."""
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    api_key, api_base, model = get_llm_config()

    print(f"Using model: {model}", file=sys.stderr)
    print(f"Question: {question}", file=sys.stderr)

    # Call the LLM
    answer = call_llm(question, api_key, api_base, model)

    # Output the result as JSON
    result = {
        "answer": answer,
        "tool_calls": []
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
