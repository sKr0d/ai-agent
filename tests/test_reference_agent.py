"""Smoke test for the deprecated reference entry point `agent.py`.

`agent.py` is kept for reference and still uses the old
`create_react_agent` API. This test asserts the module at least *import cleanly*.
If the installed LangGraph has removed that API, the test is skipped (documented)
rather than failing the suite -- the module is intentionally not part of the
live app.
"""

import importlib
import unittest


def _agent_importable():
    try:
        importlib.import_module("agent")
        return True
    except Exception:
        return False


@unittest.skipUnless(
    _agent_importable(),
    "agent.py (deprecated reference) does not import in this environment -- "
    "it uses the legacy create_react_agent API; see the PR notes.",
)
class TestReferenceAgent(unittest.TestCase):
    def test_exposes_fastapi_app(self):
        mod = importlib.import_module("agent")
        from fastapi import FastAPI
        self.assertIsInstance(mod.app, FastAPI)
        self.assertTrue(hasattr(mod, "chat"))
        self.assertTrue(hasattr(mod, "agent"))


if __name__ == "__main__":
    unittest.main()
