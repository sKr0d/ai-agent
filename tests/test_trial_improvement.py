"""Tests for trial/agents/improvement.py.

The improvement agent is deliberate pure reasoning: it declares NO tools. A live
run needs the LLM, so this is a structural smoke test -- assert the module
imports, the agent builds, and `run` is callable.
"""

import unittest

import trial.agents.improvement as timpl


class TestImprovementModule(unittest.TestCase):
    def test_run_callable(self):
        self.assertTrue(callable(timpl.run))

    def test_agent_builds(self):
        self.assertTrue(hasattr(timpl, "AGENT"))
        self.assertTrue(hasattr(timpl.AGENT, "invoke"))

    def test_has_no_tools(self):
        # create_agent(...) was built with tools=[] on purpose, so nothing in the
        # module namespace should be a registered langchain tool.
        from langchain_core.tools import StructuredTool, Tool
        built_tools = [getattr(timpl, n) for n in dir(timpl)
                      if isinstance(getattr(timpl, n), (StructuredTool, Tool))]
        self.assertEqual(built_tools, [])


if __name__ == "__main__":
    unittest.main()
