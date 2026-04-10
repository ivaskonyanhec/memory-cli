"""
memory - CLI for the claude-memory-compiler knowledge base.
"""

from __future__ import annotations

import json
import os
import hashlib
import shutil
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
from memory_cli.providers import ClaudeProvider, CodexProvider

console = Console()

VERSION = "0.1.0"
COMPILER_VAULT_DIR_ALIASES = {
    "daily": "daily_dirname",
    "resources": "resources_dirname",
    "knowledge": "knowledge_dirname",
}
PROVIDER_ALIASES = {
    "openai": "codex",
}


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


def get_daily_dir() -> Path:
    return get_vault_dir() / config_store.get("daily_dirname", "daily")


def get_resources_dir() -> Path:
    return get_vault_dir() / config_store.get("resources_dirname", "resources")


def get_knowledge_dir() -> Path:
    return get_vault_dir() / config_store.get("knowledge_dirname", "knowledge")


def uv() -> str:
    for candidate in [
        Path.home() / ".local" / "bin" / "uv",
        Path("/usr/local/bin/uv"),
        Path("/opt/homebrew/bin/uv"),
    ]:
        if candidate.exists():
            return str(candidate)
    return "uv"


def make_provider(provider_name: str):
    provider_name = PROVIDER_ALIASES.get(provider_name, provider_name)
    if provider_name == "claude":
        return ClaudeProvider(
            compiler_dir_getter=get_compiler_dir,
            uv_getter=uv,
            run_script=run_script,
        )
    if provider_name == "codex":
        return CodexProvider(
            compiler_dir_getter=get_compiler_dir,
            vault_dir_getter=get_vault_dir,
            daily_dir_getter=get_daily_dir,
            resources_dir_getter=get_resources_dir,
            knowledge_dir_getter=get_knowledge_dir,
        )
    raise click.ClickException(f"Unknown provider: {provider_name}")


def get_provider_names() -> list[str]:
    primary = config_store.get("llm_provider", "claude")
    configured = config_store.get("llm_fallback_order", None)
    candidates = configured if configured else [primary]

    ordered: list[str] = []
    for name in [primary, *candidates]:
        canonical = PROVIDER_ALIASES.get(name, name)
        if canonical not in ordered:
            ordered.append(canonical)
    return ordered


def resolve_available_provider():
    errors: list[tuple[str, str]] = []
    chosen_name: str | None = None
    chosen_provider = None

    raw_names = config_store.get("llm_fallback_order", None) or [config_store.get("llm_provider", "claude")]
    seen: set[str] = set()
    ordered_pairs: list[tuple[str, str]] = []
    for raw_name in [config_store.get("llm_provider", "claude"), *raw_names]:
        canonical = PROVIDER_ALIASES.get(raw_name, raw_name)
        if canonical in seen:
            continue
        seen.add(canonical)
        ordered_pairs.append((raw_name, canonical))

    for raw_name, provider_name in ordered_pairs:
        if raw_name != provider_name:
            console.print(
                f"  [yellow]⚠[/] Provider alias [bold]{raw_name}[/] is deprecated; using [bold]{provider_name}[/] instead."
            )
        provider = make_provider(provider_name)
        try:
            provider.check_available()
            chosen_name = provider_name
            chosen_provider = provider
            break
        except click.ClickException as exc:
            errors.append((provider_name, str(exc)))
            console.print(f"  [yellow]⚠[/] Provider unavailable: [bold]{provider_name}[/]")

    if chosen_provider is None or chosen_name is None:
        details = "\n".join(f"  - {name}: {message}" for name, message in errors)
        raise click.ClickException(f"No available providers.\n{details}")

    if errors:
        console.print(f"  [bright_cyan]→[/] Falling back to provider: [bold]{chosen_name}[/]\n")

    return chosen_provider


def run_script(script: str, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    ensure_compiler_vault_aliases()
    root = get_compiler_dir()
    cmd = [uv(), "run", "--directory", str(root), "python", str(root / "scripts" / script), *args]
    return subprocess.run(cmd, text=True, capture_output=capture_output)


def import_markdown_resource(source: Path) -> tuple[Path, str]:
    """Copy a markdown file into the vault resources folder."""
    if not source.exists():
        raise click.ClickException(f"Source file does not exist: {source}")
    if not source.is_file():
        raise click.ClickException(f"Source path is not a file: {source}")
    if source.suffix.lower() != ".md":
        raise click.ClickException(f"Source file must be a .md file: {source}")

    resources_dir = get_resources_dir()
    resources_dir.mkdir(parents=True, exist_ok=True)

    destination = resources_dir / source.name
    if destination.exists():
        raise click.ClickException(f"Resource already exists: {destination}")

    shutil.copy2(source, destination)
    return destination, f"resources/{source.name}"


def ensure_compiler_vault_aliases() -> None:
    vault_dir = get_vault_dir()
    vault_dir.mkdir(parents=True, exist_ok=True)

    for compiler_name, config_key in COMPILER_VAULT_DIR_ALIASES.items():
        configured_name = config_store.get(config_key, compiler_name)
        configured_path = vault_dir / configured_name
        configured_path.mkdir(parents=True, exist_ok=True)

        alias_path = vault_dir / compiler_name
        if alias_path == configured_path:
            continue

        if alias_path.is_symlink():
            if alias_path.resolve() == configured_path.resolve():
                continue
            raise click.ClickException(
                f"Compiler alias conflict: {alias_path} points to {alias_path.resolve()}, expected {configured_path}."
            )

        if alias_path.exists():
            raise click.ClickException(
                f"Compiler alias conflict: {alias_path} exists, but {config_key} is set to {configured_name}."
            )

        alias_path.symlink_to(configured_path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_compiler_state() -> dict:
    state_file = get_compiler_dir() / "scripts" / "state.json"
    if not state_file.exists():
        return {"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}
    return json.loads(state_file.read_text(encoding="utf-8"))


def list_sync_targets(force_all: bool, target_file: str | None) -> tuple[list[str], list[str]]:
    if target_file:
        return [target_file], []

    cfg = config_store.load()
    sync_cfg = cfg.get("sync", {})
    daily_enabled = sync_cfg.get("daily", True)
    sources_enabled = sync_cfg.get("sources", True)
    custom_dirs: list[str] = sync_cfg.get("custom_dirs", [])

    vault_dir = get_vault_dir()
    state = load_compiler_state()
    targets: list[str] = []
    warnings: list[str] = []

    if daily_enabled:
        daily_dir = get_daily_dir()
        if daily_dir.exists():
            for path in sorted(daily_dir.glob("*.md")):
                if force_all or _needs_compile(path, state.get("ingested", {})):
                    targets.append(f"daily/{path.name}")

    if sources_enabled:
        resources_dir = get_resources_dir()
        if resources_dir.exists():
            for path in sorted(resources_dir.glob("*.md")):
                if force_all or _needs_compile(path, state.get("sources", {})):
                    targets.append(f"resources/{path.name}")

    if custom_dirs:
        warnings.append(
            "Custom sync dirs are not supported by the current external compiler and will be skipped."
        )

    return targets, warnings


def _needs_compile(path: Path, state_bucket: dict) -> bool:
    entry = state_bucket.get(path.name)
    if not entry:
        return True
    return entry.get("hash") != file_hash(path)


def parse_config_value(raw: str):
    lowered = raw.lower()
    if lowered in {"true", "false", "null"}:
        return json.loads(lowered)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def format_config_value(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2)


def extract_wikilinks(content: str) -> list[str]:
    import re

    return re.findall(r"\[\[([^\]]+)\]\]", content)


def list_knowledge_articles() -> list[Path]:
    knowledge_dir = get_knowledge_dir()
    articles: list[Path] = []
    for subdir in ["concepts", "connections", "qa"]:
        directory = knowledge_dir / subdir
        if directory.exists():
            articles.extend(sorted(directory.glob("*.md")))
    return articles


def compute_missing_backlinks() -> list[tuple[Path, str]]:
    knowledge_dir = get_knowledge_dir()
    missing: list[tuple[Path, str]] = []

    for article in list_knowledge_articles():
        source_rel = article.relative_to(knowledge_dir)
        source_link = str(source_rel).replace(".md", "").replace("\\", "/")
        content = article.read_text(encoding="utf-8")

        for link in extract_wikilinks(content):
            if link.startswith("daily/"):
                continue
            target_path = knowledge_dir / f"{link}.md"
            if not target_path.exists():
                continue
            target_content = target_path.read_text(encoding="utf-8")
            if f"[[{source_link}]]" not in target_content:
                missing.append((target_path, source_link))

    return missing


def add_backlink(path: Path, backlink: str, dry_run: bool) -> bool:
    content = path.read_text(encoding="utf-8")
    link_markup = f"[[{backlink}]]"
    if link_markup in content:
        return False

    lines = content.splitlines()
    related_heading = "## Related Concepts"
    if related_heading in lines:
        index = lines.index(related_heading)
        insert_at = index + 1
        while insert_at < len(lines) and lines[insert_at].strip():
            insert_at += 1
        lines.insert(insert_at, f"- {link_markup}")
        new_content = "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    else:
        suffix = "" if content.endswith("\n") else "\n"
        new_content = f"{content}{suffix}\n## Related Concepts\n- {link_markup}\n"

    if not dry_run:
        path.write_text(new_content, encoding="utf-8")
    return True


def section_header(title: str, subtitle: str = "") -> None:
    console.print(f"\n  [bold bright_cyan]◆[/]  [bold]{title}[/]  [dim]{subtitle}[/]")
    console.print("  [dim]─────────────────────────────────────[/]\n")


def run_with_status(
    label: str,
    fn,
    *args,
    success_label: str | None = None,
    spinner: str = "dots12",
    **kwargs,
):
    with console.status(f"[bold]{label}[/]", spinner=spinner):
        result = fn(*args, **kwargs)
    if success_label:
        console.print(f"  [green]✓[/] {success_label}")
    return result


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
    table.add_row("add",    "Import a markdown resource and compile it",     "")
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

    targets, warnings = run_with_status(
        "Selecting sync targets...",
        list_sync_targets,
        force_all,
        target_file,
    )
    console.print(f"  [green]✓[/] Sync targets selected: [bold]{len(targets)}[/]")
    for warning in warnings:
        console.print(f"  [yellow]⚠[/] {warning}\n")

    if not targets:
        console.print("  [dim]Nothing to compile for the enabled sync targets.[/]\n")
        return

    if dry_run:
        console.print(f"  [bold]Files to compile ({len(targets)})[/]")
        for target in targets:
            console.print(f"    {target}")
        console.print()
        return

    provider = run_with_status(
        "Checking providers...",
        resolve_available_provider,
    )
    provider_name = provider.__class__.__name__.removesuffix("Provider").lower()
    console.print(f"  [green]✓[/] Provider ready: [bold]{provider_name}[/]")
    returncode = 0
    for target in targets:
        current = run_with_status(f"Compiling {target} with {provider_name}...", provider.compile_one, target)
        console.print(f"  [green]✓[/] Compiled [bold]{target}[/] with [bold]{provider_name}[/]")
        if current != 0:
            returncode = current
            break

    console.print()
    sys.exit(returncode)


# ── memory add ────────────────────────────────────────────────────────

@main.command()
@click.argument("source_path", type=click.Path(path_type=Path))
def add(source_path: Path):
    """Import a markdown file into resources/ and compile it immediately."""
    section_header("memory add")

    provider = run_with_status("Checking providers...", resolve_available_provider)
    provider_name = provider.__class__.__name__.removesuffix("Provider").lower()
    console.print(f"  [green]✓[/] Provider ready: [bold]{provider_name}[/]")
    _, target_file = run_with_status(
        "Importing markdown into resources...",
        import_markdown_resource,
        source_path.expanduser().resolve(),
    )
    console.print(f"  [green]✓[/] Imported [dim]{source_path}[/] -> [bold]{target_file}[/]\n")

    returncode = run_with_status(
        f"Compiling {target_file} with {provider_name}...",
        provider.compile_one,
        target_file,
    )
    console.print(f"  [green]✓[/] Compiled [bold]{target_file}[/] with [bold]{provider_name}[/]")
    console.print()
    sys.exit(returncode)


# ── memory lint ───────────────────────────────────────────────────────

@main.command()
@click.option("--structural-only", is_flag=True, help="Skip LLM contradiction check (free).")
def lint(structural_only: bool):
    """Run knowledge base health checks (broken links, orphans, contradictions, etc.)."""
    args: list[str] = ["--structural-only"] if structural_only else []
    mode = "structural only" if structural_only else "full  (includes LLM check)"
    section_header("memory lint", mode)
    lint_label = "Running structural lint checks..." if structural_only else "Running full lint checks..."
    result = run_with_status(
        lint_label,
        run_script,
        "lint.py",
        *args,
        capture_output=True,
    )
    if result.stdout:
        console.print(result.stdout, end="")

    if not structural_only and _is_llm_lint_failure(result):
        console.print("\n  [yellow]⚠[/] LLM contradiction check failed; retrying structural lint only.\n")
        fallback = run_with_status(
            "Retrying lint in structural-only mode...",
            run_script,
            "lint.py",
            "--structural-only",
            capture_output=True,
            success_label="Structural lint retry completed.",
        )
        if fallback.stdout:
            console.print(fallback.stdout, end="")
        if fallback.stderr and fallback.returncode != 0:
            console.print(fallback.stderr, end="")
        console.print()
        sys.exit(fallback.returncode)

    if result.stderr and result.returncode != 0:
        console.print(result.stderr, end="")
    if result.returncode == 0:
        completed_label = "Structural lint completed." if structural_only else "Full lint completed."
        console.print(f"  [green]✓[/] {completed_label}")
    console.print()
    sys.exit(result.returncode)


def _is_llm_lint_failure(result: subprocess.CompletedProcess) -> bool:
    if result.returncode == 0 or not result.stderr:
        return False
    stderr = result.stderr
    return (
        "check_contradictions" in stderr
        or "claude_agent_sdk" in stderr
        or "KeyboardInterrupt" in stderr
        or "Traceback" in stderr
    )


@main.command("lint-fix")
@click.option("--dry-run", is_flag=True, help="Show planned structural fixes without editing files.")
def lint_fix(dry_run: bool):
    """Apply safe structural fixes to the knowledge base."""
    section_header("memory lint-fix", "(dry run)" if dry_run else "")

    fixes = run_with_status(
        "Scanning knowledge base for safe fixes...",
        compute_missing_backlinks,
        success_label="Safe structural fixes scanned.",
    )
    applied = 0
    for path, backlink in fixes:
        action = "Would update" if dry_run else "Updated"
        changed = add_backlink(path, backlink, dry_run=dry_run)
        if changed:
            applied += 1
            console.print(f"  [green]✓[/] {action} [bold]{path.name}[/] with [dim][[{backlink}]][/]")

    if applied == 0:
        console.print("  [dim]No safe fixes to apply.[/]\n")
        return

    console.print(f"\n  [bold]Applied fixes:[/] {applied}\n")


# ── memory query ─────────────────────────────────────────────────────

@main.command()
@click.argument("question")
@click.option("--file-back", is_flag=True, help="Save the answer as a Q&A article in knowledge/qa/.")
def query(question: str, file_back: bool):
    """Ask a question and get an answer from the knowledge base."""
    section_header("memory query")
    console.print(f"  [dim]Q:[/] {question}\n")
    provider = run_with_status("Checking providers...", resolve_available_provider)
    provider_name = provider.__class__.__name__.removesuffix("Provider").lower()
    console.print(f"  [green]✓[/] Provider ready: [bold]{provider_name}[/]")
    returncode = run_with_status(
        f"Querying knowledge base with {provider_name}...",
        provider.query,
        question,
        file_back,
    )
    console.print()
    sys.exit(returncode)


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

    vault = get_knowledge_dir()
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
    log_path = get_knowledge_dir() / "log.md"

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

@main.group(invoke_without_command=True)
@click.option("--edit", is_flag=True, help="Open interactive settings editor.")
@click.pass_context
def config(ctx: click.Context, edit: bool):
    """View, get, set, or edit CLI settings stored in one config file."""
    if edit:
        _config_editor()
        return
    if ctx.invoked_subcommand is None:
        _config_show()


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """Print a config value by key."""
    value = config_store.get(key)
    if value is None:
        raise click.ClickException(f"Unknown config key: {key}")
    console.print(format_config_value(value))


@config.command("keys")
def config_keys():
    """List all available config keys."""
    section_header("memory config", "available keys")
    for key in config_store.list_keys():
        console.print(f"  {key}")
    console.print()


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a config value by key."""
    parsed = parse_config_value(value)
    config_store.set_key(key, parsed)
    console.print(f"[green]✓[/] Set [bold]{key}[/] = {format_config_value(parsed)}")


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
    paths_table.add_row("Daily folder",   cfg.get("daily_dirname", "daily"))
    paths_table.add_row("Resources folder", cfg.get("resources_dirname", "resources"))
    paths_table.add_row("Knowledge folder", cfg.get("knowledge_dirname", "knowledge"))
    paths_table.add_row("LLM provider",   cfg.get("llm_provider", "—"))
    paths_table.add_row("Fallback order", format_config_value(cfg.get("llm_fallback_order", [])))

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

    beh_table.add_row("Provider",            cfg.get("llm_provider", "claude"))
    beh_table.add_row("Fallback order",      format_config_value(cfg.get("llm_fallback_order", ["claude"])))
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

        daily_dirname = Prompt.ask(
            "  [dim]Daily folder name[/]",
            default=str(cfg.get("daily_dirname", "daily")),
            console=console,
        )
        cfg["daily_dirname"] = daily_dirname

        resources_dirname = Prompt.ask(
            "  [dim]Resources folder name[/]",
            default=str(cfg.get("resources_dirname", "resources")),
            console=console,
        )
        cfg["resources_dirname"] = resources_dirname

        knowledge_dirname = Prompt.ask(
            "  [dim]Knowledge folder name[/]",
            default=str(cfg.get("knowledge_dirname", "knowledge")),
            console=console,
        )
        cfg["knowledge_dirname"] = knowledge_dirname

        vault = Prompt.ask(
            "  [dim]Vault dir[/]",
            default=cfg.get("vault_dir"),
            console=console,
        )
        if vault != cfg.get("vault_dir"):
            cfg["vault_dir"] = vault

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

        provider_name = Prompt.ask(
            "  [dim]LLM provider[/]",
            default=str(cfg.get("llm_provider", "claude")),
            console=console,
        )
        cfg["llm_provider"] = provider_name

        fallback_order = Prompt.ask(
            "  [dim]Fallback order (JSON array)[/]",
            default=format_config_value(cfg.get("llm_fallback_order", ["claude"])),
            console=console,
        )
        parsed_fallbacks = parse_config_value(fallback_order)
        if isinstance(parsed_fallbacks, list) and all(isinstance(item, str) for item in parsed_fallbacks):
            cfg["llm_fallback_order"] = parsed_fallbacks
        else:
            console.print("  [yellow]Invalid fallback order, keeping current value.[/]")

        hour_str = Prompt.ask(
            "  [dim]Auto-compile after hour (0-23)[/]",
            default=str(cfg.get("compile_after_hour", 18)),
            console=console,
        )
        try:
            hour = int(hour_str)
            if 0 <= hour <= 23:
                cfg["compile_after_hour"] = hour
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
