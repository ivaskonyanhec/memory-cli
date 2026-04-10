from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from memory_cli.cli import main


class MemoryLintCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_lint_retries_structural_only_after_llm_failure(self) -> None:
        full = SimpleNamespace(
            returncode=1,
            stdout="Running knowledge base lint checks...\n  Checking: Contradictions (LLM)...\n",
            stderr="Traceback...\ncheck_contradictions\nKeyboardInterrupt\n",
        )
        structural = SimpleNamespace(
            returncode=0,
            stdout="Running knowledge base lint checks...\n  Skipping: Contradictions (--structural-only)\n",
            stderr="",
        )

        with patch("memory_cli.cli.run_script", side_effect=[full, structural]) as mock_run:
            result = self.runner.invoke(main, ["lint"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("retrying structural lint only", result.output)
        self.assertEqual(mock_run.call_args_list[0].args, ("lint.py",))
        self.assertEqual(mock_run.call_args_list[1].args, ("lint.py", "--structural-only"))

    def test_lint_does_not_retry_for_normal_lint_errors(self) -> None:
        failed = SimpleNamespace(
            returncode=1,
            stdout="Results: 1 errors, 0 warnings, 0 suggestions\n",
            stderr="",
        )

        with patch("memory_cli.cli.run_script", return_value=failed) as mock_run:
            result = self.runner.invoke(main, ["lint"])

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertNotIn("retrying structural lint only", result.output)
        mock_run.assert_called_once_with("lint.py", capture_output=True)


if __name__ == "__main__":
    unittest.main()
