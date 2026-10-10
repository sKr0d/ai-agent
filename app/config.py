"""Configuration: YAML defaults, with environment variables layered on top.

Priority (highest first): environment variables > config/settings.yaml > code
defaults. This mirrors how a service gets configured in Kubernetes, where env
vars/Secrets override baked-in defaults.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATH = _ROOT / "config" / "settings.yaml"


def _env(name: str, default=None):
    """Read an env var, falling back to `default` (env not read = original value)."""
    return os.environ.get(name, default)


def load_yaml() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Settings:
    model: str = "qwen3.8:27b"
    base_url: str = "http://127.0.0.1:11434/v1"  # host's Ollama
    api_key: str = "ollama"
    temperature: float = 0.0
    log_level: str = "info"

    @classmethod
    def load(cls) -> "Settings":
        raw = load_yaml()
        s = cls()

        # 1) YAML defaults (section -> fields with the same name)
        for key, value in (raw.get("llm") or {}).items():
            if key in cls.__dataclass_fields__:
                setattr(s, key, value)
        if (raw.get("logging") or {}).get("level"):
            s.log_level = str(raw["logging"]["level"]).lower()

        # 2) environment variables override YAML
        s.model = _env("LLM_MODEL", s.model)
        s.base_url = _env("LLM_BASE_URL", s.base_url)
        s.api_key = _env("LLM_API_KEY", s.api_key)
        if _env("LLM_TEMPERATURE") is not None:
            try:
                s.temperature = float(_env("LLM_TEMPERATURE"))
            except ValueError:
                pass
        s.log_level = str(_env("LOG_LEVEL", s.log_level)).lower()
        return s


_settings: "Settings | None" = None


def get_settings() -> Settings:
    """Cached settings, resolved once (like a Spring/FastAPI `Settings` singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings.load()
    return _settings
