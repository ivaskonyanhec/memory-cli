"""
memory - CLI for the claude-memory-compiler knowledge base.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from memory_cli import config_store

console = Console()

VERSION = "0.1.0"


# ── Helpers ───────────────────────────────────────────────────────────

def get_compiler_dir() -> Path:
    env = os.environ.get("MEMORY_COMPILER_DIR")
    path = Path(env) if env else Path(config_store.get("compiler_dir"))
    if not path.exists():
        console.print(
            f"[bold red]✗[/] Compiler not found at [dim]{path}[/]\n"
            "  Run [bold]memory config[/] to set the correct path.",
        )
        sys.exit(1)
    return path


def get_vault_dir() -> Path:
    return Path(config_store.get("vault_dir"))


def uv() -> str:
    for candidate in [
        Path.home() / ".local" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/opt/homebrew/bin/uv"),
    ]:
        if candidate.exists():
            return str(candidate)
    return "uv"


def run_script(script: str, *args: str) -> subprocess.CompletedProcess:
    root = get_compiler_dir()
    cmd = [uv(), "run", "--directory", str(root), "python", str(root / "scripts" / script), *args]
    return subprocess.run(cmd, text=True)


def patch_compiler_config(key: str, value: str) -> None:
    """Rewrite a variable assignment in the compiler's config.py."""
    cfg_path = get_compiler_dir() / "scripts" / "config.py"
    if not cfg_path.exists():
        return
    content = cfg_path.read_text(encoding="utf-8")
    pattern = rf'^({re.escape(key)}\s*=\s*).*$'
    replacement = rf'\g<1>Path("{value}")'
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    if new_content != content:
        cfg_path.write_text(new_content, encoding="utf-8")


def section_header(title: str, subtitle: str = "") -> None:
    console.print(f"\n  [bold bright_cyan]◆[/]  [bold]{title}[/]  [dim]{subtitle}[/]")
    console.print("  [dim]─────────────────────────────────────[/]\n")


# ── Fancy help screen ─────────────────────────────────────────────────

def print_help() -> None:
    header = Text(justify="center")
    header.append("◆  ", style="bold bright_cyan")
    header.append("memory", style="bold white")
    header.append(f"  v{VERSION}", style="dim")
    header.append("  ◆", style="bold bright_cyan")
    subtitle = Text("Personal Knowledge Base Compiler", style="dim", justify="center")

    console.print()
    console.print(Panel(
        f"{header}\n{subtitle}",
        border_style="bright_cyan",
        padding=(0, 4),
        box=box.DOUBLE,
    ))
    desc = Text(justify="left")
    desc.append("Captures Claude Code conversations → extracts knowledge → compiles into your Obsidian vault.\n", style="white")
    desc.append("Uses your existing Claude Code session — no API key needed.", style="dim")
    console.print(desc)
    console.print()

    table = Table(
        show_header=True,
        header_style="bold bright_cyan",
        box=box.SIMPLE,
        padding=(0, 2),
        show_edge=False,
    )
    table.add_column("Command", style="bold white", min_width=8)
    table.add_column("Description", style="white")
    table.add_column("Key options", style="dim")

    table.add_row("sync",   "Compile new sessions and clipped sources",      "--all  --file  --dry-run")
    table.add_row("lint",   "Run 7 health checks on the knowledge base",     "--structural-only")
    table.add_row("query",  "Ask a question, get an answer from the KB",     "--file-back")
    table.add_row("status", "Show article counts, cost, last compile",       "")
    table.add_row("log",    "Tail the knowledge build log",                  "-n  (default 30)")
    table.add_row("config", "View and edit settings",                        "--edit")

    console.print(table)
    console.print()
    console.print("  [dim]Run[/]  [bold]memory [cyan]<command>[/cyan] --help[/]  [dim]for details on any command.[/]")
    console.print()


# ── CLI root ──────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context):
    """Personal knowledge base compiler CLI."""
    if ctx.invoked_subcommand is None:
        print_help()


# ── memory sync ───────────────────────────────────────────────────────

@main.command()
@click.option("--all", "force_all", is_flag=True, help="Force recompile all files.")
@click.option("--file", "target_file", type=str, default=None, help="Compile a specific file.")
@click.option("--dry-run", is_flag=True, help="Show what would be compiled without running.")
def sync(force_all: bool, target_file: str | None, dry_run: bool):
    """Compile new daily logs and clipped sources into knowledge articles."""
    cfg = config_store.load()
    sync_cfg = cfg.get("sync", {})
    daily_enabled = sync_cfg.get("daily", True)
    sources_enabled = sync_cfg.get("sources", True)
    custom_dirs: list[str] = sync_cfg.get("custom_dirs", [])

    section_header("memory sync", "(dry run)" if dry_run else "")

    if not daily_enabled and not sources_enabled and not custom_dirs:
        console.print("  [yellow]⚠[/]  All sync folders are disabled. Run [bold]memory config --edit[/] to enable some.\n")
        return

    disabled = []
    if not daily_enabled:
        disabled.append("daily/")
    if not sources_enabled:
        disabled.append("sources/")
    if disabled:
        console.print(f"  [dim]Skipping (disabled in config): {', '.join(disabled)}[/]\n")

    args: list[str] = []
    if force_all:
        args.append("--all")
    if target_file:
        args.extend(["--file", target_file])
    if dry_run:
        args.append("--dry-run")

    # Pass enabled folders via env vars the compiler can read
    env = os.environ.copy()
    env["MEMORY_SYNC_DAILY"] = "1" if daily_enabled else "0"
    env["MEMORY_SYNC_SOURCES"] = "1" if sources_enabled else "0"
    env["MEMORY_CUSTOM_DIRS"] = json.dumps(custom_dirs)

    root = get_compiler_dir()
    cmd = [uv(), "run", "--directory", str(root), "python", str(root / "scripts" / "compile.py"), *args]
    result = subprocess.run(cmd, text=True, env=env)
    console.print()
    sys.exit(result.returncode)


# ── memory lint ───────────────────────────────────────────────────────

@main.command()
@click.option("--structural-only", is_flag=True, help="Skip LLM contradiction check (free).")
def lint(structural_only: bool):
    """Run knowledge base health checks (broken links, orphans, contradictions, etc.)."""
    args: list[str] = ["--structural-only"] if structural_only else []
    mode = "structural only" if structural_only else "full  (includes LLM check)"
    section_header("memory lint", mode)
    result = run_script("lint.py", *args)
    console.print()
    sys.exit(result.returncode)


# ── memory query ─────────────────────────────────────────────────────

@main.command()
@click.argument("question")
@click.option("--file-back", is_flag=True, help="Save the answer as a Q&A article in knowledge/qa/.")
def query(question: str, file_back: bool):
    """Ask a question and get an answer from the knowledge base."""
    args = [question] + (["--file-back"] if file_back else [])
    section_header("memory query")
    console.print(f"  [dim]Q:[/] {question}\n")
    result = run_script("query.py", *args)
    console.print()
    sys.exit(result.returncode)


# ── memory status ────────────────────────────────────────────────────

@main.command()
def status():
    """Show knowledge base stats: article count, total cost, last compile."""
    cfg = config_store.load()
    root = get_compiler_dir()
    state_file = root / "scripts" / "state.json"

    state: dict = {}
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))

    ingested = state.get("ingested", {})
    sources_state = state.get("sources", {})
    total_cost = state.get("total_cost", 0.0)
    query_count = state.get("query_count", 0)
    last_lint = state.get("last_lint")

    vault = get_vault_dir() / "knowledge"
    concept_count    = len(list((vault / "concepts").glob("*.md")))    if (vault / "concepts").exists()    else 0
    connection_count = len(list((vault / "connections").glob("*.md"))) if (vault / "connections").exists() else 0
    qa_count         = len(list((vault / "qa").glob("*.md")))          if (vault / "qa").exists()          else 0

    last_daily  = max((v.get("compiled_at", "") for v in ingested.values()),      default=None)
    last_source = max((v.get("compiled_at", "") for v in sources_state.values()), default=None)

    section_header("memory status")

    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2), show_edge=False)
    table.add_column("Label", style="dim", min_width=22)
    table.add_column("Value", style="bold white", justify="right", min_width=8)

    table.add_row("Concepts",        str(concept_count))
    table.add_row("Connections",     str(connection_count))
    table.add_row("Q&A articles",    str(qa_count))
    table.add_row("Daily logs",      str(len(ingested)))
    table.add_row("Clipped sources", str(len(sources_state)))
    table.add_row("Queries run",     str(query_count))

    if cfg.get("show_cost", True):
        table.add_section()
        table.add_row("Total API cost", f"[bright_green]${total_cost:.2f}[/bright_green]")

    console.print(table)

    if last_daily or last_source or last_lint:
        console.print()
        if last_daily:
            console.print(f"  [dim]Last daily compile :[/]  {last_daily[:19]}")
        if last_source:
            console.print(f"  [dim]Last source compile:[/]  {last_source[:19]}")
        if last_lint:
            console.print(f"  [dim]Last lint          :[/]  {str(last_lint)[:19]}")

    console.print()


# ── memory log ───────────────────────────────────────────────────────

@main.command()
@click.option("-n", "--lines", default=None, type=int, help="Number of log entries to show.")
def log(lines: int | None):
    """Tail the knowledge build log."""
    n = lines or config_store.get("log_lines", 30)
    log_path = get_vault_dir() / "knowledge" / "log.md"

    section_header("memory log", f"last {n} entries")

    if not log_path.exists():
        console.print("  [dim]No build log yet — run[/] [bold]memory sync[/] [dim]first.[/]\n")
        return

    content = log_path.read_text(encoding="utf-8")
    entries = content.split("\n## [")
    recent = entries[-n:] if len(entries) > n else entries
    output = "\n## [".join(recent).strip()

    for line in output.splitlines():
        if line.startswith("## ["):
            console.print(f"  [bold bright_cyan]{line}[/]")
        elif line.startswith("- "):
            console.print(f"  [dim]{line}[/]")
        elif line.strip():
            console.print(f"  {line}")

    console.print()


# ── memory config ────────────────────────────────────────────────────

@main.command()
@click.option("--edit", is_flag=True, help="Open interactive settings editor.")
def config(edit: bool):
    """View current settings, or edit them with --edit."""
    if edit:
        _config_editor()
    else:
        _config_show()


def _config_show() -> None:
    """Print current config as a readable table."""
    cfg = config_store.load()
    sync_cfg = cfg.get("sync", {})
    custom_dirs = sync_cfg.get("custom_dirs", [])

    section_header("memory config")

    # Paths
    paths_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2), show_edge=False)
    paths_table.add_column("Key",   style="dim",        min_width=20)
    paths_table.add_column("Value", style="bold white")

    paths_table.add_row("Compiler dir",   cfg.get("compiler_dir", "—"))
    paths_table.add_row("Vault dir",      cfg.get("vault_dir", "—"))

    console.print("  [bold]Paths[/]")
    console.print(paths_table)

    # Sync
    sync_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2), show_edge=False)
    sync_table.add_column("Folder", style="dim",       min_width=20)
    sync_table.add_column("State",  style="bold white")

    sync_table.add_row("daily/",   "[green]enabled[/]"  if sync_cfg.get("daily",   True) else "[red]disabled[/]")
    sync_table.add_row("sources/", "[green]enabled[/]"  if sync_cfg.get("sources", True) else "[red]disabled[/]")
    for d in custom_dirs:
        sync_table.add_row(d, "[green]enabled[/]")

    console.print("  [bold]Sync folders[/]")
    console.print(sync_table)

    # Behaviour
    beh_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2), show_edge=False)
    beh_table.add_column("Setting",  style="dim",        min_width=20)
    beh_table.add_column("Value",    style="bold white")

    beh_table.add_row("Auto-compile after", f"{cfg.get('compile_after_hour', 18)}:00")
    beh_table.add_row("Log lines default",  str(cfg.get("log_lines", 30)))
    beh_table.add_row("Show cost",          "[green]yes[/]" if cfg.get("show_cost", True) else "[red]no[/]")

    console.print("  [bold]Behaviour[/]")
    console.print(beh_table)

    console.print("  [dim]Run[/] [bold]memory config --edit[/] [dim]to change settings.[/]\n")


def _config_editor() -> None:
    """Interactive settings editor using rich prompts."""
    cfg = config_store.load()

    section_header("memory config", "interactive editor")
    console.print("  [dim]Press Enter to keep current value. Ctrl+C to cancel.[/]\n")

    try:
        # ── Paths ──────────────────────────────────────────────────────
        console.rule("[dim]  Paths  [/]", style="dim")
        console.print()

        compiler = Prompt.ask(
            "  [dim]Compiler dir[/]",
            default=cfg.get("compiler_dir"),
            console=console,
        )
        if compiler != cfg.get("compiler_dir"):
            cfg["compiler_dir"] = compiler

        vault = Prompt.ask(
            "  [dim]Vault dir[/]",
            default=cfg.get("vault_dir"),
            console=console,
        )
        if vault != cfg.get("vault_dir"):
            cfg["vault_dir"] = vault
            # Propagate to the compiler's config.py so scripts use the new path
            patch_compiler_config("VAULT_DIR", vault)
            console.print(f"  [dim]↳ Updated VAULT_DIR in compiler config.py[/]")

        # ── Sync folders ───────────────────────────────────────────────
        console.print()
        console.rule("[dim]  Sync folders  [/]", style="dim")
        console.print()
        console.print("  Which folders should [bold]memory sync[/] compile?\n")

        sync_cfg = cfg.setdefault("sync", {})

        daily_on = _toggle_prompt("  daily/   (AI session logs)", sync_cfg.get("daily", True))
        sync_cfg["daily"] = daily_on

        sources_on = _toggle_prompt("  sources/ (Obsidian Clipper)", sync_cfg.get("sources", True))
        sync_cfg["sources"] = sources_on

        # Custom dirs
        custom_dirs: list[str] = sync_cfg.get("custom_dirs", [])
        console.print()
        if custom_dirs:
            console.print("  [dim]Current custom dirs:[/]")
            for i, d in enumerate(custom_dirs):
                console.print(f"    [dim]{i+1}.[/] {d}")
            console.print()

        if Confirm.ask("  Add a custom sync folder?", default=False, console=console):
            while True:
                new_dir = Prompt.ask("  [dim]Absolute path[/]", console=console)
                if new_dir and new_dir not in custom_dirs:
                    custom_dirs.append(new_dir)
                    console.print(f"  [green]✓[/] Added {new_dir}")
                if not Confirm.ask("  Add another?", default=False, console=console):
                    break

        if custom_dirs and Confirm.ask("  Remove a custom folder?", default=False, console=console):
            for i, d in enumerate(custom_dirs):
                console.print(f"    [dim]{i+1}.[/] {d}")
            idx_str = Prompt.ask("  Number to remove", console=console)
            try:
                idx = int(idx_str) - 1
                removed = custom_dirs.pop(idx)
                console.print(f"  [green]✓[/] Removed {removed}")
            except (ValueError, IndexError):
                console.print("  [yellow]Invalid number, skipping.[/]")

        sync_cfg["custom_dirs"] = custom_dirs

        # ── Behaviour ──────────────────────────────────────────────────
        console.print()
        console.rule("[dim]  Behaviour  [/]", style="dim")
        console.print()

        hour_str = Prompt.ask(
            "  [dim]Auto-compile after hour (0-23)[/]",
            default=str(cfg.get("compile_after_hour", 18)),
            console=console,
        )
        try:
            hour = int(hour_str)
            if 0 <= hour <= 23:
                cfg["compile_after_hour"] = hour
                # Patch the compiler's flush.py constant
                _patch_flush_hour(hour)
            else:
                console.print("  [yellow]Out of range, keeping current value.[/]")
        except ValueError:
            console.print("  [yellow]Not a number, keeping current value.[/]")

        log_lines_str = Prompt.ask(
            "  [dim]Default lines for 'memory log'[/]",
            default=str(cfg.get("log_lines", 30)),
            console=console,
        )
        try:
            cfg["log_lines"] = max(1, int(log_lines_str))
        except ValueError:
            pass

        show_cost = Confirm.ask(
            "  Show API cost in 'memory status'?",
            default=cfg.get("show_cost", True),
            console=console,
        )
        cfg["show_cost"] = show_cost

        # ── Save ───────────────────────────────────────────────────────
        console.print()
        config_store.save(cfg)
        console.print("  [bold green]✓[/]  Settings saved to [dim]~/.memory-cli/config.json[/]\n")

    except (KeyboardInterrupt, click.Abort):
        console.print("\n\n  [dim]Cancelled — no changes saved.[/]\n")


def _toggle_prompt(label: str, current: bool) -> bool:
    """Show an enable/disable prompt with current state."""
    state_str = "[green]enabled[/]" if current else "[red]disabled[/]"
    console.print(f"  {label}  →  {state_str}")
    flip = Confirm.ask(
        f"  {'Disable' if current else 'Enable'} this folder?",
        default=False,
        console=console,
    )
    result = (not current) if flip else current
    console.print()
    return result


def _patch_flush_hour(hour: int) -> None:
    """Update COMPILE_AFTER_HOUR constant in the compiler's flush.py."""
    flush_path = get_compiler_dir() / "scripts" / "flush.py"
    if not flush_path.exists():
        return
    content = flush_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^(COMPILE_AFTER_HOUR\s*=\s*)\d+',
        rf'\g<1>{hour}',
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        flush_path.write_text(new_content, encoding="utf-8")
        console.print(f"  [dim]↳ Updated COMPILE_AFTER_HOUR in flush.py → {hour}[/]")
