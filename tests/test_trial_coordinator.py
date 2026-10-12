"""Unit tests for trial/coordinator.py -- transcript + port-forward helpers.

`render`, `truncate`, `one_line`, `_as_text`, and `brief` are pure; the
port-forward lifecycle functions are tested with subprocess/urllib mocked. The
full `run()` pipeline (real agents + real cluster) is NOT exercised here -- it
needs Ollama + a live k8s, so it is documented as integration-only.
"""

import contextlib
import unittest
from unittest import mock

import trial.coordinator as tco


class _M:
    """Minimal LangChain-message stand-in."""
    def __init__(self, type, name=None, tool_calls=None, content=""):
        self.type = type
        self.name = name
        self.tool_calls = tool_calls or []
        self.content = content


class TestTruncate(unittest.TestCase):
    def test_short_unchanged(self):
        self.assertEqual(tco.truncate("hello"), "hello")

    def test_long_is_truncated(self):
        out = tco.truncate("a" * 5000)
        self.assertTrue(out.startswith("a" * 1500))
        self.assertIn("truncated", out.lower())


class TestOneLine(unittest.TestCase):
    def test_skips_comments_and_blanks(self):
        self.assertEqual(tco.one_line("# a comment\n\nThe real line\n"), "The real line")

    def test_collapses_internal_ws(self):
        self.assertEqual(tco.one_line("  multiple   spaces\n"), "multiple spaces")

    def test_strips_list_markers(self):
        self.assertEqual(tco.one_line("- an item"), "an item")
        self.assertEqual(tco.one_line("1. numbered"), "numbered")

    def test_truncates(self):
        out = tco.one_line("x" * 300)
        self.assertTrue(out.endswith("\u2026"))
        self.assertLessEqual(len(out), 101)

    def test_no_summary_fallback(self):
        self.assertEqual(tco.one_line("# only a comment"), "(no summary)")


class TestAsText(unittest.TestCase):
    def test_passthrough(self):
        self.assertEqual(tco._as_text("hi"), "hi")

    def test_coerces_non_str(self):
        self.assertEqual(tco._as_text(["a", "b"]), str(["a", "b"]))


class TestBrief(unittest.TestCase):
    def test_fixed_params(self):
        b = tco.brief()
        self.assertEqual(b["port"], 8081)
        self.assertEqual(b["image"], "helloworld-nginx")
        self.assertEqual(b["app"], "helloworld")
        self.assertEqual(b["namespace"], "helloworld")
        self.assertIn("Hello World", b["goal"])


class TestRender(unittest.TestCase):
    def test_full_block(self):
        msgs = [
            _M("human", content="do the task"),
            _M("ai", tool_calls=[{"name": "write_file", "args": {}}]),
            _M("tool", name="write_file", content="wrote x"),
            _M("ai", content="done, wrote x"),
        ]
        out = tco.render(msgs, "CODING")
        self.assertIn("## CODING agent", out)
        self.assertIn("Task from coordinator", out)        # human task block
        self.assertIn("Agent plans to call", out)          # ai plan block
        self.assertIn("Tool `write_file` returned", out)   # tool result block
        self.assertIn("Report to coordinator", out)        # final report block
        self.assertIn("do the task", out)
        self.assertIn("wrote x", out)

    def test_unknown_type_is_skipped(self):
        out = tco.render([_M("weird", content="x")], "X")
        self.assertIn("## X agent", out)
        self.assertNotIn("x", out)


# ------------------------------------------------------------- port-forward ----
class TestPortForwardLifecycle(unittest.TestCase):
    def test_stop_proc_none_is_noop(self):
        self.assertIsNone(tco._stop_proc(None))

    def test_kill_stale_portforward_is_safe(self):
        with mock.patch("trial.coordinator.subprocess.run",
                        return_value=mock.Mock(returncode=0)), \
             mock.patch("trial.coordinator.time.sleep", lambda *a, **k: None):
            self.assertIsNone(tco._kill_stale_portforward())

    def test_wait_reachable_true(self):
        @contextlib.contextmanager
        def ok(url, timeout=3):
            class R:
                status = 200
            yield R()
        with mock.patch("trial.coordinator.urllib.request.urlopen", ok):
            self.assertTrue(tco._wait_reachable("http://x/", attempts=2, delay=0))

    def test_wait_reachable_false(self):
        def boom(url, timeout=3):
            raise ConnectionError("refused")
        with mock.patch("trial.coordinator.urllib.request.urlopen", side_effect=boom), \
             mock.patch("trial.coordinator.time.sleep", lambda *a, **k: None):
            self.assertFalse(tco._wait_reachable("http://x/", attempts=3, delay=0))


if __name__ == "__main__":
    unittest.main()
