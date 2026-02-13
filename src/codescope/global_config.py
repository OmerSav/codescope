"""Global configuration — persisted at ~/.codescope/config.json.

Stores user-wide settings like embedding provider, model, and API keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

GLOBAL_CONFIG_DIR = Path.home() / ".codescope"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"

# Valid config keys and their descriptions
VALID_KEYS: dict[str, str] = {
    "embedding_provider": "Embedding provider: 'local' or 'openai'",
    "embedding_model": "Embedding model name (e.g. 'all-MiniLM-L6-v2', 'text-embedding-3-small')",
    "openai_api_key": "OpenAI API key (required for openai provider)",
}

# Keys that should be masked when displayed
SENSITIVE_KEYS: set[str] = {"openai_api_key"}


def load_global_config() -> dict[str, Any]:
    """Load the global config from disk. Returns empty dict if not found."""
    if not GLOBAL_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(GLOBAL_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_global_config(data: dict[str, Any]) -> None:
    """Write the global config to disk."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )



def set_config_value(key: str, value: str) -> None:
    """Set a single value in the global config."""
    data = load_global_config()
    data[key] = value
    save_global_config(data)


def mask_value(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if key in SENSITIVE_KEYS and value and len(value) > 8:
        return value[:4] + "..." + value[-4:]
    return value
