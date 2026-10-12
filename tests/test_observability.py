"""Unit tests for app/observability.py.

Covers the JSON formatter, the in-memory run-log ring buffer, and idempotent
logging setup. No network.
"""

import json
import logging
import sys
import unittest

from app import observability as obs


class TestRecordRun(unittest.TestCase):
    def setUp(self):
        obs._runs.clear()

    def tearDown(self):
        obs._runs.clear()

    def test_record_then_recent(self):
        obs.record_run("thread-1", "coding", "ok", 12)
        runs = obs.recent_runs()
        self.assertEqual(len(runs), 1)
        entry = runs[0]
        self.assertEqual(entry["thread_id"], "thread-1")
        self.assertEqual(entry["agent"], "coding")
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["latency_ms"], 12)
        self.assertIn("ts", entry)

    def test_recent_runs_returns_most_recent_n(self):
        for i in range(5):
            obs.record_run(f"t{i}", "a", "ok", i)
        ids = [r["thread_id"] for r in obs.recent_runs(3)]
        self.assertEqual(ids, ["t2", "t3", "t4"])

    def test_recent_runs_clamps_to_available(self):
        obs.record_run("solo", "a", "ok", 1)
        self.assertEqual(len(obs.recent_runs(100)), 1)


class TestRingBufferCap(unittest.TestCase):
    def setUp(self):
        obs._runs.clear()

    def tearDown(self):
        obs._runs.clear()

    def test_buffer_is_capped(self):
        self.assertEqual(obs._runs.maxlen, 200)

    def test_oldest_dropped_past_cap(self):
        for i in range(250):
            obs.record_run(f"r{i}", "a", "ok", i)
        self.assertEqual(len(obs._runs), 200)
        self.assertEqual(obs._runs[0]["thread_id"], "r50")   # r0..r49 dropped
        self.assertEqual(obs._runs[-1]["thread_id"], "r249")


class TestSetupLogging(unittest.TestCase):
    def test_installs_single_json_handler(self):
        obs.setup_logging("info")
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0].formatter, obs._JsonFormatter)

    def test_replaces_handlers_not_appends(self):
        obs.setup_logging("info")
        obs.setup_logging("warning")  # second call must not stack handlers
        self.assertEqual(len(logging.getLogger().handlers), 1)


class TestJsonFormatter(unittest.TestCase):
    def test_core_fields(self):
        f = obs._JsonFormatter()
        rec = logging.LogRecord("agent.x", logging.INFO, "p.py", 1, "hello", None, None)
        out = json.loads(f.format(rec))
        self.assertEqual(out["msg"], "hello")
        self.assertEqual(out["level"], "INFO")
        self.assertEqual(out["logger"], "agent.x")
        self.assertIn("ts", out)
        self.assertNotIn("exc", out)

    def test_exception_field_present(self):
        f = obs._JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        rec = logging.LogRecord("agent.x", logging.ERROR, "p.py", 1, "err", None, exc_info)
        out = json.loads(f.format(rec))
        self.assertIn("exc", out)
        self.assertIn("ValueError", out["exc"])


if __name__ == "__main__":
    unittest.main()
