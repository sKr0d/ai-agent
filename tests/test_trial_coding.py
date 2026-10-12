"""Unit tests for trial/agents/coding.py -- write_file (path sandboxing).

The tool strips a leading `helloworld/` prefix and refuses to escape the project
directory. Each test runs against a temp dir (BASE is patched) so nothing is
written into the real trial/helloworld/ tree.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import trial.agents.coding as tcoding


class BaseWriteFile(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh, resolved temp dir that BASE is patched to, so
        # nothing is ever written into the real trial/helloworld/ tree.
        # NOTE: .resolve() is critical on macOS — mkdtemp() returns /var/... which
        # is a symlink to /private/var/...; the tool's path-sandbox check compares
        # the un-patched BASE against the resolved target, so both must be resolved.
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._patcher = mock.patch.object(tcoding, "BASE", self.tmp)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def _call(self, **args):
        out = tcoding.write_file.invoke(args)
        return out if isinstance(out, str) else str(out.content if hasattr(out, "content") else out)


class TestWriteFile(BaseWriteFile):
    def test_strips_helloworld_prefix(self):
        out = self._call(path="helloworld/index.html", content="<h1>hi</h1>\n")
        target = self.tmp / "index.html"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "<h1>hi</h1>\n")
        self.assertIn(str(self.tmp), out)

    def test_writes_nested_prefix_to_shallow_path(self):
        out = self._call(path="helloworld/helloworld/foo.txt", content="x")
        target = self.tmp / "foo.txt"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "x")

    def test_normal_write_returns_written_path_and_len(self):
        out = self._call(path="Dockerfile", content="FROM nginx:latest\n")
        self.assertTrue((self.tmp / "Dockerfile").exists())
        self.assertEqual((self.tmp / "Dockerfile").read_text(), "FROM nginx:latest\n")
        self.assertIn("wrote", out.lower())

    def test_refuses_path_escape(self):
        before = set(self.tmp.iterdir())
        out = self._call(path="../../evil.md", content="evil")
        self.assertIn("refused", out.lower())
        self.assertSetEqual(set(self.tmp.iterdir()), before)  # nothing written
        self.assertFalse((self.tmp / "evil.md").exists())

    def test_refuses_ancestry_escape(self):
        out = self._call(path="helloworld/../secret.txt", content="x")  # -> ../secret.txt
        self.assertIn("refused", out.lower())
        self.assertFalse((self.tmp / "secret.txt").exists())


if __name__ == "__main__":
    unittest.main()
