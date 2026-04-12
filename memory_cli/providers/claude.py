from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import click

_CLAUDE_SESSION_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH")


def _clean_env() -> dict:
    """Return a copy of the current environment with Claude Code session markers stripped.

    The bundled `claude` CLI exits with code 1 when it detects a nested session
    via CLAUDECODE=1. Always pass this env to any subprocess that spawns claude.
    """
    env = os.environ.copy()
    for var in _CLAUDE_SESSION_VARS:
        env.pop(var, None)
    return env


class ClaudeProvider:
    def __init__(self, *, compiler_dir_getter, uv_getter, run_script):
        self._get_compiler_dir = compiler_dir_getter
        self._uv = uv_getter
        self._run_script = run_script

    def _find_claude(self) -> str:
        if cli := shutil.which("claude"):
            return cli
        for candidate in [
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        ]:
            if candidate.exists():
                return str(candidate)
        raise click.ClickException("Claude CLI not found. Install Claude Code and ensure `claude` is on PATH.")

    def check_available(self) -> None:
        cmd = [
            self._find_claude(),
            "-p",
            "Reply with exactly OK.",
            "--verbose",
            "--allowedTools",
            "Read",
            "--max-turns",
            "1",
            "--output-format",
            "stream-json",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self._get_compiler_dir()),
                env=_clean_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                "Claude is unavailable for compilation right now. The availability check timed out."
            ) from exc
        except OSError as exc:
            raise click.ClickException(
                "Claude is unavailable for compilation right now. Failed to run the Claude CLI."
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            raise click.ClickException(
                f"Claude is unavailable for compilation right now.{suffix}"
            )

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                return

        raise click.ClickException(
            "Claude is unavailable for compilation right now. The availability check did not complete successfully."
        )

    def compile(self, *, force_all: bool, target_file: str | None, dry_run: bool) -> int:
        args: list[str] = []
        if force_all:
            args.append("--all")
        if target_file:
            args.extend(["--file", target_file])
        if dry_run:
            args.append("--dry-run")
        result = self._run_script("compile.py", *args)
        return result.returncode

    def compile_one(self, target_file: str) -> int:
        return self.compile(force_all=False, target_file=target_file, dry_run=False)

    def query(self, question: str, file_back: bool) -> int:
        args = [question] + (["--file-back"] if file_back else [])
        result = self._run_script("query.py", *args)
        return result.returncode
