"""
Persistent config for memory-cli.

Stored at ~/.memory-cli/config.json — separate from the compiler's config.py
so the CLI can be independently configured without touching compiler internals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".memory-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "compiler_dir": str(Path.home() / "projects" / "ai" / "claude-memory-compiler"),
    "vault_dir": str(Path.home() / "My Documents" / "LLM-Brain-General"),
    "daily_dirname": "daily",
    "resources_dirname": "resources",
    "knowledge_dirname": "knowledge",
    "llm_provider": "claude",
    "llm_fallback_order": ["claude"],
    "sync": {
        "daily": True,
        "sources": True,        # maps to the vault's resources/ folder
        "custom_dirs": [],       # list of extra absolute paths to compile
    },
    "compile_after_hour": 18,    # hour (0-23) after which auto-compile fires
    "log_lines": 30,             # default for `memory log`
    "show_cost": True,           # show/hide cost in `memory status`
}


def load() -> dict[str, Any]:
    """Load config, merging with defaults for any missing keys."""
    if not CONFIG_FILE.exists():
        return _deep_copy(DEFAULTS)

    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _deep_copy(DEFAULTS)

    return _deep_merge(DEFAULTS, saved)


def save(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get(key: str, default: Any = None) -> Any:
    """Get a top-level or dot-notation key (e.g. 'sync.daily')."""
    cfg = load()
    parts = key.split(".")
    val = cfg
    for part in parts:
        if not isinstance(val, dict) or part not in val:
            return default
        val = val[part]
    return val


def set_key(key: str, value: Any) -> None:
    """Set a top-level or dot-notation key and persist."""
    cfg = load()
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
    save(cfg)


def list_keys() -> list[str]:
    """List all configurable keys using dot notation."""
    return _list_keys(DEFAULTS)


def _deep_copy(d: dict) -> dict:
    return json.loads(json.dumps(d))


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = _deep_copy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _list_keys(value: Any, prefix: str = "") -> list[str]:
    if not isinstance(value, dict):
        return [prefix] if prefix else []

    keys: list[str] = []
    for key, nested in value.items():
        dotted = f"{prefix}.{key}" if prefix else key
        if isinstance(nested, dict):
            keys.extend(_list_keys(nested, dotted))
        else:
            keys.append(dotted)
    return keys
