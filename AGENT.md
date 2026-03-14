# Agent Architecture

## Overview

This agent is a CLI tool that answers questions by calling an LLM through an OpenAI-compatible API. It has **tools** (`read_file`, `list_files`, `query_api`) to navigate the project wiki, examine source code, and query the running backend API. The **agentic loop** iteratively calls tools until it finds an answer.

## LLM Provider

**Provider:** OpenRouter (or Qwen Code API on VM)
**Model:** `openrouter/free` (rotates through available free models)

OpenRouter provides an OpenAI-compatible API endpoint with access to multiple models. The free tier offers 50 requests per day for free models. For production use, the agent can be configured to use the Qwen Code API running on the university VM.

## Configuration

The agent reads its configuration from environment variables and `.env` files:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` or env | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` or env | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` or env | - |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` or env | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Environment or `.env.docker.secret` | `http://localhost:42002` |

**Important:** The autochecker injects different values at evaluation time. The agent never hardcodes these values.

## Tools

The agent has three tools that the LLM can call:

### `read_file`

Reads a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path to the file from project root (e.g., `wiki/git-workflow.md` or `backend/app/main.py`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### `list_files`

Lists files and directories at a given path.

**Parameters:**

- `path` (string, required): Relative path to the directory from project root (e.g., `wiki` or `backend/app/routers`)

**Returns:** Newline-separated listing of entry names, or an error message if the directory doesn't exist.

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### `query_api`

Calls the backend API to fetch data or test endpoints.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, PATCH)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-01`)
- `body` (string, optional): JSON request body for POST/PUT/PATCH requests

**Returns:** JSON string with `status_code` and `body`, or an error message.

**Authentication:** Uses Bearer token authentication with `LMS_API_KEY` from environment:

```
Authorization: Bearer {LMS_API_KEY}
```

### Path Security Implementation

Both file system tools use `validate_path()` to prevent access to files outside the project directory:

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
2. **Loop (max 5 iterations):**
   - Call LLM with current messages and tool definitions
   - Parse response:
     - If `tool_calls` present: execute each tool, append results as `tool` role messages, continue loop
     - If no tool calls: extract final answer, break loop
3. **Track tool calls:** Store each tool call with its args and result for output
4. **Extract source:** Parse the LLM's answer to find the file reference

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

The system prompt instructs the LLM to choose the right tool for each question type:

1. **Wiki/documentation questions** (git workflow, SSH, merge conflicts): Use `list_files("wiki")` then `read_file()` on relevant files
2. **Source code questions** (framework, routers, ETL pipeline): Use `list_files("backend/app")` then `read_file()` on relevant files
3. **System/API questions** (item count, status codes, analytics data): Use `query_api()` to query the running backend
4. **Bug diagnosis**: First use `query_api()` to reproduce the error, then `read_file()` to examine the source code

The LLM is instructed to:

- Include source references for wiki/source questions: `SOURCE: wiki/filename.md#section-anchor`
- Section anchors are lowercase with hyphens (e.g., `## Resolving Merge Conflicts` → `#resolving-merge-conflicts`)
- For API questions, the source can be omitted or cite the endpoint

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
│ LLM API         │
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

2. **Environment Loading** (`load_env()`, `get_llm_config()`, `get_api_config()`)
   - Reads `.env.agent.secret` and `.env.docker.secret` from the project root
   - Also checks environment variables first (for autochecker injection)
   - Parses `KEY=value` format manually (no external dependencies)
   - Validates that all required variables are present

3. **Tool Functions** (`read_file`, `list_files`, `query_api`)
   - Implement file system operations and HTTP requests
   - Validate paths to prevent directory traversal attacks
   - `query_api` uses Bearer token authentication
   - Return results or error messages

4. **API Client** (`call_llm_with_tools()`)
   - Uses `httpx` for HTTP requests
   - POST to `{LLM_API_BASE}/chat/completions`
   - Includes tool definitions in request
   - Maintains conversation history across iterations
   - 60-second timeout per LLM call
   - Error handling for timeouts, HTTP errors, and invalid JSON

5. **Tool Execution** (`execute_tool()`)
   - Dispatches to appropriate tool function based on name
   - Passes arguments, project root, and API credentials
   - Returns result as string

6. **Source Extraction** (`extract_source_from_answer()`)
   - Uses regex to find `SOURCE: path/to/file.md#anchor` pattern
   - Returns source string or empty if not found

7. **Output Formatting**
   - Prints JSON to stdout: `{"answer": "...", "source": "...", "tool_calls": [...]}`
   - All debug/logging output goes to stderr using `print(..., file=sys.stderr)`

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Example output for wiki question
{
  "answer": "To protect a branch, go to Settings → Code and automation → Rules → New ruleset.",
  "source": "wiki/git-workflow.md#protecting-branches",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}

# Example output for API question
{
  "answer": "There are 42 items in the database.",
  "source": "",
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "{\"status_code\": 200, \"body\": \"[...]\"}"}
  ]
}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit 1, error to stderr |
| Missing LLM API key | Exit 1, error to stderr |
| Missing LMS API key | Exit 1, error to stderr |
| LLM API timeout (>60s) | Exit 1, error to stderr |
| LLM HTTP error (4xx/5xx) | Exit 1, error to stderr with response details |
| Invalid JSON from LLM | Exit 1, error to stderr |
| Path traversal attempt | Return error message in tool result |
| File not found | Return error message in tool result |
| API authentication failure | Return 401 status in tool result |
| Max tool calls (5) reached | Return best answer found |

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
│   └── task-3.md         # Implementation plan for Task 3
└── tests/
    └── test_agent.py     # Regression tests
```

## Dependencies

- `httpx` - HTTP client (already in project dependencies via `pyproject.toml`)
- Standard library only: `json`, `os`, `re`, `sys`, `pathlib`, `typing`

## Lessons Learned

### Tool Design

1. **Clear descriptions matter:** The LLM needs explicit guidance on when to use each tool. Vague descriptions lead to wrong tool selection.

2. **Authentication is critical:** The `query_api` tool initially used `X-API-Key` header, but the backend expects Bearer token authentication. Reading the backend's `auth.py` revealed the correct format.

3. **Environment variable priority:** Checking environment variables before `.env` files allows the autochecker to inject different credentials at evaluation time.

### Model Selection

1. **Free models have limits:** OpenRouter's free tier (50 requests/day) is useful for development but hits limits quickly during testing.

2. **Tool use support:** Not all models support function calling. The `openrouter/free` router automatically selects models that support tools.

3. **Speed vs. quality:** Free models are slower and may not follow complex instructions consistently. Reducing max iterations from 10 to 5 helps avoid timeouts.

### System Prompt Engineering

1. **Explicit rules work better:** Moving from implicit guidance to "IMPORTANT RULES" with numbered steps improved compliance.

2. **Source format matters:** The regex for extracting sources needs to match various capitalizations (`SOURCE:`, `Source:`, `source:`).

3. **Question-type routing:** Explicitly mapping question types to tools (wiki → list_files → read_file, API → query_api) improved tool selection accuracy.

### Benchmark Performance

The agent was tested against the 10-question local benchmark:

- Questions 0-2 (wiki lookup): Pass with proper source references
- Questions 3-5 (source code + API): Pass when model follows instructions
- Questions 6-7 (bug diagnosis): Challenging due to multi-step reasoning
- Questions 8-9 (LLM judge): Require detailed explanations

Key insight: The agent needs to balance thoroughness (enough tool calls to find answers) with speed (avoiding 60s timeouts).

### Task 3: query_api Implementation

**Architecture Decision:** The `query_api` tool was designed to be generic — it accepts any HTTP method and path, making it flexible for future API endpoints without code changes.

**Authentication Flow:**

1. Read `LMS_API_KEY` from `.env.docker.secret` (or environment variable)
2. Include `Authorization: Bearer {LMS_API_KEY}` header in all requests
3. Backend validates token using `get_current_user()` dependency
4. Return full response including status codes (e.g., 401 for missing auth)

**Key Implementation Details:**

- Base URL from `AGENT_API_BASE_URL` env var (default: `http://localhost:42002`)
- 30-second timeout per API call (separate from 60s LLM timeout)
- Handles all HTTP methods: GET, POST, PUT, DELETE, PATCH
- Returns JSON string with `status_code` and `body` for LLM to parse

**Tool Selection Strategy:**

The system prompt explicitly guides the LLM:

```
3. System/API questions (item count, status codes, analytics data): Use query_api()
4. Bug diagnosis: First use query_api() to reproduce the error, then read_file()
```

This two-step approach is essential for questions 6-7 where the agent must:

1. Call `query_api` to trigger the error (e.g., ZeroDivisionError, TypeError)
2. Read the source code to identify the root cause

**Rate Limiting Challenge:**

OpenRouter's free tier (50 requests/day) was exhausted during development. The error response includes helpful metadata:

```json
{
  "error": {
    "message": "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day",
    "code": 429,
    "metadata": {
      "headers": {
        "X-RateLimit-Limit": "50",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1773532800000"
      }
    }
  }
}
```

**Resolution:** Add credits to OpenRouter account or use the Qwen Code API on the university VM for unlimited development testing.

### Final Architecture Summary

The Task 3 agent has three complementary tools:

| Tool | Purpose | Question Types |
|------|---------|----------------|
| `list_files` | Discover file structure | "What files exist...", "List all routers" |
| `read_file` | Read file contents | Wiki questions, source code analysis |
| `query_api` | Query running backend | Data queries, status codes, bug reproduction |

The agentic loop orchestrates these tools:

1. LLM receives question + tool schemas
2. LLM decides which tool(s) to call
3. Agent executes tools, appends results to conversation
4. LLM processes results, either calls more tools or provides final answer
5. Agent extracts source reference, outputs JSON

This architecture enables multi-step reasoning: the agent can chain tools (e.g., `query_api` → `read_file`) to diagnose bugs by first reproducing the error, then examining the source code.

## Future Extensions

- Add `search_code` tool for grep-like code search
- Implement conversation history persistence across multiple questions
- Add retry logic for rate-limited API requests
- Support streaming responses for faster time-to-first-token
