"""Unit tests for trial/agents/cicd.py -- the deploy-to-Kubernetes tool.

Covers the generated manifest (locks the probes + resource limits improvement)
and the deploy pipeline (build -> ensure namespace -> apply -> rollout -> get),
with subprocess fully mocked so no docker/kubectl is invoked.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import trial.agents.cicd as tcicd


class TestManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = tcicd._manifest("helloworld", "helloworld", "helloworld-nginx")

    def test_has_deployment_and_service(self):
        self.assertIn("kind: Deployment", self.y)
        self.assertIn("kind: Service", self.y)

    def test_container_spec(self):
        self.assertIn("name: web", self.y)
        self.assertIn("image: helloworld-nginx", self.y)
        self.assertIn("containerPort: 80", self.y)
        self.assertIn("imagePullPolicy: IfNotPresent", self.y)

    def test_probes_present(self):
        self.assertIn("livenessProbe", self.y)
        self.assertIn("readinessProbe", self.y)
        self.assertIn("path: /", self.y)
        self.assertIn("port: 80", self.y)

    def test_resource_limits_present(self):
        self.assertIn("requests:", self.y)
        self.assertIn("limits:", self.y)
        self.assertIn("cpu: 50m", self.y)
        self.assertIn("memory: 32Mi", self.y)
        self.assertIn("cpu: 100m", self.y)
        self.assertIn("memory: 256Mi", self.y)

    def test_names_and_namespace(self):
        self.assertIn("name: helloworld", self.y)
        self.assertIn("namespace: helloworld", self.y)


class TestDeployPipeline(unittest.TestCase):
    def test_build_apply_rollout_and_write_manifest(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ctx = tmp / "trial" / "helloworld"
            ctx.mkdir(parents=True)

            calls = []

            def fake_run(cmd, *a, **k):
                calls.append(" ".join(cmd))
                m = mock.Mock()
                m.returncode = 0
                m.stdout, m.stderr = "ok\n", ""
                return m

            # ROOT is a Path in the module; the tool builds ROOT/context_dir/k8s.yaml
            with mock.patch.object(tcicd, "ROOT", tmp), \
                 mock.patch("trial.agents.cicd.subprocess.run", fake_run):
                out = tcicd.deploy_to_k8s.invoke({"context_dir": "trial/helloworld"})

            self.assertIn("DEPLOYED OK", out)

            # the manifest written to disk carries the probes + limits
            manifest = (ctx / "k8s.yaml").read_text()
            self.assertIn("livenessProbe", manifest)
            self.assertIn("memory: 256Mi", manifest)

            # pipeline ran docker build -> kubectl apply -> rollout status
            joined = "\n".join(calls)
            self.assertIn("docker build", joined)
            self.assertIn("kubectl apply", joined)
            self.assertIn("rollout status", joined)
            self.assertIn("get svc", joined)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
