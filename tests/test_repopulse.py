import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from repopulse.cli import main, render
from repopulse.scanner import scan


class RepoPulseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_complete_repository(self):
        for name in ("README.md", "LICENSE", ".gitignore", "CONTRIBUTING.md", "tests/test_app.py", ".github/workflows/test.yml", "pyproject.toml"):
            self.write(name)
        self.write("app.py", "# TODO: implement\n# FIXME: repair\n")
        result = scan(self.root)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["languages"], {"Python": 2})
        self.assertEqual(result["marker_count"], 2)
        self.assertEqual(result["markers"][1]["line"], 2)
        self.assertEqual(result["dependency_files"], ["pyproject.toml"])
        self.assertEqual(result, scan(self.root))

    def test_empty_repository(self):
        result = scan(self.root)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["file_count"], 0)
        self.assertIn("None detected.", render(result))

    def test_exclusions(self):
        self.write("node_modules/a.js", "TODO")
        self.write("vendor/app.py", "TODO")
        self.write("sample.egg-info/PKG-INFO", "TODO")
        self.write("keep.py", "hello")
        result = scan(self.root, exclude=["vendor"])
        self.assertEqual(result["file_count"], 1)

    def test_read_limits_and_binary_files(self):
        self.write("large.py", "# TODO: hidden" * 10)
        (self.root / "binary.bin").write_bytes(b"\x00TODO")
        (self.root / "invalid.txt").write_bytes(b"\xffTODO")
        result = scan(self.root, max_read_bytes=20, large_bytes=100)
        self.assertEqual(result["skipped_content_files"], 3)
        self.assertEqual(result["marker_count"], 0)
        self.assertEqual(result["large_files"][0]["path"], "large.py")
        self.assertEqual(result["file_count"], 3)

    def test_marker_cap(self):
        self.write("app.py", "# TODO a\n# FIXME b\n# TODO c\n")
        result = scan(self.root, max_markers=1)
        self.assertEqual(result["marker_count"], 3)
        self.assertEqual(len(result["markers"]), 1)
        self.assertIn("Showing first 1 markers", render(result))
        self.assertEqual(scan(self.root, max_markers=0)["markers"], [])

    def test_symlinks_skipped(self):
        self.write("real.py", "# TODO here")
        try:
            (self.root / "link.py").symlink_to(self.root / "real.py")
            (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual(scan(self.root)["file_count"], 1)

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_git_ignore_and_tracked_files(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("tracked.py", "# TODO tracked")
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.py"], check=True)
        self.write(".gitignore", "*.py\nsecret.txt\n")
        self.write("ignored.py", "# TODO ignored")
        self.write("secret.txt", "private")
        result = scan(self.root)
        self.assertTrue(result["git_ignore_applied"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["marker_count"], 1)

    def test_json_cli_and_threshold(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main([str(self.root), "--format", "json", "--fail-under", "50"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stream.getvalue())["schema_version"], 2)

    def test_export_and_no_overwrite(self):
        output = self.root / "report.md"
        self.assertEqual(main([str(self.root), "--format", "markdown", "-o", str(output)]), 0)
        original = output.read_text()
        self.assertTrue(original.startswith("# RepoPulse:"))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root), "-o", str(output)]), 2)
        self.assertEqual(output.read_text(), original)

    def test_invalid_directory(self):
        with self.assertRaises(ValueError):
            scan(self.root / "missing")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / "missing")]), 2)

    def test_invalid_arguments(self):
        for option, value in (("--fail-under", "101"), ("--large-bytes", "0"), ("--max-markers", "-1")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main([option, value])
            self.assertEqual(raised.exception.code, 2)

    def test_terminal_and_markdown_escaping(self):
        self.write("app.py", "# TODO: \x1b[31m <script> *unsafe*\n")
        result = scan(self.root)
        self.assertNotIn("\x1b", render(result))
        output = render(result, markdown=True)
        self.assertIn("\\<script\\>", output)
        self.assertIn("\\*unsafe\\*", output)


if __name__ == "__main__":
    unittest.main()
