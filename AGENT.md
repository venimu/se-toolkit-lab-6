# Agent Architecture

## Overview

This agent is a CLI tool that answers questions by calling an LLM through the OpenRouter API. It is the foundation for the more advanced agent with tools and agentic loop that will be built in Tasks 2-3.

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
│ - Call API      │
│ - Format output │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ OpenRouter API  │
│ POST /chat/     │
│ completions     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSON response   │
│ to stdout:      │
│ {"answer": "...",│
│  "tool_calls":[]}│
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

3. **API Client** (`call_llm()`)
   - Uses `httpx` for HTTP requests
   - POST to `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: `{"model": LLM_MODEL, "messages": [{"role": "user", "content": question}]}`
   - 60-second timeout
   - Error handling for timeouts, HTTP errors, and invalid JSON

4. **Response Parsing**
   - Extracts `choices[0].message.content` from the API response
   - Validates that the response contains a non-empty answer

5. **Output Formatting**
   - Prints JSON to stdout: `{"answer": "<content>", "tool_calls": []}`
   - All debug/logging output goes to stderr using `print(..., file=sys.stderr)`

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Example output
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit 1, error to stderr |
| Missing API key | Exit 1, error to stderr |
| API timeout (>60s) | Exit 1, error to stderr |
| HTTP error (4xx/5xx) | Exit 1, error to stderr with response details |
| Invalid JSON response | Exit 1, error to stderr |
| Empty API response | Exit 1, error to stderr |

## Testing

Run the agent manually:

```bash
uv run agent.py "What is 2+2?"
```

Run the regression test:

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
│   └── task-1.md         # Implementation plan
└── tests/
    └── test_agent.py     # Regression test
```

## Dependencies

- `httpx` - HTTP client (already in project dependencies via `pyproject.toml`)
- Standard library only: `json`, `os`, `sys`, `pathlib`

## Future Extensions (Tasks 2-3)

- **Task 2:** Add tool support (`read_file`, `list_files`, `query_api`)
- **Task 3:** Add agentic loop with tool calling and multi-turn reasoning
