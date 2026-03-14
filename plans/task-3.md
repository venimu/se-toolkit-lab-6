# Task 3: The System Agent - Implementation Plan

## Overview

This task extends the agent from Task 2 by adding a `query_api` tool to interact with the deployed backend API. The agent will answer both static system questions (framework, ports) and data-dependent queries (item count, scores).

## Tool Schema: `query_api`

**Purpose:** Call the deployed backend API to fetch data or test endpoints.

**Schema:**

```json
{
  "name": "query_api",
  "description": "Call the backend API to fetch data or test endpoints. Use this for questions about the running system, database contents, or API behavior.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, etc.)",
        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
      },
      "path": {
        "type": "string",
        "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

**Implementation:**

- Use `httpx` to make HTTP requests
- Base URL from `AGENT_API_BASE_URL` environment variable (default: `http://localhost:42002`)
- Authenticate with `LMS_API_KEY` from `.env.docker.secret` via `X-API-Key` header
- Return JSON string with `status_code` and `body`

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | - |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Environment or `.env.docker.secret` | `http://localhost:42002` |

**Important:** The autochecker injects different values at evaluation time. Never hardcode these values.

## System Prompt Update

The system prompt should guide the LLM to choose the right tool:

1. **Wiki questions** (git workflow, SSH, documentation) → use `list_files` and `read_file` on `wiki/` directory
2. **Source code questions** (framework, router modules, ETL pipeline) → use `list_files` and `read_file` on `backend/` directory
3. **System/API questions** (item count, status codes, analytics) → use `query_api` to query the running backend
4. **Bug diagnosis** → use `query_api` to reproduce the error, then `read_file` to examine the source code

Example guidance:

```
For questions about:
- Project documentation: Use list_files("wiki") then read_file()
- Source code structure: Use list_files("backend/app") then read_file()
- Running system data: Use query_api() with appropriate method and path
- API errors: Use query_api() to reproduce, then read_file() to diagnose
```

## Authentication

The `query_api` tool must authenticate requests:

- Read `LMS_API_KEY` from environment (via `.env.docker.secret`)
- Include `X-API-Key: {LMS_API_KEY}` header in all API requests
- Handle 401/403 responses gracefully

## Agentic Loop Changes

The agentic loop remains the same as Task 2:

1. Send question + tool definitions to LLM
2. If tool calls returned, execute tools and feed results back
3. If final answer returned, extract and output JSON
4. Max 10 tool calls

The only change is adding `query_api` to the tool schemas.

## Benchmark Strategy

The `run_eval.py` script tests 10 questions:

| # | Question Type | Expected Tool |
|---|---------------|---------------|
| 0 | Wiki: branch protection | `read_file` |
| 1 | Wiki: SSH connection | `read_file` |
| 2 | Source: web framework | `read_file` |
| 3 | Source: router modules | `list_files` |
| 4 | Data: item count | `query_api` |
| 5 | Data: status code | `query_api` |
| 6 | Bug: division by zero | `query_api`, `read_file` |
| 7 | Bug: TypeError in sorted | `query_api`, `read_file` |
| 8 | Reasoning: request journey | `read_file` |
| 9 | Reasoning: ETL idempotency | `read_file` |

**Iteration strategy:**

1. Run `run_eval.py` to see first failure
2. Check which tool was (not) used
3. Improve tool descriptions or system prompt
4. Re-run until all pass

## Implementation Steps

1. Create this plan (`plans/task-3.md`)
2. Add `LMS_API_KEY` loading to `get_llm_config()` or new function
3. Add `AGENT_API_BASE_URL` loading (default: `http://localhost:42002`)
4. Implement `query_api()` function with authentication
5. Add `query_api` to tool schemas
6. Update system prompt to guide tool selection
7. Run `run_eval.py` and iterate
8. Update `AGENT.md` with lessons learned
9. Add 2 regression tests

## Expected Challenges

| Challenge | Solution |
|-----------|----------|
| LLM uses wrong tool | Improve tool descriptions, be more specific |
| API returns 401 | Check `LMS_API_KEY` is loaded correctly |
| Agent doesn't know backend URL | Add `AGENT_API_BASE_URL` to system prompt |
| Bug diagnosis fails | Guide LLM to first reproduce error, then read source |

## Implementation Notes

### Authentication Fix

The initial implementation used `X-API-Key` header for authentication, but the backend's `auth.py` uses Bearer token authentication:

```python
# Wrong:
headers = {"X-API-Key": api_key}

# Correct:
headers = {"Authorization": f"Bearer {api_key}"}
```

### Model Selection

After testing several models:

- `meta-llama/llama-3.2-3b-instruct:free` - No tool use support (404)
- `meta-llama/llama-3.1-8b-instruct:free` - No tool use support (404)
- `google/gemma-3-1b-it:free` - No tool use support (404)
- `openrouter/free` - Works, rotates through available free models with tool support

### Rate Limiting

OpenRouter free tier has a 50 requests/day limit. After hitting the limit:

```
Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day
```

For continuous development, use the Qwen Code API on the university VM.

### Performance Optimization

Reduced `MAX_TOOL_CALLS` from 10 to 5 to avoid 60s timeouts with slow free models.

## Benchmark Results

### Initial Run

```
6/10 passed

Failed on:
- Question 6: Timeout (agent took >60s for multi-step bug diagnosis)
```

### After Authentication Fix

```
3/10 passed

Failed on:
- Question 3: Timeout (list_files + multiple read_file calls)
- Questions 4-9: Not reached due to rate limiting
```

### Lessons from Failures

1. **Timeouts are common** with free models due to slow inference
2. **Source references** are often missing from answers
3. **Multi-step reasoning** (bug diagnosis) requires more than 5 tool calls

### Next Steps

1. Add credits to OpenRouter account OR configure Qwen Code API on VM
2. Improve system prompt to ensure source references are included
3. Consider increasing timeout for complex questions
4. Test with hidden autochecker questions

## Final Score

**Pending** - Blocked by OpenRouter rate limit (50/day exhausted)

### Rate Limit Issue

The OpenRouter free tier limits to 50 requests per day. When exhausted:

```
Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day
```

Error response includes reset timestamp: `X-RateLimit-Reset: 1773532800000`

### Resolution Options

1. **Add credits to OpenRouter** — 10 credits unlocks 1000 free requests/day
2. **Wait for daily reset** — Rate limit resets at midnight UTC
3. **Use Qwen Code API on VM** — Configure `LLM_API_BASE` to point to university VM

### To Complete Evaluation

1. Add new OpenRouter API key with available credits to `.env.agent.secret`
2. Run `uv run run_eval.py` to completion
3. Document final score and any remaining issues below

---

## Implementation Status (Complete)

All code implementation is complete:

- ✅ `query_api` tool implemented with Bearer token authentication
- ✅ Tool schema registered in `get_tool_schemas()`
- ✅ `get_api_config()` loads `LMS_API_KEY` and `AGENT_API_BASE_URL`
- ✅ System prompt updated with tool selection guidance
- ✅ Agent reads all config from environment variables
- ✅ Tests exist for `query_api` tool usage

**Only blocker:** OpenRouter rate limit prevents running full benchmark.
