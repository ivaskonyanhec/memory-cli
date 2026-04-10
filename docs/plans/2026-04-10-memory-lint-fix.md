# Memory Lint-Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `memory lint-fix` command that repairs safe structural issues in the knowledge base, starting with missing backlinks.

**Architecture:** Implement a local structural fixer in `memory-cli` that scans knowledge articles, detects asymmetric links, and patches target markdown files directly. Keep `memory lint` unchanged and do not modify the external compiler.

**Tech Stack:** Python 3.12, Click, pathlib, unittest

---

### Task 1: Add failing tests for backlink repair

**Files:**
- Create: `tests/test_lint_fix_command.py`
- Test: `tests/test_lint_fix_command.py`

**Step 1: Write the failing test**

```python
def test_lint_fix_adds_missing_backlink():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: FAIL because `memory lint-fix` does not exist yet.

**Step 3: Write minimal implementation**

```python
@main.command("lint-fix")
def lint_fix(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: PASS for the first backlink repair case.

**Step 5: Commit**

```bash
git add tests/test_lint_fix_command.py memory_cli/cli.py
git commit -m "feat: add lint fix command"
```

### Task 2: Add dry-run and idempotence coverage

**Files:**
- Modify: `tests/test_lint_fix_command.py`
- Modify: `memory_cli/cli.py`
- Test: `tests/test_lint_fix_command.py`

**Step 1: Write the failing test**

```python
def test_lint_fix_dry_run_does_not_edit_files():
    ...

def test_lint_fix_is_idempotent():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: FAIL because dry-run and no-op behavior are not fully implemented.

**Step 3: Write minimal implementation**

```python
if dry_run:
    ...
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: PASS for repair, dry-run, and idempotence.

**Step 5: Commit**

```bash
git add tests/test_lint_fix_command.py memory_cli/cli.py
git commit -m "test: cover lint fix dry-run and idempotence"
```

### Task 3: Document the new command

**Files:**
- Modify: `README.md`
- Test: `tests/test_lint_fix_command.py`

**Step 1: Write the failing test**

```python
# No new automated test; verify docs after tests remain green.
```

**Step 2: Run test to verify current behavior**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: PASS before docs update.

**Step 3: Write minimal implementation**

```markdown
memory lint-fix
memory lint-fix --dry-run
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_lint_fix_command -v`
Expected: PASS with docs updated.

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add lint fix command"
```
