from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import click
from click.testing import CliRunner

from memory_cli.cli import get_provider_names, make_provider, main, resolve_available_provider
from memory_cli.providers.claude import ClaudeProvider
from memory_cli.providers.codex import CodexProvider


class ProviderSelectionTests(unittest.TestCase):
    def test_make_provider_returns_claude_provider_by_default(self) -> None:
        provider = make_provider("claude")

        self.assertEqual(provider.__class__.__name__, "ClaudeProvider")

    def test_make_provider_returns_codex_provider(self) -> None:
        provider = make_provider("codex")

        self.assertEqual(provider.__class__.__name__, "CodexProvider")

    def test_get_provider_names_returns_primary_when_no_fallback_order(self) -> None:
        with patch("memory_cli.cli.config_store.get", return_value="claude"):
            provider_names = get_provider_names()

        self.assertEqual(provider_names, ["claude"])

    def test_get_provider_names_includes_primary_then_unique_fallbacks(self) -> None:
        def get_value(key: str, default=None):
            values = {
                "llm_provider": "claude",
                "llm_fallback_order": ["codex", "claude", "ollama"],
            }
            return values.get(key, default)

        with patch("memory_cli.cli.config_store.get", side_effect=get_value):
            provider_names = get_provider_names()

        self.assertEqual(provider_names, ["claude", "codex", "ollama"])

    def test_unknown_provider_raises_click_exception(self) -> None:
        with self.assertRaises(click.ClickException) as context:
            make_provider("unknown-provider")

        self.assertIn("Unknown provider", str(context.exception))


class ProviderResolutionTests(unittest.TestCase):
    def test_resolve_available_provider_returns_primary_when_available(self) -> None:
        primary = Mock()
        fallback = Mock()

        with patch("memory_cli.cli.get_provider_names", return_value=["claude", "codex"]), patch(
            "memory_cli.cli.make_provider", side_effect=[primary, fallback]
        ):
            provider = resolve_available_provider()

        self.assertIs(provider, primary)
        primary.check_available.assert_called_once_with()
        fallback.check_available.assert_not_called()

    def test_resolve_available_provider_falls_back_on_availability_failure(self) -> None:
        primary = Mock()
        primary.check_available.side_effect = click.ClickException("primary unavailable")
        fallback = Mock()

        with patch("memory_cli.cli.get_provider_names", return_value=["claude", "codex"]), patch(
            "memory_cli.cli.make_provider", side_effect=[primary, fallback]
        ):
            provider = resolve_available_provider()

        self.assertIs(provider, fallback)
        primary.check_available.assert_called_once_with()
        fallback.check_available.assert_called_once_with()

    def test_resolve_available_provider_raises_when_none_are_available(self) -> None:
        primary = Mock()
        primary.check_available.side_effect = click.ClickException("primary unavailable")
        fallback = Mock()
        fallback.check_available.side_effect = click.ClickException("fallback unavailable")

        with patch("memory_cli.cli.get_provider_names", return_value=["claude", "codex"]), patch(
            "memory_cli.cli.make_provider", side_effect=[primary, fallback]
        ), self.assertRaises(click.ClickException) as context:
            resolve_available_provider()

        self.assertIn("No available providers", str(context.exception))


class ClaudeProviderTests(unittest.TestCase):
    def test_claude_provider_compile_uses_existing_compiler_script(self) -> None:
        run_script = Mock()
        run_script.return_value.returncode = 0
        provider = ClaudeProvider(
            compiler_dir_getter=Mock(),
            uv_getter=Mock(),
            run_script=run_script,
        )

        returncode = provider.compile(force_all=True, target_file="resources/note.md", dry_run=False)

        self.assertEqual(returncode, 0)
        run_script.assert_called_once_with("compile.py", "--all", "--file", "resources/note.md")

    def test_claude_provider_query_uses_existing_query_script(self) -> None:
        run_script = Mock()
        run_script.return_value.returncode = 0
        provider = ClaudeProvider(
            compiler_dir_getter=Mock(),
            uv_getter=Mock(),
            run_script=run_script,
        )

        returncode = provider.query("What is memory?", True)

        self.assertEqual(returncode, 0)
        run_script.assert_called_once_with("query.py", "What is memory?", "--file-back")


class CodexProviderTests(unittest.TestCase):
    def test_codex_provider_compile_one_updates_state_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compiler_dir = root / "compiler"
            vault_dir = root / "vault"
            daily_dir = vault_dir / "daily"
            resources_dir = vault_dir / "resources"
            knowledge_dir = vault_dir / "knowledge"
            (compiler_dir / "scripts").mkdir(parents=True)
            (knowledge_dir / "concepts").mkdir(parents=True)
            daily_dir.mkdir(parents=True)
            resources_dir.mkdir(parents=True)

            source = resources_dir / "note.md"
            source.write_text("# Source\n", encoding="utf-8")
            (compiler_dir / "AGENTS.md").write_text("# schema\n", encoding="utf-8")
            (knowledge_dir / "index.md").write_text("# Index\n", encoding="utf-8")
            (compiler_dir / "scripts" / "state.json").write_text(
                '{"ingested": {}, "sources": {}, "query_count": 0, "last_lint": null, "total_cost": 0.0}',
                encoding="utf-8",
            )

            def fake_run(*args, **kwargs):
                (knowledge_dir / "concepts" / "compiled.md").write_text("done\n", encoding="utf-8")
                return Mock(returncode=0, stdout="OK\n", stderr="")

            provider = CodexProvider(
                compiler_dir_getter=lambda: compiler_dir,
                vault_dir_getter=lambda: vault_dir,
                daily_dir_getter=lambda: daily_dir,
                resources_dir_getter=lambda: resources_dir,
                knowledge_dir_getter=lambda: knowledge_dir,
            )

            with patch("memory_cli.providers.codex.shutil.which", return_value="/usr/local/bin/codex"), patch(
                "memory_cli.providers.codex.subprocess.run", side_effect=fake_run
            ) as mock_run:
                returncode = provider.compile_one("resources/note.md")

            self.assertEqual(returncode, 0)
            self.assertTrue((knowledge_dir / "concepts" / "compiled.md").exists())
            state = json.loads((compiler_dir / "scripts" / "state.json").read_text(encoding="utf-8"))
            self.assertIn("note.md", state["sources"])
            self.assertEqual(mock_run.call_count, 1)

    def test_codex_provider_compile_requires_targeted_flow(self) -> None:
        provider = CodexProvider(
            compiler_dir_getter=Mock(),
            vault_dir_getter=Mock(),
            daily_dir_getter=Mock(),
            resources_dir_getter=Mock(),
            knowledge_dir_getter=Mock(),
        )

        with self.assertRaises(click.ClickException) as context:
            provider.compile(force_all=False, target_file=None, dry_run=False)

        self.assertIn("compile_one", str(context.exception))


class ProviderRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_sync_uses_selected_provider(self) -> None:
        provider = Mock()
        provider.compile_one.return_value = 0

        with patch(
            "memory_cli.cli.config_store.load",
            return_value={"sync": {"daily": True, "sources": True, "custom_dirs": []}},
        ), patch("memory_cli.cli.resolve_available_provider", return_value=provider), patch(
            "memory_cli.cli.list_sync_targets", return_value=(["resources/note.md"], [])
        ):
            result = self.runner.invoke(main, ["sync"])

        self.assertEqual(result.exit_code, 0, result.output)
        provider.compile_one.assert_called_once_with("resources/note.md")

    def test_add_uses_selected_provider_for_preflight_and_compile(self) -> None:
        provider = Mock()
        provider.compile_one.return_value = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "note.md"
            source.write_text("# Title\n", encoding="utf-8")
            vault_dir = root / "vault"

            with patch("memory_cli.cli.get_vault_dir", return_value=vault_dir), patch(
                "memory_cli.cli.resolve_available_provider", return_value=provider
            ):
                result = self.runner.invoke(main, ["add", str(source)])

        self.assertEqual(result.exit_code, 0, result.output)
        provider.compile_one.assert_called_once_with("resources/note.md")


if __name__ == "__main__":
    unittest.main()
