"""Unit tests for trial/agents/monitoring.py -- the three real signals.

Covers http_get (probe), kubectl_logs (anomaly detection + benign-404
suppression), and query_metrics (pod-health parse, incl. the PodList
items[] bug fix). All external calls are mocked.
"""

import contextlib
import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError

import trial.agents.monitoring as tmon


# ---------------------------------------------------------------- kubectl_logs --
class TestKubectlLogs(unittest.TestCase):
    OK_LINE = "1.1.1.1 - - [x] \"GET / HTTP/1.1\" 200 148 \"-\" \"curl\"\n"
    BENIGN_LINES = (
        # A 3-digit byte size (153, the real observed favicon 404 size) so the
        # line does NOT match the "5xx magnitude" pattern -- it must be treated as
        # benign noise, not a real fault.
        "1.1.1.1 - - [x] \"GET /favicon.ico HTTP/1.1\" 404 153 \"-\" \"curl\"\n"
        "2026/x [error] open() \"/usr/share/nginx/html/favicon.ico\" failed "
        "(2: No such file or directory), client: 1.1.1.1, request: \"GET /favicon.ico HTTP/1.1\"\n"
    )
    REAL_LIKE = (
        "1.1.1.1 - - [x] \"GET /boom HTTP/1.1\" 503 0 \"-\" \"curl\"\n"
        "2026/x [error] upstream timed out\n"
    )

    def test_detects_real_faults_and_suppresses_benign(self):
        log = self.OK_LINE + self.BENIGN_LINES + self.REAL_LIKE
        with mock.patch.object(tmon, "_kubectl", return_value=(True, log)):
            out = tmon.kubectl_logs.invoke({})
        self.assertIn("LOGS for helloworld/helloworld", out)
        self.assertIn("ANOMALY SUMMARY", out)
        after = out.split("ANOMALY SUMMARY", 1)[1]
        self.assertRegex(after, r"2 real-fault line")      # 503 + "upstream"
        self.assertRegex(after, r"1 benign 404 line")       # the favicon 404 noise
        summary = after.split("suppressed:", 1)[1]
        self.assertIn("503", summary)                # real fault reported
        self.assertIn("upstream timed out", summary) # real fault reported
        self.assertNotIn("No such file", summary)    # benign 404 suppressed

    def test_log_read_failed(self):
        with mock.patch.object(tmon, "_kubectl", return_value=(False, "kubectl: not found")):
            out = tmon.kubectl_logs.invoke({})
        self.assertIn("LOG READ FAILED", out)

    def test_empty_logs_summary_none(self):
        with mock.patch.object(tmon, "_kubectl", return_value=(True, "")):
            out = tmon.kubectl_logs.invoke({})
        self.assertIn("0 real-fault line", out)


# ---------------------------------------------------------------- query_metrics --
class TestQueryMetrics(unittest.TestCase):
    def _podlist(self, restarts, ready=True):
        return json.dumps({
            "items": [{
                "metadata": {"name": "helloworld-xyz"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {"ready": ready, "restartCount": restarts}
                    ],
                },
            }]
        })

    def test_healthy_when_zero_restarts(self):
        with mock.patch.object(tmon, "_kubectl",
                               return_value=(True, self._podlist(0))):
            out = tmon.query_metrics.invoke({})
        self.assertIn("helloworld-xyz", out)
        self.assertIn("phase=Running", out)
        self.assertIn("restarts=0", out)
        self.assertIn("ready=True", out)
        self.assertIn("healthy", out)

    def test_restarts_detected(self):
        with mock.patch.object(tmon, "_kubectl",
                               return_value=(True, self._podlist(3))):
            out = tmon.query_metrics.invoke({})
        self.assertIn("restarts=3", out)
        self.assertIn("RESTARTS DETECTED", out)
        self.assertNotIn("healthy", out)

    def test_query_failed(self):
        with mock.patch.object(tmon, "_kubectl", return_value=(False, "boom")):
            out = tmon.query_metrics.invoke({})
        self.assertIn("METRICS QUERY FAILED", out)

    def test_parse_failed(self):
        with mock.patch.object(tmon, "_kubectl", return_value=(True, "not json")):
            out = tmon.query_metrics.invoke({})
        self.assertIn("METRICS PARSE FAILED", out)


# ------------------------------------------------------------------- http_get --
class TestHttpGet(unittest.TestCase):
    def test_200_returns_body(self):
        @contextlib.contextmanager
        def ok(url, timeout=5):
            class R:
                status = 200
                def read(self):
                    return b"hello world"
            yield R()
        with mock.patch.object(tmon.urllib.request, "urlopen", ok):
            out = tmon.http_get.invoke({"url": "http://x/", "retries": 2})
        self.assertIn("HTTP 200", out)
        self.assertIn("hello world", out)

    def test_http_error_returns_code(self):
        def err(url, timeout=5):
            raise HTTPError(url, 500, "err", {}, io.BytesIO(b"Bad Gateway"))
        with mock.patch.object(tmon.urllib.request, "urlopen", side_effect=err):
            out = tmon.http_get.invoke({"url": "http://x/", "retries": 3})
        self.assertIn("HTTP 500", out)
        self.assertIn("Bad Gateway", out)

    def test_unreachable(self):
        def refused(url, timeout=5):
            raise ConnectionError("connection refused")
        with mock.patch.object(tmon.urllib.request, "urlopen", side_effect=refused), \
             mock.patch("trial.agents.monitoring.time.sleep", lambda *a, **k: None):
            out = tmon.http_get.invoke({"url": "http://x/", "retries": 2})
        self.assertIn("UNREACHABLE", out)


if __name__ == "__main__":
    unittest.main()
