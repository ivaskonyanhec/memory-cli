from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click


class CodexProvider:
    def __init__(
        self,
        *,
        compiler_dir_getter,
        vault_dir_getter,
        daily_dir_getter,
        resources_dir_getter,
        knowledge_dir_getter,
    ):
        self._get_compiler_dir = compiler_dir_getter
        self._get_vault_dir = vault_dir_getter
        self._get_daily_dir = daily_dir_getter
        self._get_resources_dir = resources_dir_getter
        self._get_knowledge_dir = knowledge_dir_getter

    def _find_codex(self) -> str:
        if cli := shutil.which("codex"):
            return cli
        for candidate in [
            Path.home() / ".local" / "bin" / "codex",
            Path.home() / ".nvm" / "versions" / "node" / "v22.17.0" / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path("/opt/homebrew/bin/codex"),
        ]:
            if candidate.exists():
                return str(candidate)
        raise click.ClickException("Codex CLI not found. Install Codex and ensure `codex` is on PATH.")

    def check_available(self) -> None:
        cmd = [
            self._find_codex(),
            "exec",
            "--skip-git-repo-check",
            "Reply with exactly OK.",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                "Codex is unavailable for compilation right now. The availability check timed out."
            ) from exc
        except OSError as exc:
            raise click.ClickException(
                "Codex is unavailable for compilation right now. Failed to run the Codex CLI."
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            raise click.ClickException(f"Codex is unavailable for compilation right now.{suffix}")

        output = (result.stdout or "").strip()
        if not output or "OK" not in output:
            detail = output.splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            raise click.ClickException(
                f"Codex is unavailable for compilation right now. The availability check returned an unexpected response.{suffix}"
            )

    def compile(self, *, force_all: bool, target_file: str | None, dry_run: bool) -> int:
        if dry_run or target_file is None:
            raise click.ClickException("Codex provider expects compile_one() for targeted compile flow.")
        return self.compile_one(target_file)

    def compile_one(self, target_file: str) -> int:
        source_path, state_bucket, state_key = self._resolve_target(target_file)
        compiler_dir = self._get_compiler_dir()
        knowledge_dir = self._get_knowledge_dir()
        before = self._snapshot_knowledge(knowledge_dir)

        prompt = self._build_prompt(target_file, source_path)
        cmd = [
            self._find_codex(),
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "-C",
            str(compiler_dir),
            "--add-dir",
            str(self._get_vault_dir()),
            prompt,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                f"Codex timed out while compiling {target_file}."
            ) from exc
        except OSError as exc:
            raise click.ClickException(
                "Failed to run Codex for compilation."
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            raise click.ClickException(f"Codex compilation failed for {target_file}.{suffix}")

        after = self._snapshot_knowledge(knowledge_dir)
        if before == after:
            raise click.ClickException(
                f"Codex did not produce any knowledge updates for {target_file}."
            )

        self._update_state(state_bucket, state_key, source_path)
        return 0

    def query(self, question: str, file_back: bool) -> int:
        compiler_dir = self._get_compiler_dir()
        knowledge_dir = self._get_knowledge_dir()
        qa_dir = knowledge_dir / "qa"
        before = self._snapshot_knowledge(knowledge_dir) if file_back else {}

        prompt = self._build_query_prompt(question, file_back)
        cmd = [
            self._find_codex(),
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "-C",
            str(compiler_dir),
            "--add-dir",
            str(self._get_vault_dir()),
            prompt,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise click.ClickException(
                "Codex timed out while querying the knowledge base."
            ) from exc
        except OSError as exc:
            raise click.ClickException(
                "Failed to run Codex for querying."
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f" {detail[-1]}" if detail else ""
            raise click.ClickException(f"Codex query failed.{suffix}")

        answer = (result.stdout or "").strip()
        if answer:
            print(answer)

        if file_back:
            after = self._snapshot_knowledge(knowledge_dir)
            if before == after or not qa_dir.exists():
                raise click.ClickException(
                    "Codex did not file the query answer back into the knowledge base."
                )

        self._update_query_state()
        return 0

    def _resolve_target(self, target_file: str) -> tuple[Path, str, str]:
        target = Path(target_file)
        if target.parts[:1] == ("daily",):
            path = self._get_daily_dir() / target.name
            return path, "ingested", target.name
        if target.parts[:1] == ("resources",):
            path = self._get_resources_dir() / target.name
            return path, "sources", target.name
        raise click.ClickException(f"Unsupported Codex compile target: {target_file}")

    def _build_prompt(self, target_file: str, source_path: Path) -> str:
        compiler_dir = self._get_compiler_dir()
        schema = (compiler_dir / "AGENTS.md").read_text(encoding="utf-8")
        wiki_index = self._read_index()
        existing_articles = self._existing_articles_context()
        timestamp = self._now_iso()
        content = source_path.read_text(encoding="utf-8")
        knowledge_dir = self._get_knowledge_dir()
        concepts_dir = knowledge_dir / "concepts"
        connections_dir = knowledge_dir / "connections"

        if target_file.startswith("daily/"):
            return f"""You are a knowledge compiler. Your job is to read a daily conversation log
and extract knowledge into structured wiki articles.

## Schema (AGENTS.md)

{schema}

## Current Wiki Index

{wiki_index}

## Existing Wiki Articles

{existing_articles if existing_articles else "(No existing articles yet)"}

## Daily Log to Compile

**File:** {source_path.name}

{content}

## Your Task

Read the daily log above and compile it into wiki articles following the schema exactly.

### Rules:

1. Extract 3-7 distinct concepts worth their own article
2. Create concept articles in `{concepts_dir}`
3. Create connection articles in `{connections_dir}` when the log reveals non-obvious relationships
4. Update existing articles when the log adds new information
5. Update `{knowledge_dir / 'index.md'}`
6. Append a compile entry to `{knowledge_dir / 'log.md'}`

### Required source references:
- Use `daily/{source_path.name}` in article/log source references
- Keep encyclopedia style and preserve wikilinks
"""

        return f"""You are a knowledge compiler. Your job is to read a clipped web article or reference
document and extract knowledge into structured wiki articles.

## Schema (AGENTS.md)

{schema}

## Current Wiki Index

{wiki_index}

## Existing Wiki Articles

{existing_articles if existing_articles else "(No existing articles yet)"}

## Clipped Source to Compile

**File:** {source_path.name}

{content}

## Your Task

Read the clipped source above and compile it into wiki articles following the schema exactly.

### Rules:

1. Extract 3-7 distinct concepts, frameworks, or ideas worth their own article
2. Create concept articles in `{concepts_dir}`
3. Create connection articles in `{connections_dir}` when the source reveals non-obvious relationships
4. Update existing articles when this source adds new information or a different perspective
5. Update `{knowledge_dir / 'index.md'}`
6. Append a compile entry to `{knowledge_dir / 'log.md'}`

### Required source references:
- Use `sources/{source_path.name}` in article/log source references
- Treat this as an external reference, not a conversation log
"""

    def _existing_articles_context(self) -> str:
        knowledge_dir = self._get_knowledge_dir()
        parts: list[str] = []
        for subdir in ["concepts", "connections", "qa"]:
            directory = knowledge_dir / subdir
            if not directory.exists():
                continue
            for article_path in sorted(directory.glob("*.md")):
                rel = article_path.relative_to(knowledge_dir)
                content = article_path.read_text(encoding="utf-8")
                parts.append(f"### {rel}\n```markdown\n{content}\n```")
        return "\n\n".join(parts)

    def _read_all_wiki_content(self) -> str:
        knowledge_dir = self._get_knowledge_dir()
        parts = [f"## INDEX\n\n{self._read_index()}"]
        for subdir in ["concepts", "connections", "qa"]:
            directory = knowledge_dir / subdir
            if not directory.exists():
                continue
            for md_file in sorted(directory.glob("*.md")):
                rel = md_file.relative_to(knowledge_dir)
                content = md_file.read_text(encoding="utf-8")
                parts.append(f"## {rel}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    def _build_query_prompt(self, question: str, file_back: bool) -> str:
        knowledge_dir = self._get_knowledge_dir()
        qa_dir = knowledge_dir / "qa"
        wiki_content = self._read_all_wiki_content()
        file_back_instructions = ""
        if file_back:
            timestamp = self._now_iso()
            file_back_instructions = f"""

## File Back Instructions

After answering, do the following:
1. Create a Q&A article at {qa_dir}/ with the filename being a slugified version of the question
2. Update {knowledge_dir / 'index.md'} with a new row for this Q&A article
3. Append to {knowledge_dir / 'log.md'}:
   ## [{timestamp}] query (filed) | question summary
   - Question: {question}
   - Consulted: [[list of articles read]]
   - Filed to: [[qa/article-name]]
"""

        return f"""You are a knowledge base query engine. Answer the user's question by
consulting the knowledge base below.

## How to Answer

1. Read the INDEX section first
2. Identify 3-10 articles that are relevant to the question
3. Read those articles carefully
4. Synthesize a clear, thorough answer
5. Cite your sources using [[wikilinks]]
6. If the knowledge base does not contain relevant information, say so honestly

## Knowledge Base

{wiki_content}

## Question

{question}
{file_back_instructions}
"""

    def _read_index(self) -> str:
        index_path = self._get_knowledge_dir() / "index.md"
        if index_path.exists():
            return index_path.read_text(encoding="utf-8")
        return "# Knowledge Base Index\n\n| Article | Summary | Compiled From | Updated |\n|---------|---------|---------------|---------|"

    def _snapshot_knowledge(self, knowledge_dir: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in sorted(knowledge_dir.rglob("*.md")):
            rel = path.relative_to(knowledge_dir)
            snapshot[str(rel)] = self._file_hash(path)
        return snapshot

    def _update_state(self, bucket: str, key: str, source_path: Path) -> None:
        state_path = self._get_compiler_dir() / "scripts" / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}

        state.setdefault(bucket, {})[key] = {
            "hash": self._file_hash(source_path),
            "compiled_at": self._now_iso(),
            "cost_usd": 0.0,
        }
        state["total_cost"] = state.get("total_cost", 0.0)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _update_query_state(self) -> None:
        state_path = self._get_compiler_dir() / "scripts" / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}

        state["query_count"] = state.get("query_count", 0) + 1
        state["total_cost"] = state.get("total_cost", 0.0)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _file_hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
