# Memory Add Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `memory add` CLI command that copies a Markdown file into the Obsidian vault's `resources/` folder and immediately compiles that imported file into the knowledge base.

**Architecture:** Extend the existing Click CLI in `memory_cli/cli.py` with a focused `add` command and a small helper for importing resource files. Keep compiler execution aligned with the current `memory sync` implementation by passing `--file resources/<basename>` to `scripts/compile.py`.

**Tech Stack:** Python 3.12, Click, Rich, unittest, pathlib, unittest.mock

---

### Task 1: Add failing tests for `memory add`

**Files:**
- Create: `tests/test_add_command.py`
- Modify: `pyproject.toml`
- Test: `tests/test_add_command.py`

**Step 1: Write the failing test**

```python
def test_add_copies_markdown_and_compiles_only_that_resource():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_add_command -v`
Expected: FAIL because `memory add` does not exist yet.

**Step 3: Write minimal implementation**

```python
@main.command()
def add(...):
    ...
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_add_command -v`
Expected: PASS for the new success-path test.

**Step 5: Commit**

```bash
git add tests/test_add_command.py pyproject.toml memory_cli/cli.py
git commit -m "feat: add memory add command"
```

### Task 2: Cover validation failures

**Files:**
- Modify: `tests/test_add_command.py`
- Modify: `memory_cli/cli.py`
- Test: `tests/test_add_command.py`

**Step 1: Write the failing test**

```python
def test_add_rejects_missing_files():
    ...

def test_add_rejects_non_markdown_files():
    ...

def test_add_rejects_existing_resource_name():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_add_command -v`
Expected: FAIL on validation cases not yet handled.

**Step 3: Write minimal implementation**

```python
if not source.exists():
    raise click.ClickException(...)
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_add_command -v`
Expected: PASS for success and failure-path tests.

**Step 5: Commit**

```bash
git add tests/test_add_command.py memory_cli/cli.py
git commit -m "test: cover memory add validation"
```

### Task 3: Document the new command

**Files:**
- Modify: `README.md`
- Modify: `memory_cli/cli.py`
- Test: `tests/test_add_command.py`

**Step 1: Write the failing test**

```python
# No new automated test; verify help text manually through CLI output.
```

**Step 2: Run test to verify current behavior**

Run: `python -m unittest tests.test_add_command -v`
Expected: PASS before docs-only updates.

**Step 3: Write minimal implementation**

```python
table.add_row("add", "Import a markdown resource and compile it", "")
```

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_add_command -v`
Expected: PASS with updated docs and help output.

**Step 5: Commit**

```bash
git add README.md memory_cli/cli.py
git commit -m "docs: add memory add usage"
```
