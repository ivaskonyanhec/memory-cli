# memory-cli

A global CLI for the [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) knowledge base.

Turns verbose `uv run python scripts/compile.py` invocations into simple shell commands:

```bash
memory sync          # compile new conversations and clipped articles
memory add FILE.md   # import a markdown file into resources/ and compile it
memory lint          # run 7 knowledge base health checks
memory lint-fix      # apply safe structural lint fixes
memory query "..."   # ask the knowledge base a question
memory status        # show article counts, last compile time
memory log           # tail the build log
memory config        # view and edit settings
memory config keys   # list configurable keys
memory config get K  # read one config value
memory config set K V # update one config value
memory config --edit # interactive settings editor
```

## What a memory means here

In this project, a memory is a durable Markdown note distilled from raw inputs such as Claude Code session logs, clipped references, or imported documents.

It is not the full transcript. It is the compact, reusable knowledge extracted from those sources and stored in your vault as linked notes that can be queried, updated, and recompiled over time.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Claude Code](https://claude.ai/code) — installed and authenticated (`claude` must be on PATH)
- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) set up and configured

## How compilation works

This project follows the general idea of building explicit external memory for LLM workflows: turn raw context into compact reusable notes, then retrieve and refine those notes over time. A short reference for that approach is Andrej Karpathy's note here:

https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

`memory-cli` uses authenticated local CLIs as providers. Right now the supported providers are:

- `claude` via `claude -p`
- `codex` via `codex exec`

This means:

- **No API key needed** — uses your existing local CLI login/session
- **Full tool access** — the provider can read and write knowledge files directly

Before `memory sync`, `memory add`, and `memory query` run real work, `memory-cli` performs a lightweight provider availability check. If the primary provider is unavailable, it tries the next provider in `llm_fallback_order` and prints the fallback in the console.

Example:

```bash
memory config set llm_provider claude
memory config set llm_fallback_order '["claude","codex"]'
```

## Installation

```bash
uv tool install -e /path/to/memory-cli
```

This installs `memory` as a global command available in any shell.

Make sure `~/.local/bin` is on your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"  # add to ~/.zshrc
```

If your compiler lives somewhere other than `~/projects/ai/claude-memory-compiler`, either set the env var:

```bash
export MEMORY_COMPILER_DIR="/path/to/your/claude-memory-compiler"
```

Or run `memory config --edit` and set it there.

## Configuration

`memory-cli` stores its settings in a single file:

`~/.memory-cli/config.json`

The CLI reads and writes this file for both command behavior and provider selection. You can inspect the full config with `memory config`, list valid keys with `memory config keys`, read one value with `memory config get`, update one value with `memory config set`, or use `memory config --edit` for the interactive editor.

## Commands

### `memory sync`

Compile new or changed daily logs and clipped sources into knowledge articles.

```bash
memory sync                              # compile only new/changed files
memory sync --all                        # force recompile everything
memory sync --file daily/2026-04-10.md  # compile a specific file
memory sync --dry-run                    # preview what would be compiled
```

`memory-cli` now selects sync targets itself, so `sync.daily` and `sync.sources` are enforced by the CLI before delegation to the active provider.

Shows live progress while the selected provider compiles each file:
```
Compiling resources/ARCHITECTURE.md with codex...
Compiled resources/ARCHITECTURE.md with codex
```

### `memory add`

Import a standalone Markdown file into the configured vault resources folder and compile it immediately.

```bash
memory add /path/to/file.md
```

The command:

- copies the file to your configured resources folder
- refuses to overwrite an existing resource with the same name
- verifies provider availability before copying the file
- compiles only that imported file

Use this when you already have a local Markdown note or exported article and want it ingested without waiting for a broader `memory sync`.

### `memory lint`

Run 7 health checks on the knowledge base.

```bash
memory lint                    # all checks (includes LLM contradiction check)
memory lint --structural-only  # skip LLM check — instant, free
```

Checks: broken wikilinks · orphan pages · orphan sources · stale articles · missing backlinks · sparse articles · contradictions

Reports saved to `reports/lint-YYYY-MM-DD.md` in the compiler directory.

### `memory lint-fix`

Apply safe structural fixes to the knowledge base.

```bash
memory lint-fix
memory lint-fix --dry-run
```

Current scope:

- repairs missing backlinks when article `A` links to `B` but `B` does not link back to `A`
- does not use any provider/LLM
- does not rewrite contradictions, sparse articles, or broken links

### `memory query`

Ask a question and get an answer synthesized from the knowledge base.

```bash
memory query "What auth patterns do I use?"
memory query "What's my error handling strategy?" --file-back
```

`--file-back` saves the answer as a Q&A article in `knowledge/qa/` and updates the index — every question makes the KB smarter.

### `memory status`

Show knowledge base statistics.

```bash
memory status
```

```
  Knowledge Base Status
  ────────────────────────────────────
  Concepts              42
  Connections            8
  Q&A articles           5
  Daily logs            14
  Clipped sources        7
  Queries run           12

  Last daily compile : 2026-04-10T14:30:00
  Last source compile: 2026-04-10T12:15:00
  Last lint          : 2026-04-09T09:00:00
```

### `memory log`

Tail the knowledge build log.

```bash
memory log             # show last 30 entries
memory log -n 10       # show last 10 entries
```

### `memory config`

View or edit settings interactively.

```bash
memory config          # show current configuration
memory config keys
memory config get llm_provider
memory config set llm_provider codex
memory config set llm_fallback_order '["claude","codex"]'
memory config set daily_dirname journal
memory config set resources_dirname references
memory config set knowledge_dirname brain
memory config --edit   # interactive editor
```

Settings are stored at `~/.memory-cli/config.json`. The editor and `get/set` commands update the same file. You can configure:

- **Toggle sync folders** — enable/disable `daily/`, `resources/`, or add custom directories
- **Set paths** — compiler directory and Obsidian vault directory
- **Set vault folder names** — daily, resources, and knowledge subfolders under the vault
- **Providers** — primary LLM provider and ordered fallback providers
- **Behaviour** — auto-compile hour (0–23), default log lines, show/hide cost

At the moment:

- `sync.daily` and `sync.sources` are enforced directly by `memory-cli`
- `sync.custom_dirs` can be configured, but the current external compiler does not support compiling arbitrary custom directory files, so those entries are skipped with a warning
- configurable vault folder names work from the CLI side; `memory-cli` creates compiler-compatible aliases inside the vault so the external compiler can still operate

## How it works

`memory` is a thin wrapper around the compiler scripts:

| Command | Delegates to |
|---------|-------------|
| `memory sync` | `scripts/compile.py` via `uv run` |
| `memory lint` | `scripts/lint.py` via `uv run` |
| `memory query` | `scripts/query.py` via `uv run` |
| `memory status` | reads `scripts/state.json` directly |
| `memory log` | reads `knowledge/log.md` directly |
| `memory config` | reads/writes `~/.memory-cli/config.json` |

`compile.py` calls `claude -p` internally, using your authenticated Claude Code session.

## Configuration reference

| Setting | Default | Description |
|---------|---------|-------------|
| `compiler_dir` | `~/projects/ai/claude-memory-compiler` | Path to compiler |
| `vault_dir` | `~/My Documents/LLM-Brain-General` | Obsidian vault path |
| `daily_dirname` | `daily` | Daily logs folder under the vault |
| `resources_dirname` | `resources` | Imported/clipped sources folder under the vault |
| `knowledge_dirname` | `knowledge` | Knowledge base folder under the vault |
| `llm_provider` | `claude` | Backend used for compile and query flows |
| `llm_fallback_order` | `["claude"]` | Ordered provider fallback list |
| `sync.daily` | `true` | Compile daily session logs |
| `sync.sources` | `true` | Compile clipped web articles |
| `sync.custom_dirs` | `[]` | Extra directories to compile |
| `compile_after_hour` | `18` | Hour after which auto-compile fires |
| `log_lines` | `30` | Default lines for `memory log` |
| `show_cost` | `true` | Show cost in `memory status` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
