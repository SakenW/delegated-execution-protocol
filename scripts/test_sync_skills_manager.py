"""Exercise the sync gate with real Git trees and a recording Manager CLI."""

import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sync_skills_manager import sync


class SyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.src, self.lib = base / "source", base / "library"
        self.src.mkdir()
        self.git("init", "-q")
        for name in ("gone", "different", "mode"):
            (self.src / name).write_text(name)
        (self.src / ".gitignore").write_text("*.pyc\n")
        self.git("add", "gone", "different", "mode", ".gitignore")
        self.commit()
        self.before = self.git("rev-parse", "HEAD")
        shutil.copytree(self.src, self.lib, ignore=shutil.ignore_patterns(".git"))
        (self.src / "different").write_text("candidate")
        self.git("add", "different")
        self.commit()
        self.marker = base / "update-called"
        self.manager = base / "cli"
        info = dict(source_type="local", path=str(self.lib), source_ref=str(self.src))
        self.manager.write_text(
            "#!/usr/bin/env python3\nimport sys, shutil\nfrom pathlib import Path\n"
            f"if sys.argv[3] == 'show': print({json.dumps(info)!r})\n"
            "elif sys.argv[3] == 'update':\n"
            f" Path({str(self.marker)!r}).touch()\n"
            f" shutil.copy2({str(self.src / 'different')!r}, {str(self.lib / 'different')!r})\n"
            " print('[{\"refreshed\":true,\"error\":null}]')\n"
            "else: sys.exit(2)\n"
        )
        self.manager.chmod(0o700)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.src, text=True).strip()

    def commit(self):
        self.git("-c", "user.name=fixture", "-c", "user.email=fixture@example.test",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")

    def test_all_differences_reported_without_update(self):
        (self.lib / "gone").unlink()
        (self.lib / "different").write_text("independent edit")
        (self.lib / "缓存.pyc").write_text("ignored file")
        (self.lib / "mode").chmod(0o755)
        (self.src / "untracked").symlink_to("different")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertNotEqual(sync(self.src, self.manager, self.before), 0)
        for line in ('Manager 缺少 "gone"', 'Manager 内容不同 "different"', 'Manager 多出 "缓存.pyc"',
                     'Manager 文件类型或执行权限不同 "mode"', '源码 多出 "untracked"'):
            self.assertIn(line, err.getvalue().splitlines())
        self.assertFalse(self.marker.exists())
        self.assertEqual((self.lib / "different").read_text(), "independent edit")

    def test_extra_path_alone_stops_update(self):
        (self.lib / "extra.pyc").touch()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertNotEqual(sync(self.src, self.manager, self.before), 0)
        self.assertEqual(err.getvalue().strip(), 'Manager 多出 "extra.pyc"')
        self.assertFalse(self.marker.exists())

    def test_changed_source_alone_stops_update(self):
        (self.src / "different").write_text("uncommitted")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertNotEqual(sync(self.src, self.manager, self.before), 0)
        self.assertEqual(err.getvalue().strip(), '源码 内容不同 "different"')
        self.assertFalse(self.marker.exists())

    def test_content_only_drift_stops_update(self):
        (self.lib / "different").write_text("independent edit")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertNotEqual(sync(self.src, self.manager, self.before), 0)
        self.assertIn('内容不同 "different"', err.getvalue())
        self.assertFalse(self.marker.exists())

    def test_dry_run_then_valid_transition(self):
        self.assertEqual(sync(self.src, self.manager, self.before, check_only=True), 0)
        self.assertFalse(self.marker.exists())
        self.assertEqual(sync(self.src, self.manager, self.before), 0)
        self.assertTrue(self.marker.exists())
        self.assertEqual((self.lib / "different").read_text(), "candidate")


if __name__ == "__main__":
    unittest.main()
