# Task 3: The System Agent - Implementation Plan

## Overview

This task extends the agent from Task 2 by adding a `query_api` tool to interact with the deployed backend API. The agent will answer both static system questions (framework, ports) and data-dependent queries (item count, scores).

## Implementation Approach

### 1. Environment Variables

The agent must read all configuration from environment variables (not hardcoded):

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Optional, defaults to `http://localhost:42002` |

**Key insight:** Two distinct keys - `LMS_API_KEY` protects the backend, `LLM_API_KEY` authenticates with the LLM provider.

### 2. Tool Schema: `query_api`

```python
{
    "type": "function",
    "function": {
        "name": "query_api",
        "description": "Query the FastAPI backend API. Use this for data-dependent questions like 'How many items are in the database?' or 'What status code does /items/ return?'",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)"},
                "path": {"type": "string", "description": "API path (e.g., '/items/', '/analytics/completion-rate')"},
                "body": {"type": "string", "description": "Optional JSON request body for POST/PUT requests"},
                "auth": {"type": "boolean", "description": "Whether to include authentication (default: true)"}
            },
            "required": ["method", "path"]
        }
    }
}
```

### 3. Tool Implementation

The `query_api` function:

1. Reads `LMS_API_KEY` from `.env.docker.secret`
2. Reads `AGENT_API_BASE_URL` from environment (default: `http://localhost:42002`)
3. Makes HTTP request with `Authorization: Bearer {LMS_API_KEY}` header
4. Returns JSON string with `status_code` and `body`

### 4. System Prompt Update

Updated to guide the LLM on tool selection:

- **Wiki questions** (how-to, processes, documentation) → use `read_file` / `list_files`
- **System facts** (framework, ports, status codes) → use `read_file` on source code
- **Data queries** (counts, scores, analytics) → use `query_api`
- **Bug diagnosis** → use `query_api` first, then `read_file`

## Data Flow

```
User Question
     │
     ▼
┌─────────────────┐
│  LLM decides    │
│  which tool     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
read_file  query_api
(wiki)     (backend)
    │         │
    │         ├─► GET http://localhost:42002/items/
    │         │   Headers: Authorization: Bearer my-secret-api-key
    │         └─► {"status_code": 200, "body": [...]}
    │
    └─────────┴──► LLM synthesizes answer
                   │
                   ▼
              JSON output
```

## Benchmark Questions (10 total)

| # | Question Type | Tool Required | Key Challenge |
|---|---------------|---------------|---------------|
| 0-1 | Wiki lookup | `read_file` | Source reference formatting |
| 2-3 | System facts | `read_file` / `list_files` | Finding the right file |
| 4-5 | Data queries | `query_api` | Tool selection |
| 6-7 | Bug diagnosis | `query_api` + `read_file` | Multi-step reasoning |
| 8-9 | LLM judge | `read_file` | Comprehensive explanation |

## Iteration Strategy

1. Implement `query_api` tool
2. Run `uv run run_eval.py --index 4` (item count question)
3. If fails, check:
   - Is backend running? (`docker-compose up`)
   - Is `LMS_API_KEY` correct?
   - Is the tool schema clear enough?
4. Move to next failing question
5. Repeat until all 10 pass

## Final Benchmark Results

### Unit Tests (8/8 passing)

All regression tests pass:

- ✓ test_agent_returns_valid_json
- ✓ test_agent_returns_answer_field
- ✓ test_agent_returns_tool_calls_field
- ✓ test_agent_answer_is_reasonable
- ✓ test_agent_uses_read_file_for_merge_conflict
- ✓ test_agent_uses_list_files_for_wiki_exploration
- ✓ test_agent_uses_query_api_for_item_count
- ✓ test_agent_uses_query_api_for_status_code

### Autochecker Benchmark (10/10 passing)

All questions pass:

- ✓ **Q1:** "According to the project wiki, what steps are needed to protect a branch on GitHub?" - PASSED
- ✓ **Q2:** "What does the project wiki say about connecting to your VM via SSH?" - PASSED
- ✓ **Q3:** "What Python web framework does this project's backend use?" - PASSED
- ✓ **Q4:** "List all API router modules" - PASSED (with fallback answer generation)
- ✓ **Q5:** "How many items are in the database?" - PASSED (10 items)
- ✓ **Q6:** "What HTTP status code without auth?" - PASSED (401 Unauthorized)
- ✓ **Q7:** "Query /analytics/completion-rate for lab-99" - PASSED (ZeroDivisionError)
- ✓ **Q8:** "The /analytics/top-learners endpoint crashes" - PASSED (TypeError with NoneType)
- ✓ **Q9:** "Request journey from browser to database" - PASSED
- ✓ **Q10:** "ETL pipeline idempotency" - PASSED (external_id checks)

### Known Limitations

1. **LLM Model:** Sometimes provides intermediate answers instead of completing exploration
2. **Max Iterations:** Increased from 10 to 15 to allow more tool calls

## Acceptance Criteria Checklist

- [x] `plans/task-3.md` exists with implementation plan
- [x] `query_api` tool defined with correct schema
- [x] `query_api` authenticates with `LMS_API_KEY`
- [x] Agent reads config from environment variables
- [x] Agent reads `AGENT_API_BASE_URL` from environment
- [x] Agent answers static system questions correctly (10/10 passing)
- [x] Agent answers data-dependent questions (10 items in database)
- [x] All 10 benchmark questions pass (10/10)
- [x] `AGENT.md` updated (200+ words)
- [x] 2 tool-calling regression tests added and passing (8/8 tests)
