"""Unit tests for app/config.py.

Locks the configuration layering the whole service relies on:
env vars > config/settings.yaml > code defaults. No network.
"""

import contextlib
import os
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from app.config import Settings, load_yaml, get_settings


@contextlib.contextmanager
def _no_llm_env():
    """Temporarily remove every LLM_* / LOG_LEVEL env var and restore it."""
    keys = ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "LLM_TEMPERATURE",
            "LOG_LEVEL")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class TestLoadYaml(unittest.TestCase):
    def test_returns_dict(self):
        self.assertIsInstance(load_yaml(), dict)

    def test_missing_file_returns_empty(self):
        bogus = Path("/nonexistent-xyz/settings.yaml")
        with patch("app.config._CONFIG_PATH", bogus):
            self.assertEqual(load_yaml(), {})


class TestSettingsFromYamlAndDefaults(unittest.TestCase):
    """With no env vars present, values come from config/settings.yaml."""

    def test_yaml_defaults_win(self):
        with _no_llm_env():
            s = Settings.load()
        self.assertEqual(s.model, "qwen3.8:27b")
        self.assertEqual(s.base_url, "http://127.0.0.1:11434/v1")
        self.assertEqual(s.log_level, "info")
        self.assertEqual(s.temperature, 0)

    def test_code_defaults_when_no_yaml_no_env(self):
        with _no_llm_env(), patch("app.config._CONFIG_PATH",
                                  Path("/nonexistent-xyz/settings.yaml")):
            s = Settings.load()
        # fall back to the dataclass field defaults
        self.assertEqual(s.model, "qwen3.8:27b")
        self.assertEqual(s.api_key, "ollama")


class TestEnvOverridesYaml(unittest.TestCase):
    """Env vars must take precedence over the YAML file."""

    def test_model_override(self):
        with patch.dict(os.environ, {"LLM_MODEL": "some-other-model"}):
            self.assertEqual(Settings.load().model, "some-other-model")

    def test_base_url_override(self):
        with patch.dict(os.environ, {"LLM_BASE_URL": "http://ollama:11434/v1"}):
            self.assertEqual(Settings.load().base_url, "http://ollama:11434/v1")

    def test_temperature_parse(self):
        with patch.dict(os.environ, {"LLM_TEMPERATURE": "0.75"}):
            self.assertAlmostEqual(Settings.load().temperature, 0.75, places=6)

    def test_temperature_invalid_keeps_previous(self):
        with patch.dict(os.environ, {"LLM_TEMPERATURE": "not-a-float"}):
            self.assertEqual(Settings.load().temperature, 0)  # yaml value retained


class TestGetSettingsCaching(unittest.TestCase):
    def test_returns_cached_singleton(self):
        import app.config
        app.config._settings = None  # force a fresh resolve
        a = get_settings()
        b = get_settings()
        self.assertIs(a, b)
        app.config._settings = None  # be a good citizen for later tests


if __name__ == "__main__":
    unittest.main()
