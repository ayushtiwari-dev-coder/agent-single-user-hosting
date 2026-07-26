# Local Agent Template

A local-first, provider-agnostic AI agent framework. It runs a full **ReAct (Reason + Act) loop** against pluggable LLM providers (Gemini, Groq), persists everything to a local SQLite database, gives the model a self-clustering **long-term memory**, and exposes itself through three interchangeable front ends: a terminal CLI, a Telegram bot, and a FastAPI + WebSocket backend for a React web UI.

This document explains how the internals actually work, how to extend the agent with new tools, and how to clone and run the project yourself.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [How the Agent Works — The ReAct Loop](#how-the-agent-works--the-react-loop)
4. [The Tool System](#the-tool-system)
5. [Memory System](#memory-system)
6. [Conversation Context & Summarization](#conversation-context--summarization)
7. [Approval / Permission System](#approval--permission-system)
8. [Loop Protection](#loop-protection)
9. [LLM Provider Layer](#llm-provider-layer)
10. [Interfaces (CLI, Telegram, Web)](#interfaces-cli-telegram-web)
11. [Configuration](#configuration)
12. [Database](#database)
13. [How to Add a New Tool](#how-to-add-a-new-tool)
14. [Cloning & Running the Project](#cloning--running-the-project)
15. [Running Tests](#running-tests)
16. [License](#license)

---

## Architecture Overview

At its core, this project is a single **`AgentEngine`** class (`engine/agent_engine.py`) that runs a loop:

1. Send the conversation history + a list of available tools to an LLM.
2. Stream the response back to whichever interface is connected (CLI / Telegram / WebSocket).
3. If the model asked to call a tool, execute it (after checking permissions and loop safety), append the result to the conversation, and go back to step 1.
4. If the model returned plain text instead of a tool call, save it and return — the turn is done.

Everything else in the codebase supports this loop: the database persists messages so the loop can resume across restarts, the memory manager gives the model long-term recall, the tool registry auto-discovers new capabilities, and the three interface modules just plug callbacks into `AgentEngine.send_message()`.

---

## Project Structure

```
Local-Agent-Template/
├── main.py                      # Entry point — routes to CLI / Telegram / Web
├── migrate_db.py                 # One-off DB migration helper
├── requirements.txt
│
├── engine/
│   ├── agent_engine.py            # The ReAct loop itself
│   ├── handle_permissions.py      # Approval gating + unified tool execution
│   ├── stream_processor.py        # Buffers streamed text/tool-call deltas
│   └── thinking_configure.py      # Maps "thinking_level" setting to provider params
│
├── llm/
│   ├── base_provider.py           # Abstract provider interface
│   ├── provider_factory.py        # Instantiates the right provider by name
│   ├── schemas.py                 # LLMResponse / StreamChunk / ToolCall dataclasses
│   ├── context_formatter.py       # Converts DB messages -> provider-specific format
│   ├── generate_with_retry.py     # Retry/backoff wrapper for API calls
│   ├── loop_protector.py          # Detects repeated/failing tool calls
│   └── providers/
│       ├── gemini.py
│       └── groq.py
│
├── tools/
│   ├── core.py                    # @agent_tool decorator
│   ├── registry.py                # Auto-discovers every tool at startup
│   └── memory_tools.py            # Example tools (remember / search memory)
│
├── managers/
│   ├── conversation_manager.py     # Save messages, compile context, trim history
│   ├── memory_manager.py           # Semantic (embedding-based) long-term memory
│   ├── summary_manager.py          # Background thread that compresses old history
│   ├── approval_manager.py         # Thread-blocking wait/resolve for tool approvals
│   └── user_manager.py
│
├── database/
│   ├── connection.py               # SQLite connection, lives in ~/.local_workflow_agent/
│   ├── table_generator.py          # CREATE TABLE statements
│   └── helper.py
│
├── queries/                        # Raw SQL per-table (conversations, messages, memory, etc.)
│
├── interfaces/
│   ├── telegram_bot.py             # Long-polling Telegram bot
│   ├── telegram_menu.py
│   └── websocket.py                # FastAPI router — powers the React front end
│
├── cli/
│   ├── menu_flows.py                # Interactive terminal menu
│   ├── chat_loop.py                  # The actual terminal chat REPL
│   ├── callbacks.py
│
├── config_configure/
│   └── out_chat_config.py           # CLI screens for editing config.json
│
├── utils/
│   ├── config_manager.py            # Public getters/setters re-exported for the app
│   ├── path_helper.py                # Resolves project root, loads .env
│   └── config/
│       ├── core.py                   # DEFAULT_CONFIG + load/save
│       ├── settings.py               # Typed getters/setters (max_turns, thresholds, etc.)
│       └── models.py
│
└── tests/                           # ~35 test files covering nearly every module above(140 tests)
```

---

## How the Agent Works — The ReAct Loop

The loop lives in `AgentEngine.send_message()`. Walking through it:

```python
db_messages = compile_llm_context(conversation_id)   # 1. load trimmed history
tool_call_history = []
turn_count = 0

while True:
    if turn_count >= MAX_TURNS:                        # hard safety ceiling
        return "Error: Maximum tool execution limit reached."
    turn_count += 1

    stream = self.provider.generate_content(
        messages=db_messages,
        tools=get_all_tools(),                          # every registered tool, every turn
    )
    full_text, parsed_tool_calls, prompt_tokens, comp_tokens = process_llm_stream(stream, send_message_callback)

    log_api_usage(...)                                  # token accounting -> SQLite

    if parsed_tool_calls:
        db_messages.append({"role": "assistant", "content": full_text, "tool_calls": parsed_tool_calls})
        for tool_call in parsed_tool_calls:
            # loop-safety check, then permission check, then execution
            tool_output, status = determine_and_execute_tool(...)
            db_messages.append({"role": "tool", "tool_name": tool_call.name, "content": formatted_output})
        continue                                        # go generate again with the tool result in context
    else:
        save_assistant_message(conversation_id, full_text)
        self._trigger_summary_safely(conversation_id)     # fire-and-forget background summary
        return full_text
```

Key points:

- **Every tool is offered on every turn.** The registry (`get_all_tools()`) is queried fresh each iteration, so tools added while the process is running are picked up automatically on the next turn.
- **The model decides when to stop.** The loop only exits when the model responds with plain text instead of a tool call, or when `MAX_TURNS` (config: `max_turns`, default 15) is hit.
- **Tool results are fed back as `role: "tool"` messages** with an explicit `SUCCESS`/`FAILED` prefix, which is the main signal that steers the model's next decision.
- **Streaming and execution are decoupled.** `stream_processor.py` buffers partial tool-call JSON deltas (since providers stream them token-by-token) and only hands `agent_engine.py` a clean, parsed `ToolCall` once a chunk is fully assembled.

---

## The Tool System

Tools are plain Python functions tagged with a decorator — there is no manual registration list to maintain.

**`tools/core.py`** defines the tag:

```python
def agent_tool(requires_approval: bool = False) -> Callable:
    def decorator(func: Callable) -> Callable:
        func.__is_agent_tool__ = True
        func.requires_approval = requires_approval
        return func
    return decorator
```

**`tools/registry.py`** scans the `tools/` package at import time using `pkgutil.iter_modules`, imports every module inside it, and inspects each function for the `__is_agent_tool__` flag:

```python
FLAT_REGISTRY = {}       # {"remember_user_preference": <func>, ...}
GROUPED_REGISTRY = {}    # {"memory_tools": {"description": ..., "tools": {...}}}

def get_all_tools() -> list:
    return list(FLAT_REGISTRY.values())

def execute_tool(tool_name, arguments, conversation_id=None) -> str:
    tool_func = FLAT_REGISTRY.get(tool_name)
    sig = inspect.signature(tool_func)
    if "conversation_id" in sig.parameters and conversation_id is not None:
        arguments["conversation_id"] = conversation_id     # auto-injected, not sent by the LLM
    ...
    return tool_func(**arguments)
```

The underlying LLM SDKs (Gemini/Groq) introspect each Python function's **name, docstring, and type-hinted parameters** to build the tool schema automatically — you never hand-write a JSON schema.

`engine/handle_permissions.py` sits between the registry and the engine: it checks `tool_func.requires_approval`, blocks on `approval_callback` if needed, executes via `execute_tool`, detects success/error from the return value's shape (`Error:`-prefixed string, or a `{"status": ...}` dict), and logs every run to the `tool_logs` table.

---

## Memory System

Long-term memory is **semantic**, not keyword-based — it lives in `managers/memory_manager.py` and is exposed to the model as two tools in `tools/memory_tools.py`: `remember_user_preference` and `search_user_history`.

**Saving a memory:**

1. Embed both the memory content and its suggested category using the active embedding provider (`provider.embed_text([...])`).
2. Compare the category's embedding against every existing category block's embedding using cosine similarity.
3. If the best match scores above `memory_similarity_threshold` (default `0.80`), the memory is filed into that existing block. Otherwise, a brand-new category block is created — this is how the store self-organizes without any fixed taxonomy.
4. The raw memory text + its own embedding vector are saved under the resolved category.

**Retrieving a memory** (`search_user_history`) mirrors this: embed the query category to find the right block, embed the search text itself, then rank every memory inside that block by cosine similarity to the query and return the top `limit` matches.

This means the model doesn't need to know exactly how something was phrased before — "the user's coffee order" and "beverage preferences" can resolve to the same cluster if their embeddings are close enough.

---

## Conversation Context & Summarization

Two mechanisms keep the context window from growing unbounded, both in `managers/conversation_manager.py` and `managers/summary_manager.py`:

- **`compile_llm_context()`** builds the message list sent to the LLM each turn. If a running summary exists for the conversation, it's injected as a `system` message at index 0, and only messages created *after* the last-summarized message are pulled from SQLite. It then estimates tokens with `tiktoken` (falling back to `len(text)//4` if unavailable) and, if over `max_context_tokens` (default 100,000), trims the oldest messages one at a time — carefully popping any orphaned `tool` messages that followed a removed `assistant` tool-call message, and protecting the very first user message from being dropped.
- **Background summarization** (`summary_manager.py`) triggers after every completed turn. It fires a **daemon thread** (non-blocking — the user gets their answer immediately) that checks whether unsummarized messages have crossed `summary_trigger_count` (default 30), and if so, asks the LLM to fold the new messages into the existing summary, capped at ~300 words, and persists it.

---

## Approval / Permission System

Some tools are dangerous enough to require a human in the loop. Any tool decorated with `@agent_tool(requires_approval=True)` triggers this flow in `engine/handle_permissions.py`:

1. If `autonomous=False` on the `AgentEngine`, the engine calls `approval_callback(tool_name, tool_args, conversation_id)` — a function supplied by whichever interface is active (CLI prompt, Telegram inline button, or React WebSocket message).
2. Interfaces that are asynchronous (Telegram, WebSocket) use `managers/approval_manager.py`, which parks the executing thread on a `threading.Event` via `wait_for_decision()` until the UI calls `resolve_decision(conversation_id, approved)` from a separate callback/handler — effectively turning an async user click into a synchronous return value for the engine.
3. If `autonomous=True`, approval is skipped entirely — useful for background/scripted runs.

---

## Loop Protection

`llm/loop_protector.py` guards against the model getting stuck. Before each tool executes, it scans backward through the **current turn's** call history (stopping at the first non-matching call, so it's strictly consecutive/back-to-back) and halts the whole loop with an error message if:

- The exact same tool + arguments has **failed** `max_failed_attempts` times in a row (default 3), or
- The exact same tool + arguments has **succeeded** `max_success_attempts` times in a row (default 2) — this catches the model wastefully repeating an already-successful action.

---

## LLM Provider Layer

Providers implement `llm/base_provider.py`'s `BaseLLMProvider` ABC:

```python
class BaseLLMProvider(ABC):
    @abstractmethod
    def format_messages(self, db_messages): ...      # DB format -> SDK-specific format
    @abstractmethod
    def generate_content(self, messages, tools, system_instruction="", **kwargs): ...  # returns a stream
    @abstractmethod
    def embed_text(self, texts): ...                  # returns list[list[float]]
```

`llm/provider_factory.py`'s `LLMFactory.get_provider(name, api_key, model_name)` is the single place that maps a provider string (`"gemini"` / `"groq"`) to a concrete class. Since the engine, memory manager, and summary manager all go through this factory rather than importing an SDK directly, adding a third provider means writing one new `providers/your_provider.py` file and adding one `elif` branch to the factory — nothing else in the codebase needs to change.

---

## Interfaces (CLI, Telegram, Web)

All three interfaces are thin wrappers that supply callbacks to the same `AgentEngine.send_message()`:

| Interface | File | Notes |
|---|---|---|
| **CLI** | `cli/menu_flows.py`, `cli/chat_loop.py` | Terminal REPL using `rich` for formatting and `prompt_toolkit` for input; approval prompts are simple y/n. |
| **Telegram** | `interfaces/telegram_bot.py` | Long-polling bot via `pyTelegramBotAPI`; approvals become inline keyboard buttons that call `resolve_decision()`. |
| **Web** | `interfaces/websocket.py` + `main.py`'s `start_web()` | FastAPI app with a `WebSocket` router. Streams text as `message_chunk` events and parses engine status strings (`"Executing tool..."`, etc.) into structured `tool_start`/`tool_end`/`thought_start` events for a React front end running on port 5173 to consume. CORS is wide open (`allow_origins=["*"]`) since this is meant for local development. |

`main.py` is the single entry point — it creates the SQLite tables on every boot (idempotent), then either reads `--mode {cli,telegram,web}` from argv or shows an interactive numbered menu.

---

## Configuration

Two separate mechanisms hold configuration:

- **`.env`** (project root, loaded by `utils/path_helper.py::load_env_file()`) — holds secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`. Parsed with `python-dotenv` if present, otherwise a small built-in fallback parser (handles quotes and inline `#` comments).
- **`config.json`** (stored at `~/.local_workflow_agent/config.json`, managed by `utils/config/core.py`) — holds everything else: active provider/model per task, `temperature`, `max_turns`, `max_context_tokens`, `summary_trigger_count`, `memory_similarity_threshold`, `loop_guard` thresholds, `system_instruction`, sandbox/container settings, and Telegram bot settings. Missing keys always fall back to `DEFAULT_CONFIG` via a deep-merge in `load_config()`, so upgrading the code never breaks an existing config file. Typed getter/setter pairs for every setting live in `utils/config/settings.py` (re-exported through `utils/config_manager.py`), and `config_configure/out_chat_config.py` provides the interactive CLI screens for editing them.

---

## Database

SQLite, stored at `~/.local_workflow_agent/assistant.db` (`database/connection.py`), opened with `PRAGMA journal_mode = WAL` for concurrent read/write safety and `row_factory = sqlite3.Row` for dict-like access. Tables are created idempotently by `database/table_generator.py` on every boot. Core tables (inferred from the `queries/` modules):

- `conversations`, `messages` — chat history
- `summaries` — one running summary per conversation
- `tool_logs` — every tool execution, arguments, output, status
- `model_usage` — prompt/completion token counts per call, per model
- `memories`, `memory_categories` — the semantic memory store and its embedding vectors
- `users` — for multi-user setups (Telegram `allowed_user_ids`, etc.)

Each table has a dedicated file under `queries/` containing its raw SQL — managers never write inline SQL themselves, they call into `queries/*`.

---

## How to Add a New Tool

Because of the auto-discovery registry, adding a capability is entirely additive — you never touch `agent_engine.py` or the registry itself.

1. **Create a new file under `tools/`**, e.g. `tools/web_tools.py`. The filename becomes the tool's category in `GROUPED_REGISTRY`, and the module's docstring becomes its description.

   ```python
   # tools/web_tools.py
   """Tools for fetching and summarizing web content."""

   import requests
   from tools.core import agent_tool

   @agent_tool()  # safe, no approval needed
   def fetch_url(url: str) -> str:
       """Fetches the raw text content of a public URL."""
       try:
           resp = requests.get(url, timeout=10)
           resp.raise_for_status()
           return resp.text[:5000]
       except Exception as e:
           return f"Error: Failed to fetch URL: {e}"
   ```

2. **Type-hint every parameter and write a clear docstring** — both are read directly by the provider SDK to build the function-calling schema the model sees. There is no separate JSON schema file to maintain.

3. **Mark destructive/risky tools with `@agent_tool(requires_approval=True)`.** This forces every interface to pause and call its `approval_callback` before the tool runs.

   ```python
   @agent_tool(requires_approval=True)
   def delete_file(path: str) -> str:
       """Permanently deletes a file from the workspace. Requires user approval."""
       ...
   ```

4. **Follow the error contract.** Return either a plain string starting with `"Error: ..."` on failure, or `{"status": "success"/"error", "output": ...}` — `handle_permissions.py` uses this shape to decide what the model sees and whether the run is logged as a failure.

5. **Need conversation context inside the tool?** Just add a `conversation_id: int` parameter — the registry injects it automatically at call time; the LLM never has to supply it.

6. **That's it.** On the next process start (or next loop turn, since `get_all_tools()` is re-read live), the model can see and call the new tool. No wiring into `main.py`, the engine, or any interface is required.

---

## Cloning & Running the Project

This template is hosted at:

**https://github.com/ayushtiwari-dev-coder/Local-Agent-Template**

```bash
# 1. Clone the repository
git clone https://github.com/ayushtiwari-dev-coder/Local-Agent-Template.git
cd Local-Agent-Template

# 2. (Recommended) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create a .env file in the project root with your API keys
echo "GEMINI_API_KEY=your_key_here" >> .env
echo "GROQ_API_KEY=your_key_here" >> .env

# 5. Run it
py