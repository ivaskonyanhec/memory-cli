from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from memory_cli import config_store
from memory_cli.cli import main


class MemoryConfigCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_config_get_reads_value_from_single_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.json"

            with patch.object(config_store, "CONFIG_DIR", config_dir), patch.object(
                config_store, "CONFIG_FILE", config_file
            ):
                config_store.save(config_store.load() | {"llm_provider": "codex"})

                result = self.runner.invoke(main, ["config", "get", "llm_provider"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("codex", result.output)

    def test_config_set_updates_value_in_single_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.json"

            with patch.object(config_store, "CONFIG_DIR", config_dir), patch.object(
                config_store, "CONFIG_FILE", config_file
            ):
                result = self.runner.invoke(main, ["config", "set", "llm_provider", "codex"])
                saved = config_store.load()

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(saved["llm_provider"], "codex")

    def test_config_set_parses_json_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.json"

            with patch.object(config_store, "CONFIG_DIR", config_dir), patch.object(
                config_store, "CONFIG_FILE", config_file
            ):
                result = self.runner.invoke(
                    main,
                    ["config", "set", "llm_fallback_order", '["claude","codex"]'],
                )
                saved = config_store.load()

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(saved["llm_fallback_order"], ["claude", "codex"])

    def test_config_keys_lists_available_keys(self) -> None:
        result = self.runner.invoke(main, ["config", "keys"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("compiler_dir", result.output)
        self.assertIn("vault_dir", result.output)
        self.assertIn("llm_provider", result.output)
        self.assertIn("llm_fallback_order", result.output)
        self.assertIn("sync.daily", result.output)


if __name__ == "__main__":
    unittest.main()
