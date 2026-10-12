"""Unit tests for app/server.py -- the FastAPI surface.

All handlers are exercised WITHOUT a live LLM: the LLM probe (`_llm_reachable`)
and the orchestrator are mocked. No network.
"""

import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException

from app import observability as obs
from app import server
from app.server import ChatRequest, health, ready, root, runs


class TestHealth(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(health(), {"status": "ok"})


class TestRoot(unittest.TestCase):
    def test_lists_endpoints(self):
        out = root()
        self.assertEqual(out["service"], "multi-dev-agent")
        for e in ("/health", "/ready", "/chat", "/runs"):
            self.assertIn(e, out["endpoints"])


class TestRuns(unittest.TestCase):
    def setUp(self):
        obs._runs.clear()

    def tearDown(self):
        obs._runs.clear()

    def test_empty_by_default(self):
        self.assertEqual(runs(10)["runs"], [])

    def test_shows_bounded_recent(self):
        for i in range(5):
            obs.record_run(f"t{i}", "coding" if i % 2 else "cicd", "ok", i)
        out = runs(3)
        self.assertEqual(len(out["runs"]), 3)
        self.assertEqual(out["runs"][-1]["thread_id"], "t4")


class _Msg:
    def __init__(self, content):
        self.content = content


class TestReady(unittest.TestCase):
    """/ready is the k8s readiness probe: 200 when LLM reachable, 503 when not."""

    def _run(self, reachable):
        async def probe():
            return reachable
        with mock.patch.object(server, "_llm_reachable", probe):
            return asyncio.run(ready())

    def test_200_when_reachable(self):
        self.assertEqual(self._run(True), {"status": "ok", "llm_reachable": True})

    def test_503_when_llm_down(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run(False)
        self.assertEqual(ctx.exception.status_code, 503)


class TestChat(unittest.TestCase):
    """/chat routes through the (mocked) orchestrator; errors => 500 + run log."""

    def setUp(self):
        obs._runs.clear()

    def tearDown(self):
        obs._runs.clear()

    def test_happy_path(self):
        async def ainvoke(payload, config=None):
            return {"messages": [_Msg("hi there")]}

        fake = mock.Mock()
        fake.ainvoke = ainvoke
        with mock.patch.object(server, "orchestrator", fake), \
             mock.patch.object(server, "detect_agent", lambda m: "coding"):
            resp = asyncio.run(server.chat(ChatRequest(message="hello")))
        self.assertEqual(resp.response, "hi there")
        self.assertEqual(resp.agent, "coding")
        self.assertEqual(resp.steps, 1)
        self.assertTrue(resp.run_id)
        self.assertTrue(resp.thread_id)

    def test_error_returns_500_and_logs(self):
        async def boom(payload, config=None):
            raise RuntimeError("busted")

        fake = mock.Mock()
        fake.ainvoke = boom
        with mock.patch.object(server, "orchestrator", fake), \
             mock.patch.object(server, "detect_agent", lambda m: "coding"):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(server.chat(ChatRequest(message="hello")))
        self.assertEqual(ctx.exception.status_code, 500)
        # the failure must be recorded so a monitoring agent can see it
        self.assertTrue(any(r["status"].startswith("error:")
                            for r in obs.recent_runs()))


if __name__ == "__main__":
    unittest.main()
