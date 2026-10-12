"""Unit tests for app/llm.py.

Verifies get_llm() returns a cached ChatOpenAI client built from settings, with
no network call at construction time.
"""

import unittest

from langchain_openai import ChatOpenAI

from app import llm as llmmod
from app.config import get_settings


class TestGetLlm(unittest.TestCase):
    def test_returns_cached_client(self):
        a = llmmod.get_llm()
        b = llmmod.get_llm()
        self.assertIsInstance(a, ChatOpenAI)
        self.assertIs(a, b)  # @lru_cache => same instance

    def test_model_from_settings_matches(self):
        # The client and the resolved settings must agree on the model string.
        client = llmmod.get_llm()
        s = get_settings()
        model = getattr(client, "model_name", None) or getattr(client, "model", None)
        self.assertEqual(model, s.model)


if __name__ == "__main__":
    unittest.main()
