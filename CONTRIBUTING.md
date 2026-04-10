# Contributing to memory-cli

Thanks for your interest in contributing.

## Project structure

```
memory-cli/
├── pyproject.toml          # package metadata and entry point
├── README.md
├── CONTRIBUTING.md
└── memory_cli/
    ├── __init__.py
    ├── cli.py              # all commands live here (Click-based)
    └── config_store.py     # persistent config at ~/.memory-cli/config.json
```

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/memory-cli
cd memory-cli
uv tool install -e .
```

The `-e` flag installs in editable mode — changes to `cli.py` take effect immediately without reinstalling.

## Adding a new command

1. Add a new `@main.command()` function in `memory_cli/cli.py`
2. Follow the existing pattern: delegate to a compiler script via `run_script()`, or read vault/state files directly for read-only commands
3. Update `README.md` with the new command's description and options

Example skeleton:

```python
@main.command()
@click.option("--flag", is_flag=True, help="Description.")
def mycommand(flag: bool):
    """One-line description shown in --help."""
    args = ["--flag"] if flag else []
    result = run_script("myscript.py", *args)
    sys.exit(result.returncode)
```

## Design principles

- **Thin wrapper**: `memory-cli` delegates to `claude-memory-compiler` scripts. Business logic lives in the compiler, not here.
- **No hidden state**: Commands either delegate to scripts or read `state.json` / markdown files directly. No caching, no extra databases.
- **Portable**: The `MEMORY_COMPILER_DIR` env var lets anyone point the CLI at their own compiler installation.
- **Fail loudly**: If the compiler directory is missing, exit with a clear error rather than guessing.

## Sending a pull request

1. Fork the repo and create a branch: `git checkout -b my-feature`
2. Make your changes
3. Test manually: `memory --help`, `memory sync --dry-run`, `memory status`
4. Open a PR with a clear description of what the command does and why it's useful
