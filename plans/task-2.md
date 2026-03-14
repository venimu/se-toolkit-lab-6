# Task 2: The Documentation Agent - Implementation Plan

## Overview

This task extends the agent from Task 1 by adding **tools** (`read_file`, `list_files`) and an **agentic loop**. The agent will now be able to navigate the project wiki to find answers to questions.

## Tool Schemas

### `read_file`

**Purpose:** Read a file from the project repository.

**Schema:**
```json
{
  "name": "read_file",
  "description": "Read the contents of a file from the project repository.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path to the file from the project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path` to construct the absolute path
- Validate that the resolved path is within the project directory (no `../` traversal)
- Return file contents as string, or error message if file doesn't exist

### `list_files`

**Purpose:** List files and directories at a given path.

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories in a directory within the project repository.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path to the directory from the project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `pathlib.Path.iterdir()` to list entries
- Validate that the resolved path is within the project directory
- Return newline-separated listing of entry names

## Path Security

Both tools must prevent access to files outside the project directory:

1. **Resolve the path:** Combine project root with the relative path
2. **Resolve to absolute:** Use `.resolve()` to resolve any `..` or symlinks
3. **Check containment:** Verify the resolved path starts with the project root
4. **Return error:** If path escapes project root, return an error message instead of file contents

```python
def validate_path(relative_path: str, project_root: Path) -> Path | None:
    """Validate that a path is within the project directory."""
    full_path = (project_root / relative_path).resolve()
    if not str(full_path).startswith(str(project_root.resolve())):
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

### Implementation Steps

1. **Initialize messages list:** Start with system prompt + user question
2. **Loop (max 10 iterations):**
   - Call LLM with current messages and tool definitions
   - Parse response:
     - If `tool_calls` present: execute each tool, append results as `tool` role messages, continue loop
     - If no tool calls: extract final answer, break loop
3. **Track tool calls:** Store each tool call with its args and result for output
4. **Extract source:** Parse the LLM's answer to find the wiki file reference (e.g., `wiki/git-workflow.md#section`)

### Message Format

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

The system prompt should instruct the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific files and find answers
3. Include source references in the final answer (file path + section anchor)
4. Call tools iteratively until it finds the answer
5. Output the final answer with the source in a specific format

Example system prompt:
```
You are a documentation agent that answers questions by reading files from a project wiki.

Available tools:
- list_files(path): List files in a directory
- read_file(path): Read contents of a file

Process:
1. Use list_files to discover relevant wiki files
2. Use read_file to read files and find the answer
3. Include the source reference in your answer (e.g., wiki/git-workflow.md#resolving-merge-conflicts)

When you have the answer, respond with a final message that includes:
- The answer
- The source as: SOURCE: wiki/filename.md#section-anchor
```

## Output Format

```json
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
| Path traversal attempt | Return error message: "Access denied: path outside project" |
| File not found | Return error message: "File not found: {path}" |
| LLM returns invalid tool call | Skip the call, continue loop |
| Max tool calls (10) reached | Stop loop, return best answer found |

## Testing Strategy

Two regression tests:

1. **Test `read_file` usage:**
   - Question: `"How do you resolve a merge conflict?"`
   - Verify: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **Test `list_files` usage:**
   - Question: `"What files are in the wiki?"`
   - Verify: `list_files` in tool_calls

## Implementation Steps

1. Create this plan (`plans/task-2.md`)
2. Implement `read_file` and `list_files` tool functions with path validation
3. Define tool schemas for LLM function calling
4. Implement the agentic loop in `call_llm` or a new function
5. Update output JSON to include `source` and populated `tool_calls`
6. Update `AGENT.md` with tool documentation
7. Add 2 regression tests
8. Test manually with sample questions
9. Run tests and verify acceptance criteria
