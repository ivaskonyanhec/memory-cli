# memory-cli

A global CLI for the [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) knowledge base.

Turns verbose `uv run python scripts/compile.py` invocations into simple shell commands:

```bash
memory sync          # compile new conversations and clipped articles
memory add FILE.md   # import a markdown file into resources/ and compile it
memory lint          # run 7 knowledge base health checks
memory query "..."   # ask the knowledge base a question
memory status        # show article counts, last compile time
memory log           # tail the build log
memory config        # view and edit settings
memory config --edit # interactive settings editor
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Claude Code](https://claude.ai/code) — installed and authenticated (`claude` must be on PATH)
- [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) set up and configured

## How compilation works

`memory sync` uses `claude -p` (Claude Code's headless/scripting mode) to run the compiler. This means:

- **No API key needed** — uses your existing Claude Code session
- **No subprocess hangs** — `claude -p` exits cleanly after the task completes
- **Full tool access** — Claude reads files and writes knowledge articles directly

This is different from the `claude_agent_sdk` approach, which requires a streaming protocol that doesn't work outside interactive Claude Code sessions.

Before `memory sync` and `memory add` run a real compile, `memory-cli` now performs a lightweight Claude availability check. If your Claude session is unavailable or your usage is exhausted, the command stops early instead of staging or compiling files into inconsistent state.

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

## Commands

### `memory sync`

Compile new or changed daily logs and clipped sources into knowledge articles.

```bash
memory sync                              # compile only new/changed files
memory sync --all                        # force recompile everything
memory sync --file daily/2026-04-10.md  # compile a specific file
memory sync --dry-run                    # preview what would be compiled
```

Shows live progress as Claude writes each article:
```
[1/1] Compiling source: Git Commit Message AI.md...
    Write: ai-git-commit-workflow.md
    Write: llm-cli-tool.md
    Edit:  index.md
    Edit:  log.md
  Done.
```

### `memory add`

Import a standalone Markdown file into the vault's `resources/` folder and compile it immediately.

```bash
memory add /path/to/file.md
```

The command:

- copies the file to `resources/<basename>.md`
- refuses to overwrite an existing resource with the same name
- verifies Claude availability before copying the file
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
memory config --edit   # interactive editor
```

Settings are stored at `~/.memory-cli/config.json`. The editor lets you:

- **Toggle sync folders** — enable/disable `daily/`, `resources/`, or add custom directories
- **Set paths** — compiler directory and Obsidian vault directory
- **Behaviour** — auto-compile hour (0–23), default log lines, show/hide cost

Changes to vault path and compile hour are written back to the compiler's `config.py` and `flush.py` automatically.

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
| `sync.daily` | `true` | Compile daily session logs |
| `sync.sources` | `true` | Compile clipped web articles |
| `sync.custom_dirs` | `[]` | Extra directories to compile |
| `compile_after_hour` | `18` | Hour after which auto-compile fires |
| `log_lines` | `30` | Default lines for `memory log` |
| `show_cost` | `true` | Show cost in `memory status` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
