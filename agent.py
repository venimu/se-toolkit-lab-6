#!/usr/bin/env python3
"""Agent CLI that answers questions using an LLM via OpenRouter API.

This agent has tools (read_file, list_files) to navigate the project wiki
and an agentic loop to iteratively call tools until it finds an answer.

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10


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


def validate_path(relative_path: str, project_root: Path) -> Path | None:
    """Validate that a path is within the project directory.

    Args:
        relative_path: Path relative to project root.
        project_root: Absolute path to project root.

    Returns:
        Absolute path if valid, None if path escapes project directory.
    """
    try:
        full_path = (project_root / relative_path).resolve()
        resolved_root = project_root.resolve()
        if not str(full_path).startswith(str(resolved_root)):
            return None
        return full_path
    except (ValueError, OSError):
        return None


def read_file(path: str, project_root: Path) -> str:
    """Read a file from the project repository.

    Args:
        path: Relative path to the file from project root.
        project_root: Absolute path to project root.

    Returns:
        File contents as string, or error message.
    """
    validated = validate_path(path, project_root)
    if validated is None:
        return f"Error: Access denied - path '{path}' is outside project directory"

    if not validated.exists():
        return f"Error: File not found - {path}"

    if not validated.is_file():
        return f"Error: Not a file - {path}"

    try:
        return validated.read_text()
    except (OSError, IOError) as e:
        return f"Error: Could not read file - {e}"


def list_files(path: str, project_root: Path) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative path to the directory from project root.
        project_root: Absolute path to project root.

    Returns:
        Newline-separated listing of entries, or error message.
    """
    validated = validate_path(path, project_root)
    if validated is None:
        return f"Error: Access denied - path '{path}' is outside project directory"

    if not validated.exists():
        return f"Error: Directory not found - {path}"

    if not validated.is_dir():
        return f"Error: Not a directory - {path}"

    try:
        entries = sorted([entry.name for entry in validated.iterdir()])
        return "\n".join(entries)
    except (OSError, IOError) as e:
        return f"Error: Could not list directory - {e}"


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas for LLM function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the project repository. Use this to read wiki files to find answers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file from the project root (e.g., 'wiki/git-workflow.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in a directory within the project repository. Use this to discover what files are available.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the directory from the project root (e.g., 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
    ]


SYSTEM_PROMPT = """You are a documentation agent that answers questions by reading files from a project wiki.

Available tools:
- list_files(path): List files and directories in a directory
- read_file(path): Read the contents of a file

Process:
1. Use list_files to discover relevant wiki files (start with "wiki" directory)
2. Use read_file to read specific files and find the answer
3. Look for section headers in files (lines starting with #, ##, etc.)
4. Include the source reference in your answer using the format: wiki/filename.md#section-anchor

Section anchors are lowercase with hyphens instead of spaces.
For example, "## Resolving Merge Conflicts" becomes "#resolving-merge-conflicts"

When you have found the answer, respond with a final message (no tool calls) that includes:
- A clear answer to the question
- The source reference at the end: SOURCE: wiki/filename.md#section-anchor

Always explore the wiki systematically - start by listing files in the wiki directory, then read relevant files."""


def execute_tool(name: str, args: dict[str, Any], project_root: Path) -> str:
    """Execute a tool and return its result.

    Args:
        name: Tool name.
        args: Tool arguments.
        project_root: Absolute path to project root.

    Returns:
        Tool result as string.
    """
    if name == "read_file":
        path = args.get("path", "")
        return read_file(path, project_root)
    elif name == "list_files":
        path = args.get("path", "")
        return list_files(path, project_root)
    else:
        return f"Error: Unknown tool - {name}"


def extract_source_from_answer(answer: str) -> str:
    """Extract the source reference from the LLM's answer.

    Looks for patterns like:
    - SOURCE: wiki/file.md#anchor
    - Source: wiki/file.md#anchor
    - source: wiki/file.md#anchor

    Args:
        answer: The LLM's answer text.

    Returns:
        Source reference string, or empty string if not found.
    """
    patterns = [
        r"SOURCE:\s*(wiki/[\w\-/.]+#\w[\w\-]*)",
        r"Source:\s*(wiki/[\w\-/.]+#\w[\w\-]*)",
        r"source:\s*(wiki/[\w\-/.]+#\w[\w\-]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, answer, re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def call_llm_with_tools(
    question: str,
    api_key: str,
    api_base: str,
    model: str,
    project_root: Path,
    timeout: int = 60,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Call the LLM with tool support and agentic loop.

    Args:
        question: The user's question.
        api_key: API key for authentication.
        api_base: Base URL of the API.
        model: Model name to use.
        project_root: Absolute path to project root.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (answer, source, tool_calls_list)
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Initialize messages with system prompt and user question
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_list: list[dict[str, Any]] = []
    tool_schemas = get_tool_schemas()

    for iteration in range(MAX_TOOL_CALLS):
        print(f"Iteration {iteration + 1}/{MAX_TOOL_CALLS}", file=sys.stderr)

        # Build payload with tool definitions
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tool_schemas,
            "tool_choice": "auto",
        }

        print(f"Calling LLM API at {url}...", file=sys.stderr)

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            print(
                f"Error: API request timed out after {timeout} seconds", file=sys.stderr
            )
            sys.exit(1)
        except httpx.HTTPError as e:
            print(f"Error: HTTP request failed: {e}", file=sys.stderr)
            if hasattr(e, "response") and e.response:
                print(f"Response: {e.response.text[:500]}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError:
            print("Error: Invalid JSON response from API", file=sys.stderr)
            sys.exit(1)

        # Parse the response
        try:
            choices = data.get("choices", [])
            if not choices:
                print("Error: No choices in API response", file=sys.stderr)
                sys.exit(1)

            message = choices[0].get("message", {})
            content = message.get("content")
            tool_calls = message.get("tool_calls")

        except (KeyError, IndexError, TypeError) as e:
            print(f"Error: Failed to parse API response: {e}", file=sys.stderr)
            print(f"Response: {data}", file=sys.stderr)
            sys.exit(1)

        # Check if LLM wants to call tools
        if tool_calls:
            print(f"LLM requested {len(tool_calls)} tool call(s)", file=sys.stderr)

            # Add assistant message with tool calls to conversation
            messages.append(
                {"role": "assistant", "content": content, "tool_calls": tool_calls}
            )

            # Execute each tool call
            for tool_call in tool_calls:
                tool_id = tool_call.get("id")
                function = tool_call.get("function", {})
                tool_name = function.get("name")
                tool_args_str = function.get("arguments", "{}")

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                print(
                    f"Executing tool: {tool_name} with args: {tool_args}",
                    file=sys.stderr,
                )

                # Execute the tool
                result = execute_tool(tool_name, tool_args, project_root)

                # Record the tool call for output
                tool_calls_list.append(
                    {"tool": tool_name, "args": tool_args, "result": result}
                )

                # Add tool result to conversation
                messages.append(
                    {"role": "tool", "tool_call_id": tool_id, "content": result}
                )

                print(f"Tool result: {result[:200]}...", file=sys.stderr)

            # Continue loop - LLM will process tool results and either call more tools or give answer
            continue

        else:
            # No tool calls - LLM provided final answer
            print(f"LLM provided final answer", file=sys.stderr)
            answer = content or ""

            # Extract source from answer
            source = extract_source_from_answer(answer)

            # Clean up the answer - remove the SOURCE: line if present
            answer_cleaned = re.sub(
                r"\n?\s*(?:SOURCE|Source|source):\s*wiki/[\w\-/.]+#\w[\w\-]*\s*",
                "",
                answer,
            ).strip()

            return answer_cleaned, source, tool_calls_list

    # Max iterations reached
    print("Warning: Maximum tool calls reached", file=sys.stderr)

    # Try to get an answer from the last message
    if messages and messages[-1].get("role") == "assistant":
        answer = messages[-1].get("content", "")
        source = extract_source_from_answer(answer) if answer else ""
        answer_cleaned = (
            re.sub(
                r"\n?\s*(?:SOURCE|Source|source):\s*wiki/[\w\-/.]+#\w[\w\-]*\s*",
                "",
                answer or "",
            ).strip()
            if answer
            else ""
        )
        return answer_cleaned, source, tool_calls_list

    return "Could not find answer within maximum tool calls", "", tool_calls_list


def main() -> None:
    """Main entry point for the agent CLI."""
    # Parse command line arguments
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    api_key, api_base, model = get_llm_config()

    project_root = Path(__file__).parent

    print(f"Using model: {model}", file=sys.stderr)
    print(f"Question: {question}", file=sys.stderr)

    # Call the LLM with tools
    answer, source, tool_calls_list = call_llm_with_tools(
        question, api_key, api_base, model, project_root
    )

    # Output the result as JSON
    result = {"answer": answer, "source": source, "tool_calls": tool_calls_list}

    print(json.dumps(result))


if __name__ == "__main__":
    main()

