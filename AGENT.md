# Agent Architecture

## Overview

This agent is a CLI tool that answers questions by calling an LLM through the OpenRouter API. It has **tools** (`read_file`, `list_files`) to navigate the project wiki and an **agentic loop** that iteratively calls tools until it finds an answer.

## LLM Provider

**Provider:** OpenRouter
**Model:** `meta-llama/llama-3.3-70b-instruct:free`

OpenRouter provides an OpenAI-compatible API endpoint with access to multiple models. The free tier offers 50 requests per day for free models.

## Configuration

The agent reads its configuration from `.env.agent.secret` in the project root:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | OpenRouter API key | `sk-or-v1-...` |
| `LLM_API_BASE` | API base URL | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Model name | `meta-llama/llama-3.3-70b-instruct:free` |

## Tools

The agent has two tools that the LLM can call to interact with the project files:

### `read_file`

Reads a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path to the file from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### `list_files`

Lists files and directories at a given path.

**Parameters:**

- `path` (string, required): Relative path to the directory from project root (e.g., `wiki`)

**Returns:** Newline-separated listing of entry names, or an error message if the directory doesn't exist.

**Security:** Validates that the resolved path is within the project directory. Paths with `../` traversal that escape the project root are rejected.

### Path Security Implementation

Both tools use `validate_path()` to prevent access to files outside the project directory:

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

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki files (starting with the `wiki` directory)
2. Use `read_file` to read specific files and find answers
3. Look for section headers in files (lines starting with `#`, `##`, etc.)
4. Include source references in the answer (e.g., `wiki/git-workflow.md#resolving-merge-conflicts`)
5. Respond with a final message (no tool calls) when the answer is found

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
├── .env.agent.secret     # API credentials (gitignored)
├── AGENT.md              # This documentation
├── plans/
│   ├── task-1.md         # Implementation plan for Task 1
│   └── task-2.md         # Implementation plan for Task 2
└── tests/
    └── test_agent.py     # Regression tests
```

## Dependencies

- `httpx` - HTTP client (already in project dependencies via `pyproject.toml`)
- Standard library only: `json`, `os`, `re`, `sys`, `pathlib`, `typing`

## Future Extensions (Task 3)

- **Task 3:** Add `query_api` tool to query the FastAPI backend
- Multi-turn conversations with persistent state
- More sophisticated source tracking and citation
