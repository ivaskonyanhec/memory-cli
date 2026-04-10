# Provider Abstraction Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Introduce a local provider abstraction in `memory-cli` so the CLI routes compile, single-file compile, query, and availability checks through a selected provider while preserving current Claude-backed behavior.

**Architecture:** Move the current Claude-specific preflight, compile, and query delegation out of `memory_cli/cli.py` and behind provider modules in `memory_cli/providers/`. Keep the external `claude-memory-compiler` untouched; phase 1 only wraps existing Claude behavior and adds a stub OpenAI provider plus provider selection via config.

**Tech Stack:** Python 3.12, Click, pathlib, subprocess, unittest, unittest.mock

---

### Task 1: Add failing tests for provider selection and Claude routing

**Files:**
- Create: `tests/test_providers.py`
- Modify: `tests/test_add_command.py`
- Test: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
def test_get_provider_returns_claude_provider_by_default():
    ...

def test_sync_uses_selected_provider():
    ...

def test_add_uses_selected_provider_for_preflight_and_compile():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_providers -v`
Expected: FAIL because no provider package or provider lookup exists yet.

**Step 3: Write minimal implementation**

```python
def get_provider():
    return ClaudeProvider()
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_providers -v`
Expected: PASS for default provider lookup and routing.

**Step 5: Commit**

```bash
git add tests/test_providers.py tests/test_add_command.py memory_cli/cli.py memory_cli/providers
git commit -m "refactor: route cli commands through provider layer"
```

### Task 2: Add provider modules and preserve Claude behavior

**Files:**
- Create: `memory_cli/providers/__init__.py`
- Create: `memory_cli/providers/base.py`
- Create: `memory_cli/providers/claude.py`
- Modify: `memory_cli/cli.py`
- Test: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
def test_claude_provider_compile_uses_existing_compiler_script():
    ...

def test_claude_provider_query_uses_existing_query_script():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_providers -v`
Expected: FAIL because provider methods are missing or do not delegate correctly.

**Step 3: Write minimal implementation**

```python
class ClaudeProvider(Provider):
    def check_available(self) -> None: ...
    def compile(self, *, force_all: bool, target_file: str | None, dry_run: bool) -> int: ...
    def compile_one(self, target_file: str) -> int: ...
    def query(self, question: str, file_back: bool) -> int: ...
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_providers -v`
Expected: PASS with existing Claude behavior preserved.

**Step 5: Commit**

```bash
git add memory_cli/providers/__init__.py memory_cli/providers/base.py memory_cli/providers/claude.py memory_cli/cli.py tests/test_providers.py
git commit -m "refactor: extract claude provider"
```

### Task 3: Add config support for provider selection

**Files:**
- Modify: `memory_cli/config_store.py`
- Modify: `memory_cli/cli.py`
- Modify: `tests/test_providers.py`
- Test: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
def test_get_provider_uses_llm_provider_config():
    ...

def test_unknown_provider_raises_click_exception():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_providers -v`
Expected: FAIL because config does not yet contain `llm_provider` and provider selection is hard-coded.

**Step 3: Write minimal implementation**

```python
DEFAULTS["llm_provider"] = "claude"
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_providers -v`
Expected: PASS for config-driven provider selection.

**Step 5: Commit**

```bash
git add memory_cli/config_store.py memory_cli/cli.py tests/test_providers.py
git commit -m "feat: add provider selection config"
```

### Task 4: Add stub OpenAI provider

**Files:**
- Create: `memory_cli/providers/openai.py`
- Modify: `memory_cli/providers/__init__.py`
- Modify: `tests/test_providers.py`
- Test: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
def test_openai_provider_requires_api_key():
    ...

def test_openai_provider_compile_raises_not_implemented():
    ...
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_providers -v`
Expected: FAIL because no OpenAI provider exists.

**Step 3: Write minimal implementation**

```python
class OpenAIProvider(Provider):
    def check_available(self) -> None: ...
    def compile(self, *, force_all: bool, target_file: str | None, dry_run: bool) -> int:
        raise click.ClickException(...)
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_providers -v`
Expected: PASS with clean “not implemented yet” behavior.

**Step 5: Commit**

```bash
git add memory_cli/providers/openai.py memory_cli/providers/__init__.py tests/test_providers.py
git commit -m "feat: add openai provider stub"
```

### Task 5: Document provider selection

**Files:**
- Modify: `README.md`
- Modify: `memory_cli/config_store.py`
- Test: `tests/test_providers.py`

**Step 1: Write the failing test**

```python
# No new automated test; verify documentation after tests stay green.
```

**Step 2: Run test to verify current behavior**

Run: `python3 -m unittest tests.test_providers tests.test_add_command -v`
Expected: PASS before docs-only updates.

**Step 3: Write minimal implementation**

```markdown
`llm_provider` selects which backend `memory-cli` uses for compile and query flows.
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_providers tests.test_add_command -v`
Expected: PASS with updated docs.

**Step 5: Commit**

```bash
git add README.md memory_cli/config_store.py
git commit -m "docs: document provider selection"
```
