"""Unit tests for the app/agents/* STUB tools (the scaffold, pre-real-tools).

The stubs return canned text by design; we assert they do so, and that the two
safety invariants hold: prod deploys are BLOCKED and improvements are dry-run.
No LLM / network: we call the langchain tools directly.
"""

import unittest

from app.agents.base import build_worker
from app.agents.cicd import (build_cicd_agent, deploy_to_k8s, trigger_pipeline)
from app.agents.coding import build_coding_agent, run_tests, write_code
from app.agents.improvement import (apply_improvement, build_improver_agent,
                                    propose_improvement)
from app.agents.monitoring import (build_monitor_agent, check_health, fetch_logs,
                                   query_metrics)


def call(tool, **args):
    """Invoke a langchain @tool as a plain function and return its text output."""
    out = tool.invoke(args)
    if isinstance(out, str):
        return out
    if hasattr(out, "content"):
        return out.content
    return str(out)


class TestCodingStubs(unittest.TestCase):
    def test_write_code(self):
        self.assertIn("coding", call(write_code, language="python",
                                     description="x").lower())

    def test_run_tests_reports_passes(self):
        self.assertIn("passed", call(run_tests, target="module").lower())


class TestCicdStubs(unittest.TestCase):
    def test_trigger_pipeline_queues(self):
        self.assertIn("queued", call(trigger_pipeline, branch="main").lower())

    def test_deploy_prod_is_blocked(self):          # safety invariant
        out = call(deploy_to_k8s, channel="prod").lower()
        self.assertIn("block", out)
        self.assertIn("approval", out)

    def test_deploy_staging_allowed(self):
        self.assertIn("deployed", call(deploy_to_k8s, channel="staging").lower())

    def test_deploy_case_insensitive_prod_gate(self):
        self.assertIn("block", call(deploy_to_k8s, channel="PROD").lower())


class TestMonitoringStubs(unittest.TestCase):
    def test_query_metrics(self):
        self.assertIn("baseline", call(query_metrics, metric="latency_p99").lower())

    def test_fetch_logs(self):
        self.assertIn("no errors", call(fetch_logs, component="agent",
                                        since="5m").lower())

    def test_check_health(self):
        self.assertIn("healthy", call(check_health).lower())


class TestImprovementStubs(unittest.TestCase):
    def test_propose(self):
        self.assertIn("improve", call(propose_improvement, area="retries").lower())

    def test_apply_is_dry_run(self):                # safety invariant
        self.assertIn("dry-run", call(apply_improvement, change="x").lower())


class TestBuildWorker(unittest.TestCase):
    def test_builds_a_graph_with_invoke(self):
        g = build_worker("you are a test agent", [])
        self.assertTrue(hasattr(g, "invoke"))

    def test_all_six_builder_fns_return_graphs(self):
        for builder in (build_coding_agent, build_cicd_agent,
                        build_monitor_agent):
            self.assertTrue(hasattr(builder(), "invoke"))


if __name__ == "__main__":
    unittest.main()
