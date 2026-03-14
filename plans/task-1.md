# Task 1: Call an LLM from Code - Implementation Plan

## LLM Provider and Model

**Provider:** OpenRouter  
**Model:** `meta-llama/llama-3.3-70b-instruct:free`

**Why OpenRouter:**
- Free tier available (50 requests/day for free models)
- No credit card required
- OpenAI-compatible API endpoint
- Good model quality with Llama 3.3 70B

**API Configuration:**
- Base URL: `https://openrouter.ai/api/v1`
- Model: `meta-llama/llama-3.3-70b-instruct:free`
- Authentication: Bearer token via `LLM_API_KEY` environment variable

## Agent Architecture

### Input/Output Flow

```
Command line argument (question)
    ↓
agent.py parses argument
    ↓
Read .env.agent.secret for API credentials
    ↓
Build HTTP request to OpenRouter API
    ↓
Send POST request to /v1/chat/completions
    ↓
Parse JSON response
    ↓
Extract answer from response
    ↓
Output JSON to stdout: {"answer": "...", "tool_calls": []}
```

### Components

1. **Environment Loading**
   - Read `.env.agent.secret` from project root
   - Extract `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
   - Use `python-dotenv` or manual parsing

2. **API Client**
   - Use `httpx` (already in project dependencies) for HTTP requests
   - POST to `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Body: `{"model": LLM_MODEL, "messages": [{"role": "user", "content": question}]}`

3. **Response Parsing**
   - Extract `choices[0].message.content` from API response
   - Handle errors (timeout, API errors, invalid responses)

4. **Output Formatting**
   - Print JSON to stdout: `{"answer": "<content>", "tool_calls": []}`
   - All debug/logging output to stderr

### Error Handling

- **Timeout:** 60 second limit (enforced by subprocess timeout in tests)
- **API errors:** Print error to stderr, exit with code 1
- **Missing credentials:** Print helpful message to stderr, exit with code 1
- **Invalid JSON response:** Print error to stderr, exit with code 1

### Testing Strategy

Create one regression test that:
1. Runs `agent.py "What is 2+2?"` as subprocess
2. Parses stdout as JSON
3. Verifies `answer` field exists and is non-empty
4. Verifies `tool_calls` field exists and is an array

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI script
├── .env.agent.secret     # API credentials (gitignored)
├── AGENT.md              # Documentation
├── plans/
│   └── task-1.md         # This plan
└── tests/
    └── test_agent.py     # Regression test
```

## Implementation Steps

1. Create `.env.agent.secret` with OpenRouter credentials
2. Create `agent.py` with:
   - Argument parsing (`sys.argv[1]`)
   - Environment loading
   - HTTP client using `httpx`
   - JSON output formatting
3. Create `AGENT.md` documentation
4. Create regression test
5. Test manually with sample questions
6. Run `run_eval.py --index 0` to verify
