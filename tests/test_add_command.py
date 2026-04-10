from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import click
from click.testing import CliRunner

from memory_cli.cli import main


class MemoryAddCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_add_copies_markdown_and_compiles_only_that_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "note.md"
            source.write_text("# Title\n", encoding="utf-8")

            vault_dir = root / "vault"
            compiler_dir = root / "compiler"

            with patch("memory_cli.cli.get_vault_dir", return_value=vault_dir), patch(
                "memory_cli.cli.get_compiler_dir", return_value=compiler_dir
            ), patch("memory_cli.cli.uv", return_value="uv"), patch(
                "memory_cli.cli.resolve_available_provider"
            ) as mock_resolve_provider:
                provider = mock_resolve_provider.return_value
                provider.compile_one.return_value = 0

                result = self.runner.invoke(main, ["add", str(source)])

            self.assertEqual(result.exit_code, 0, result.output)
            imported = vault_dir / "resources" / "note.md"
            self.assertTrue(imported.exists())
            self.assertEqual(imported.read_text(encoding="utf-8"), "# Title\n")
            provider.compile_one.assert_called_once_with("resources/note.md")

    def test_add_rejects_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing.md"

            result = self.runner.invoke(main, ["add", str(missing)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("does not exist", result.output)

    def test_add_rejects_non_markdown_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "note.txt"
            source.write_text("hello\n", encoding="utf-8")

            result = self.runner.invoke(main, ["add", str(source)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn(".md", result.output)

    def test_add_rejects_existing_resource_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "note.md"
            source.write_text("# Incoming\n", encoding="utf-8")

            vault_dir = root / "vault"
            existing = vault_dir / "resources" / "note.md"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("# Existing\n", encoding="utf-8")

            with patch("memory_cli.cli.get_vault_dir", return_value=vault_dir):
                result = self.runner.invoke(main, ["add", str(source)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("already exists", result.output)

    def test_add_stops_before_copy_when_claude_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "note.md"
            source.write_text("# Title\n", encoding="utf-8")
            vault_dir = root / "vault"

            with patch("memory_cli.cli.get_vault_dir", return_value=vault_dir), patch(
                "memory_cli.cli.resolve_available_provider",
            ) as mock_resolve_provider:
                mock_resolve_provider.side_effect = click.ClickException(
                    "Claude is unavailable for compilation right now."
                )
                result = self.runner.invoke(main, ["add", str(source)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Claude is unavailable", result.output)
            self.assertFalse((vault_dir / "resources" / "note.md").exists())


class MemorySyncCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_sync_stops_before_compile_when_claude_preflight_fails(self) -> None:
        with patch("memory_cli.cli.config_store.load", return_value={"sync": {"daily": True, "sources": True, "custom_dirs": []}}), patch(
            "memory_cli.cli.resolve_available_provider",
        ) as mock_resolve_provider:
            mock_resolve_provider.side_effect = click.ClickException(
                "Claude is unavailable for compilation right now."
            )
            result = self.runner.invoke(main, ["sync"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Claude is unavailable", result.output)

    def test_sync_dry_run_skips_claude_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compiler_dir = root / "compiler"
            (compiler_dir / "scripts").mkdir(parents=True)
            vault_dir = root / "vault"
            daily_dir = vault_dir / "daily"
            resources_dir = vault_dir / "resources"
            daily_dir.mkdir(parents=True)
            resources_dir.mkdir(parents=True)
            (daily_dir / "session.md").write_text("# daily\n", encoding="utf-8")
            (resources_dir / "article.md").write_text("# source\n", encoding="utf-8")
            (compiler_dir / "scripts" / "state.json").write_text(
                json.dumps({"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}),
                encoding="utf-8",
            )

            with patch(
                "memory_cli.cli.config_store.load",
                return_value={"sync": {"daily": False, "sources": True, "custom_dirs": []}},
            ), patch("memory_cli.cli.get_provider_names", return_value=["claude"]), patch(
                "memory_cli.cli.make_provider"
            ) as mock_make_provider, patch(
                "memory_cli.cli.resolve_available_provider"
            ) as mock_resolve_provider, patch(
                "memory_cli.cli.get_compiler_dir", return_value=compiler_dir
            ), patch(
                "memory_cli.cli.get_vault_dir", return_value=vault_dir
            ):
                result = self.runner.invoke(main, ["sync", "--dry-run"])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_resolve_provider.assert_not_called()
        mock_make_provider.assert_called_once_with("claude")
        self.assertIn("Skipping (disabled in config): daily/", result.output)
        self.assertIn("article.md", result.output)
        self.assertNotIn("session.md", result.output)

    def test_sync_compiles_only_selected_filtered_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compiler_dir = root / "compiler"
            (compiler_dir / "scripts").mkdir(parents=True)
            vault_dir = root / "vault"
            daily_dir = vault_dir / "daily"
            resources_dir = vault_dir / "resources"
            daily_dir.mkdir(parents=True)
            resources_dir.mkdir(parents=True)
            (daily_dir / "session.md").write_text("# daily\n", encoding="utf-8")
            (resources_dir / "article.md").write_text("# source\n", encoding="utf-8")
            (compiler_dir / "scripts" / "state.json").write_text(
                json.dumps({"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}),
                encoding="utf-8",
            )

            with patch(
                "memory_cli.cli.config_store.load",
                return_value={"sync": {"daily": False, "sources": True, "custom_dirs": []}},
            ), patch(
                "memory_cli.cli.resolve_available_provider"
            ) as mock_resolve_provider, patch(
                "memory_cli.cli.get_compiler_dir", return_value=compiler_dir
            ), patch(
                "memory_cli.cli.get_vault_dir", return_value=vault_dir
            ):
                mock_resolve_provider.return_value.compile_one.return_value = 0

                result = self.runner.invoke(main, ["sync"])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_resolve_provider.return_value.compile_one.assert_called_once_with("resources/article.md")
        self.assertNotIn("session.md", result.output)

    def test_sync_warns_that_custom_dirs_are_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            compiler_dir = root / "compiler"
            (compiler_dir / "scripts").mkdir(parents=True)
            vault_dir = root / "vault"
            vault_dir.mkdir(parents=True)
            (compiler_dir / "scripts" / "state.json").write_text(
                json.dumps({"ingested": {}, "sources": {}, "query_count": 0, "last_lint": None, "total_cost": 0.0}),
                encoding="utf-8",
            )

            with patch(
                "memory_cli.cli.config_store.load",
                return_value={"sync": {"daily": False, "sources": False, "custom_dirs": ["/tmp/custom"]}},
            ), patch("memory_cli.cli.get_provider_names", return_value=["claude"]), patch(
                "memory_cli.cli.make_provider"
            ) as mock_make_provider, patch(
                "memory_cli.cli.get_compiler_dir", return_value=compiler_dir
            ), patch(
                "memory_cli.cli.get_vault_dir", return_value=vault_dir
            ):
                result = self.runner.invoke(main, ["sync", "--dry-run"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Custom sync dirs are not supported", result.output)
        mock_make_provider.assert_called_once_with("claude")


if __name__ == "__main__":
    unittest.main()
