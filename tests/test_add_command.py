from __future__ import annotations

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
                "memory_cli.cli.verify_claude_available"
            ), patch(
                "memory_cli.cli.subprocess.run"
            ) as mock_run:
                mock_run.return_value.returncode = 0

                result = self.runner.invoke(main, ["add", str(source)])

            self.assertEqual(result.exit_code, 0, result.output)
            imported = vault_dir / "resources" / "note.md"
            self.assertTrue(imported.exists())
            self.assertEqual(imported.read_text(encoding="utf-8"), "# Title\n")
            mock_run.assert_called_once_with(
                [
                    "uv",
                    "run",
                    "--directory",
                    str(compiler_dir),
                    "python",
                    str(compiler_dir / "scripts" / "compile.py"),
                    "--file",
                    "resources/note.md",
                ],
                text=True,
            )

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
                "memory_cli.cli.verify_claude_available",
                side_effect=click.ClickException("Claude is unavailable for compilation right now."),
                create=True,
            ):
                result = self.runner.invoke(main, ["add", str(source)])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Claude is unavailable", result.output)
            self.assertFalse((vault_dir / "resources" / "note.md").exists())


class MemorySyncCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_sync_stops_before_compile_when_claude_preflight_fails(self) -> None:
        with patch("memory_cli.cli.config_store.load", return_value={"sync": {"daily": True, "sources": True, "custom_dirs": []}}), patch(
            "memory_cli.cli.verify_claude_available",
            side_effect=click.ClickException("Claude is unavailable for compilation right now."),
            create=True,
        ), patch("memory_cli.cli.subprocess.run") as mock_run:
            result = self.runner.invoke(main, ["sync"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Claude is unavailable", result.output)
        mock_run.assert_not_called()

    def test_sync_dry_run_skips_claude_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiler_dir = Path(tmpdir) / "compiler"
            compiler_dir.mkdir(parents=True, exist_ok=True)

            with patch(
                "memory_cli.cli.config_store.load",
                return_value={"sync": {"daily": True, "sources": True, "custom_dirs": []}},
            ), patch("memory_cli.cli.get_compiler_dir", return_value=compiler_dir), patch(
                "memory_cli.cli.uv", return_value="uv"
            ), patch(
                "memory_cli.cli.verify_claude_available",
                side_effect=AssertionError("preflight should not run for dry-run"),
                create=True,
            ), patch("memory_cli.cli.subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0

                result = self.runner.invoke(main, ["sync", "--dry-run"])

        self.assertEqual(result.exit_code, 0, result.output)
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
