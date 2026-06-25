# Mini Agent Harness

A tiny Python agent harness built step by step.

This project is for learning how an agent works under the hood:

```text
user prompt
-> model call
-> optional tool request
-> tool execution
-> model final answer
```

## Current Features

- Reads model settings from environment variables.
- Calls an OpenAI-compatible chat completion API.
- Supports OpenAI-compatible native `tools` / `tool_calls`.
- Includes two tools:
  - `read_file`: read UTF-8 text files inside the project workspace.
  - `web_search`: search the web and return compact snippets.
- Can print agent loop logs with `--verbose` so you can see when the model asks for a tool.
- Asks for terminal approval before running a requested tool by default.
- Includes a small `unittest` test suite for the core loop.

## Setup

Create a local `.env` file based on `.env.example`:

```bash
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4.1-mini
TEMPERATURE=0.7
MAX_TOKENS=4096
```

The CLI automatically reads `.env` from the current project directory. You can also load it into your terminal manually if you prefer:

```bash
set -a
source .env
set +a
```

## Run

Install the local CLI commands from the project root:

```bash
/Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m pip install -e .
```

Start the interactive terminal interface:

```bash
minicode
```

Inside the interface, type a prompt and press Enter. Type `/exit` or `/quit` to stop.

Each interactive session writes a local JSON record under:

```text
src/conversations/
```

Session files are named by date and sequence number, for example:

```text
src/conversations/2026-06-22-001.json
```

Session records include prompts, final answers, errors, model name, and base URL. They do not include the API key and are ignored by Git.

During one `minicode` session, successful previous turns are also sent back to the model as short-term session memory. This memory is session-scoped, not long-term memory.

From the project root:

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m mini_agent_harness.main "你好，请用一句话介绍你自己"
```

Try the file-reading tool:

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m mini_agent_harness.main "请读取 pyproject.toml，并总结这个项目是什么"
```

When the agent wants to run a tool, approve it with `y`:

```text
Agent wants to run a tool:
  tool: read_file
  arguments: {'path': 'pyproject.toml'}
Allow? [y/N]
```

Print agent loop logs while running:

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m mini_agent_harness.main --verbose "请读取 pyproject.toml，并总结这个项目是什么"
```

Skip terminal approval when you already trust the requested tools:

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m mini_agent_harness.main --no-approval "请读取 pyproject.toml，并总结这个项目是什么"
```

Limit the number of model/tool loop steps:

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m mini_agent_harness.main --max-steps 2 "请读取 pyproject.toml，并总结这个项目是什么"
```

## Test

```bash
PYTHONPATH=src /Users/lyk/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3 -m unittest discover -s tests
```

## CI

GitHub Actions runs the same unit test suite on pushes to `main` and on pull requests:

```bash
python -m unittest discover -s tests
```

## How It Works

- `main.py` is the command-line entrypoint.
- `config.py` loads API settings from environment variables.
- `model_client.py` talks to the model API.
- `tool.py` defines the tool interface.
- `tools.py` implements concrete tools.
- `agent.py` controls the agent loop, including the `max_steps` safety limit.

The current tool-calling protocol uses OpenAI-compatible native `tools` / `tool_calls`. The agent sends tool schemas to the model API, executes requested tool calls locally, sends the tool result back with `role: "tool"`, and then asks the model for the final answer.

The old JSON text protocol is kept only as a compatibility fallback for models that do not return native `tool_calls`.
