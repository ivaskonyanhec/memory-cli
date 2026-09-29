from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from memory_cli.cli import main


class MemoryLintFixCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_lint_fix_adds_missing_backlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "knowledge"
            concepts_dir = knowledge_dir / "concepts"
            concepts_dir.mkdir(parents=True)

            alpha = concepts_dir / "alpha.md"
            beta = concepts_dir / "beta.md"
            alpha.write_text("# Alpha\n\n## Related Concepts\n- [[concepts/beta]]\n", encoding="utf-8")
            beta.write_text("# Beta\n", encoding="utf-8")

            with patch("memory_cli.cli.get_knowledge_dir", return_value=knowledge_dir):
                result = self.runner.invoke(main, ["lint-fix"])

            self.assertEqual(result.exit_code, 0, result.output)
            updated = beta.read_text(encoding="utf-8")
            self.assertIn("[[concepts/alpha]]", updated)

    def test_lint_fix_dry_run_does_not_edit_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "knowledge"
            concepts_dir = knowledge_dir / "concepts"
            concepts_dir.mkdir(parents=True)

            alpha = concepts_dir / "alpha.md"
            beta = concepts_dir / "beta.md"
            alpha.write_text("# Alpha\n\n- [[concepts/beta]]\n", encoding="utf-8")
            original = "# Beta\n"
            beta.write_text(original, encoding="utf-8")

            with patch("memory_cli.cli.get_knowledge_dir", return_value=knowledge_dir):
                result = self.runner.invoke(main, ["lint-fix", "--dry-run"])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(beta.read_text(encoding="utf-8"), original)
            self.assertIn("Would update", result.output)

    def test_lint_fix_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "knowledge"
            concepts_dir = knowledge_dir / "concepts"
            concepts_dir.mkdir(parents=True)

            alpha = concepts_dir / "alpha.md"
            beta = concepts_dir / "beta.md"
            alpha.write_text("# Alpha\n\n- [[concepts/beta]]\n", encoding="utf-8")
            beta.write_text("# Beta\n\n## Related Concepts\n- [[concepts/alpha]]\n", encoding="utf-8")

            with patch("memory_cli.cli.get_knowledge_dir", return_value=knowledge_dir):
                result = self.runner.invoke(main, ["lint-fix"])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("No safe fixes", result.output)


if __name__ == "__main__":
    unittest.main()


class MemoryLintFixPlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def _run(self, beta_text: str, alpha_text: str = "# Alpha\n\n## Related Concepts\n\n- [[concepts/beta]]\n") -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_dir = Path(tmpdir) / "knowledge"
            concepts_dir = knowledge_dir / "concepts"
            concepts_dir.mkdir(parents=True)
            (concepts_dir / "alpha.md").write_text(alpha_text, encoding="utf-8")
            beta = concepts_dir / "beta.md"
            beta.write_text(beta_text, encoding="utf-8")

            with patch("memory_cli.cli.get_knowledge_dir", return_value=knowledge_dir):
                result = self.runner.invoke(main, ["lint-fix"])

            self.assertEqual(result.exit_code, 0, result.output)
            return beta.read_text(encoding="utf-8")

    def test_backlink_joins_list_after_blank_line_under_heading(self) -> None:
        updated = self._run("# Beta\n\n## Related Concepts\n\n- [[concepts/gamma]]\n\n## Sources\n\n- daily/x.md\n")

        self.assertIn("## Related Concepts\n\n- [[concepts/gamma]]\n- [[concepts/alpha]]\n\n## Sources", updated)

    def test_backlink_uses_short_related_heading(self) -> None:
        updated = self._run("# Beta\n\n## Related\n\n- [[concepts/gamma]]\n")

        self.assertIn("## Related\n\n- [[concepts/gamma]]\n- [[concepts/alpha]]\n", updated)
        self.assertNotIn("## Related Concepts", updated)

    def test_new_related_section_goes_before_sources(self) -> None:
        updated = self._run("# Beta\n\n## Sources\n\n- daily/x.md\n")

        self.assertIn("## Related Concepts\n\n- [[concepts/alpha]]\n\n## Sources", updated)

    def test_links_inside_code_are_not_backlinked(self) -> None:
        updated = self._run("# Beta\n", alpha_text="# Alpha\n\nUse `new Map([[concepts/beta]])` here.\n")

        self.assertNotIn("[[concepts/alpha]]", updated)
