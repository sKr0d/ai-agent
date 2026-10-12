"""Unit tests for app/orchestrator.py -- the subagents-as-tools supervisor.

`detect_agent` is a pure function over message lists and the routing table; the
orchestrator object itself is a compiled LangGraph. No LLM / network.
"""

import unittest

from app import orchestrator as orch
from app.orchestrator import SPECIALISTS, build_orchestrator, detect_agent, orchestrator


class _Msg:
    """Minimal stand-in for a LangChain message."""
    def __init__(self, tool_calls=None, name=None):
        self.tool_calls = tool_calls
        self.name = name


class TestRoutingTable(unittest.TestCase):
    def test_four_specialists(self):
        self.assertEqual(set(SPECIALISTS),
                         {"ask_coding", "ask_cicd", "ask_monitoring", "ask_improvement"})

    def test_maps_tools_to_agent_names(self):
        self.assertEqual(SPECIALISTS["ask_coding"], "coding")
        self.assertEqual(SPECIALISTS["ask_improvement"], "improvement")


class TestDetectAgentByToolCall(unittest.TestCase):
    def test_detects_coding(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=[{"name": "ask_coding"}])]),
                         "coding")

    def test_detects_cicd(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=[{"name": "ask_cicd"}])]),
                         "cicd")

    def test_detects_monitoring(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=[{"name": "ask_monitoring"}])]),
                         "monitoring")

    def test_detects_improvement(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=[{"name": "ask_improvement"}])]),
                         "improvement")


class TestDetectAgentFallback(unittest.TestCase):
    def test_falls_back_to_orchestrator(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=[], name="orchestrator")]),
                         "orchestrator")

    def test_detects_by_message_name(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=None, name="ask_cicd")]),
                         "cicd")

    def test_unknown_name_falls_back(self):
        self.assertEqual(detect_agent([_Msg(tool_calls=None, name="ask_unknown")]),
                         "orchestrator")


class TestOrchestratorObject(unittest.TestCase):
    def test_is_a_compiled_graph(self):
        self.assertTrue(hasattr(orchestrator, "invoke"))

    def test_builder_returns_graph(self):
        self.assertTrue(hasattr(build_orchestrator(), "invoke"))


if __name__ == "__main__":
    unittest.main()
