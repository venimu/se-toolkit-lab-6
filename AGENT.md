# Agent Architecture

## Overview

This agent is a CLI tool that answers questions by calling an LLM through the OpenRouter API. It has **tools** (`read_file`, `list_files`, `query_api`) to navigate the project wiki, read source code, and query the backend API. The **agentic loop** iteratively calls tools until it finds an answer.

## LLM Provider

**Provider:** OpenRouter
**Model:** `meta-llama/llama-3.3-70b-instruct:free`

OpenRouter provides an OpenAI-compatible API endpoint with access to multiple models. The free tier offers 50 requests per day for free models.

## Configuration

The agent reads its configuration from environment variables:

| Variable | Description | Source |
|----------|-------------|--------|
| `LLM_API_KEY` | OpenRouter API key | `.env.agent.secret` |
| `LLM_API_BASE` | API base URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Backend API base URL | Environment (default: `http://localhost:42002`) |

> **Important:** Two distinct keys are used:
>
> - `LLM_API_KEY` authenticates with the LLM provider (OpenRouter)
> - `LMS_API_KEY` authenticates with the backend API (Learning Management Service)
>
> The autochecker injects its own values for these variables during evaluation, so the agent must read from environment variables, not hardcoded values.

## Tools

The agent has three tools that the LLM can call to interact with the project:

### `read_file`

Reads a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path to the file from project root (e.g., `wiki/git-workflow.md`, `backend/app/main.py`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Use cases:**

- Reading wiki documentation
- Reading source code to understand system behavior
- Finding configuration values in code

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### `list_files`

Lists files and directories at a given path.

**Parameters:**

- `path` (string, required): Relative path to the directory from project root (e.g., `wiki`, `backend/app/routers`)

**Returns:** Newline-separated listing of entry names, or an error message if the directory doesn't exist.

**Use cases:**

- Discovering what wiki files are available
- Finding router modules in the backend
- Exploring project structure

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### `query_api` (Task 3)

Queries the FastAPI backend API with authentication.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-01`)
- `body` (string, optional): JSON request body for POST/PUT requests

**Returns:** JSON string with `status_code` and `body`, or an error message.

**Example response:**

```json
{"status_code": 200, "body": [{"id": 1, "title": "Lab 01", ...}]}
```

**Use cases:**

- Data-dependent questions: "How many items are in the database?"
- Status code questions: "What status code does /items/ return?"
- Analytics queries: "What is the completion rate for lab-01?"
- Bug diagnosis: Query an endpoint to see the error, then read source code

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` with Bearer token authentication.

**Error handling:**

- Connection refused → Error with hint to start backend
- 401/403 → Authentication error
- Timeout → Error after 30 seconds
- Invalid JSON → Parse error message

### Path Security Implementation

Both `read_file` and `list_files` use `validate_path()` to prevent access to files outside the project directory:

```python
def validate_path(relative_path: str, project_root: Path) -> Path | None:
    """Validate that a path is within the project directory."""
    full_path = (project_root / relative_path).resolve()
    resolved_root = project_root.resolve()
    if not str(full_path).startswith(str(resolved_root)):
        return None  # Path escapes project directory
    return full_path
```

## Agentic Loop

The agentic loop enables multi-turn reasoning with the LLM:

```
Question ──▶ LLM ──▶ tool call? ──yes──▶ execute tool ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

### How It Works

1. **Initialize messages:** Start with system prompt + user question
2. **Loop (max 10 iterations):**
   - Call LLM with current messages and tool definitions
   - Parse response:
     - If `tool_calls` present: execute each tool, append results as `tool` role messages, continue loop
     - If no tool calls: extract final answer, break loop
3. **Track tool calls:** Store each tool call with its args and result for output
4. **Extract source:** Parse the LLM's answer to find the wiki file reference

### Message Format

The conversation is maintained as a list of messages:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool call:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": tool_result},
]
```

## System Prompt Strategy

The system prompt instructs the LLM to choose the right tool based on question type:

### Question Type Detection

1. **Documentation questions** (how-to, processes, guides):
   - Use `list_files` to discover wiki files
   - Use `read_file` to read specific files
   - Include source reference: `wiki/filename.md#section-anchor`

2. **System fact questions** (framework, ports, status codes):
   - Use `read_file` to read source code
   - Look for imports (e.g., `from fastapi import FastAPI`)
   - Include source reference: `backend/app/filename.py`

3. **Data-dependent questions** (counts, scores, analytics):
   - Use `query_api` to query the backend
   - Common endpoints: `/items/`, `/analytics/scores`, `/analytics/completion-rate`
   - No source reference needed (data comes from API)

4. **Bug diagnosis questions**:
   - First use `query_api` to see the error response
   - Then use `read_file` to read the source code
   - Explain both the error and its root cause

### Tool Selection Hints

The system prompt provides explicit guidance:

- "For questions about the running system's data, use `query_api`"
- "For questions about code structure or documentation, use `read_file`"
- "For bug diagnosis, first query the API, then read the source code"

Section anchors are lowercase with hyphens instead of spaces:

- `## Resolving Merge Conflicts` becomes `#resolving-merge-conflicts`

The LLM is instructed to include `SOURCE: wiki/filename.md#section-anchor` in its final answer, which the agent parses to populate the `source` field.

## How It Works

### Input/Output Flow

```
┌─────────────────┐
│ Command line    │
│ argument        │
│ (question)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ agent.py        │
│ - Parse args    │
│ - Load .env     │
│ - Agentic loop  │
│   - Call LLM    │
│   - Execute     │
│     tools       │
│ - Format output │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ OpenRouter API  │
│ POST /chat/     │
│ completions     │
│ with tools      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSON response   │
│ to stdout:      │
│ {"answer": "...",│
│  "source": "...",│
│  "tool_calls":[]│
└─────────────────┘
```

### Components

1. **Argument Parsing** (`sys.argv`)
   - Takes the first command-line argument as the question
   - Exits with usage message if no argument provided

2. **Environment Loading** (`load_env()`)
   - Reads `.env.agent.secret` from the project root
   - Parses `KEY=value` format manually (no external dependencies)
   - Validates that all required variables are present

3. **Tool Functions** (`read_file`, `list_files`)
   - Implement file system operations
   - Validate paths to prevent directory traversal attacks
   - Return results or error messages

4. **API Client** (`call_llm_with_tools()`)
   - Uses `httpx` for HTTP requests
   - POST to `{LLM_API_BASE}/chat/completions`
   - Includes tool definitions in request
   - Maintains conversation history across iterations
   - 60-second timeout
   - Error handling for timeouts, HTTP errors, and invalid JSON

5. **Tool Execution** (`execute_tool()`)
   - Dispatches to appropriate tool function based on name
   - Passes arguments and project root
   - Returns result as string

6. **Source Extraction** (`extract_source_from_answer()`)
   - Uses regex to find `SOURCE: wiki/filename.md#anchor` pattern
   - Returns source string or empty if not found

7. **Output Formatting**
   - Prints JSON to stdout: `{"answer": "...", "source": "...", "tool_calls": [...]}`
   - All debug/logging output goes to stderr using `print(..., file=sys.stderr)`

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Example output
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit 1, error to stderr |
| Missing API key | Exit 1, error to stderr |
| API timeout (>60s) | Exit 1, error to stderr |
| HTTP error (4xx/5xx) | Exit 1, error to stderr with response details |
| Invalid JSON response | Exit 1, error to stderr |
| Path traversal attempt | Return error message in tool result |
| File not found | Return error message in tool result |
| Max tool calls (10) reached | Return best answer found |

## Testing

Run the agent manually:

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Run the evaluation benchmark:

```bash
uv run run_eval.py --index 0  # Single question
uv run run_eval.py            # All questions
```

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI script
├── .env.agent.secret     # LLM API credentials (gitignored)
├── .env.docker.secret    # Backend API credentials (gitignored)
├── AGENT.md              # This documentation
├── plans/
│   ├── task-1.md         # Implementation plan for Task 1
│   ├── task-2.md         # Implementation plan for Task 2
│   └── task-3.md         # Implementation plan for Task 3 (System Agent)
└── tests/
    └── test_agent.py     # Regression tests
```

## Dependencies

- `httpx` - HTTP client (already in project dependencies via `pyproject.toml`)
- Standard library only: `json`, `os`, `re`, `sys`, `pathlib`, `typing`

## Lessons Learned (Task 3)

### Tool Schema Design

The initial `query_api` tool description was too vague. The LLM would sometimes:

- Call `read_file` for data questions like "How many items are in the database?"
- Forget to include the HTTP method in the tool call

**Fix:** Made the tool description more explicit with examples:
> "Use this for data-dependent questions like 'How many items are in the database?', 'What status code does /items/ return?'"

### Authentication Handling

Initially I hardcoded the `LMS_API_KEY` value. This would fail the autochecker which injects different credentials.

**Fix:** Read `LMS_API_KEY` from `.env.docker.secret` and check `AGENT_API_BASE_URL` from environment first (for the autochecker), then fall back to the `.env.docker.secret` file.

### Error Messages for Debugging

When the backend isn't running, the agent would crash with a connection error.

**Fix:** Catch `httpx.ConnectError` and return a helpful error message:
> "Cannot connect to API at <http://localhost:42002>. Make sure the backend is running."

This allows the LLM to explain the issue to the user rather than crashing.

### Bug Diagnosis Questions

Questions 6-7 require multi-step reasoning:

1. Query the API to see the error
2. Read the source code to find the bug
3. Explain the root cause

The LLM sometimes stops after step 1. The system prompt now explicitly says:
> "For bug diagnosis questions: First use query_api to see the error response. Then use read_file to read the source code and find the bug. Explain both the error and its root cause."

### Benchmark Performance

The 10 benchmark questions test different capabilities:

| # | Question Type | Tool Required | Key Challenge |
|---|---------------|---------------|---------------|
| 0-1 | Wiki lookup | `read_file` | Source reference formatting |
| 2-3 | System facts | `read_file` / `list_files` | Finding the right file |
| 4-5 | Data queries | `query_api` | Tool selection |
| 6-7 | Bug diagnosis | `query_api` + `read_file` | Multi-step reasoning |
| 8-9 | LLM judge | `read_file` | Comprehensive explanation |

The LLM-based judging for questions 8-9 is stricter than local keyword matching. The agent must provide detailed explanations tracing the request flow (Caddy → FastAPI → auth → router → ORM → PostgreSQL) and explaining idempotency via `external_id` checks.

### Final Eval Score

*To be updated after autochecker evaluation*

## Future Extensions

- Multi-turn conversations with persistent state
- More sophisticated source tracking and citation
- Support for streaming responses
- Caching of frequently accessed files
