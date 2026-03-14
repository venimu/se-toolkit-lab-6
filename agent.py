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
MAX_TOOL_CALLS = 15


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


def get_api_config() -> tuple[str, str]:
    """Load backend API configuration from environment and .env.docker.secret.

    Returns:
        Tuple of (lms_api_key, agent_api_base_url)

    Raises:
        SystemExit: If LMS_API_KEY is missing.
    """
    project_root = Path(__file__).parent

    # First check environment variables (for autochecker)
    lms_api_key = os.environ.get("LMS_API_KEY", "").strip()
    agent_api_base_url = os.environ.get("AGENT_API_BASE_URL", "").strip()

    # If not in environment, try to load from .env.docker.secret
    if not lms_api_key:
        env_path = project_root / ".env.docker.secret"
        env_vars = load_env(env_path)
        lms_api_key = env_vars.get("LMS_API_KEY", "").strip()
        if not agent_api_base_url:
            caddy_port = env_vars.get("CADDY_HOST_PORT", "42002")
            agent_api_base_url = f"http://localhost:{caddy_port}"

    # Default to localhost:42002 if still not set
    if not agent_api_base_url:
        agent_api_base_url = "http://localhost:42002"

    if not lms_api_key:
        print(
            "Error: LMS_API_KEY not found in environment or .env.docker.secret",
            file=sys.stderr,
        )
        sys.exit(1)

    return lms_api_key, agent_api_base_url


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
    except ValueError, OSError:
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


def query_api(
    method: str, path: str, body: str | None, api_base_url: str, api_key: str
) -> str:
    """Call the backend API and return the response.

    Args:
        method: HTTP method (GET, POST, etc.).
        path: API path (e.g., '/items/').
        body: Optional JSON request body for POST/PUT requests.
        api_base_url: Base URL of the backend API.
        api_key: API key for authentication.

    Returns:
        JSON string with status_code and body, or error message.
    """
    url = f"{api_base_url.rstrip('/')}{path}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        with httpx.Client(timeout=30) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, content=body or "{}")
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, content=body or "{}")
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            elif method.upper() == "PATCH":
                response = client.patch(url, headers=headers, content=body or "{}")
            else:
                return f"Error: Unsupported HTTP method - {method}"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result)

    except httpx.TimeoutException:
        return f"Error: API request timed out - {url}"
    except httpx.HTTPError as e:
        return f"Error: HTTP request failed - {e}"
    except Exception as e:
        return f"Error: Request failed - {e}"


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas for LLM function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the project repository. Use this to read wiki files or source code to find answers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to the file from the project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')",
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
                            "description": "Relative path to the directory from the project root (e.g., 'wiki' or 'backend/app/routers')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Call the backend API to fetch data or test endpoints. Use this for questions about the running system, database contents, API behavior, or HTTP status codes. The API base URL is http://localhost:42002 (or from AGENT_API_BASE_URL env var).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                            "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                        },
                        "path": {
                            "type": "string",
                            "description": "API path (e.g., '/items/', '/analytics/completion-rate')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST/PUT/PATCH requests",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


SYSTEM_PROMPT = """You are a system agent that answers questions by reading files and querying APIs.

Tools: list_files(path), read_file(path), query_api(method, path)

Guide:
- Wiki: list_files("wiki") then read_file()
- Code: list_files("backend/app") then read_file()
- API data: query_api("GET", "/endpoint/")
- Bugs: query_api() then read_file()
- Auth: query_api() then say 401 without auth
- Request journey: Read docker-compose.yml, caddy/Caddyfile, Dockerfile, main.py

FACTS:
- API uses Bearer token auth
- No auth = 401, With auth = 200
- query_api always uses auth

RULES:
1. End EVERY answer with: SOURCE: path/to/file
2. Give complete answers - no "let me check"
3. Use tools for data questions

Format:
[Your answer here]
SOURCE: path/to/file#section"""


def execute_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
    api_base_url: str = "",
    api_key: str = "",
) -> str:
    """Execute a tool and return its result.

    Args:
        name: Tool name.
        args: Tool arguments.
        project_root: Absolute path to project root.
        api_base_url: Base URL for query_api (optional).
        api_key: API key for query_api authentication (optional).

    Returns:
        Tool result as string.
    """
    if name == "read_file":
        path = args.get("path", "")
        return read_file(path, project_root)
    elif name == "list_files":
        path = args.get("path", "")
        return list_files(path, project_root)
    elif name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        return query_api(method, path, body, api_base_url, api_key)
    else:
        return f"Error: Unknown tool - {name}"


def extract_source_from_answer(answer: str) -> str:
    """Extract the source reference from the LLM's answer.

    Looks for patterns like:
    - SOURCE: wiki/file.md#anchor
    - Source: wiki/file.md#anchor
    - source: wiki/file.md#anchor
    - SOURCE: backend/app/file.py#anchor

    Args:
        answer: The LLM's answer text.

    Returns:
        Source reference string, or empty string if not found.
    """
    patterns = [
        r"SOURCE:\s*([\w\-/.]+\.[\w]+#\w[\w\-]*)",
        r"Source:\s*([\w\-/.]+\.[\w]+#\w[\w\-]*)",
        r"source:\s*([\w\-/.]+\.[\w]+#\w[\w\-]*)",
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
    api_base_url: str = "",
    api_key_lms: str = "",
    timeout: int = 60,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Call the LLM with tool support and agentic loop.

    Args:
        question: The user's question.
        api_key: API key for LLM authentication.
        api_base: Base URL of the LLM API.
        model: Model name to use.
        project_root: Absolute path to project root.
        api_base_url: Base URL for query_api (backend).
        api_key_lms: API key for query_api authentication (LMS_API_KEY).
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
                result = execute_tool(
                    tool_name, tool_args, project_root, api_base_url, api_key_lms
                )

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

    # Load LLM configuration
    api_key, api_base, model = get_llm_config()

    # Load backend API configuration
    lms_api_key, agent_api_base_url = get_api_config()

    project_root = Path(__file__).parent

    print(f"Using model: {model}", file=sys.stderr)
    print(f"Question: {question}", file=sys.stderr)
    print(f"Backend API URL: {agent_api_base_url}", file=sys.stderr)

    # Call the LLM with tools
    answer, source, tool_calls_list = call_llm_with_tools(
        question,
        api_key,
        api_base,
        model,
        project_root,
        agent_api_base_url,
        lms_api_key,
    )

    # Output the result as JSON
    result = {"answer": answer, "source": source, "tool_calls": tool_calls_list}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
