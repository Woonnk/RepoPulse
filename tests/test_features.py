import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from repopulse.cli import main, render
from repopulse.compare import compare, load_snapshot, validate_snapshot
from repopulse.config import CHECK_IDS, load_config, validate
from repopulse.html_report import render_html
from repopulse.scanner import scan


FIXTURES = Path(__file__).parent / "fixtures"


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(self.root), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_realistic_language_fixtures(self):
        cases = [
            ("python", "Python", {"readme-usage", "python-version"}, ["FastAPI"]),
            ("node", "Node", {"node-test-script", "node-lockfile"}, ["React", "Vite"]),
            ("rust", "Rust", {"rust-edition"}, []),
            ("go", "Go", {"go-version"}, []),
        ]
        for folder, kind, checks, frameworks in cases:
            with self.subTest(folder=folder):
                result = scan(FIXTURES / folder)
                self.assertEqual(result["projects"][0]["type"], kind)
                self.assertEqual(result["projects"][0]["frameworks"], frameworks)
                self.assertTrue(checks <= {f["check"] for f in result["findings"]})
                self.assertTrue(all(f["suggestion"] for f in result["findings"]))
                validate_snapshot(result)

    def test_monorepo_detection_and_nested_lockfile(self):
        self.write("web/package.json", '{"scripts":{"test":"vitest"},"dependencies":{"vue":"3"}}')
        self.write("web/pnpm-lock.yaml", "lockfileVersion: 9")
        self.write("api/go.mod", "module example.com/api\n\ngo 1.22.0\n")
        self.write("tools/Cargo.toml", '[package]\nname="tools"\nversion="0.1.0"\nedition="2021"\n')
        result = scan(self.root)
        self.assertEqual({p["type"] for p in result["projects"]}, {"Node", "Rust", "Go"})
        self.assertFalse(any(f["check"] in ("node-lockfile", "node-test-script", "rust-edition", "go-version") for f in result["findings"]))

    def test_manifests_are_never_executed(self):
        self.write("setup.py", 'raise RuntimeError("must never execute")')
        self.write("package.json", '{"scripts":{"test":"touch malicious-file"}}')
        scan(self.root)
        self.assertFalse((self.root / "malicious-file").exists())

    def test_manifest_parse_failures_are_findings(self):
        for filename, content in (("package.json", "[]"), ("pyproject.toml", "[broken"), ("Cargo.toml", "[package]\nname = ["), ("go.mod", "go 1.22")):
            with self.subTest(filename=filename):
                self.write(filename, content)
                result = scan(self.root, enabled_checks=["manifest-valid"])
                self.assertTrue(any(f["path"] == filename and f["severity"] == "error" for f in result["findings"]))
                (self.root / filename).unlink()

    def test_unread_manifest_is_not_reported_invalid(self):
        self.write("package.json", '{"name": "long name"}')
        result = scan(self.root, max_read_bytes=4)
        self.assertEqual(result["projects"][0]["manifest_status"], "unread")
        self.assertFalse(any(f["check"] == "manifest-valid" for f in result["findings"]))

    def test_workspace_and_dynamic_metadata(self):
        self.write("pyproject.toml", '[project]\nname="x"\ndynamic=["requires-python"]\n')
        self.write("Cargo.toml", '[workspace.package]\nedition="2021"\n[package]\nname="x"\nversion="0.1.0"\n')
        self.assertFalse(any(f["check"] in ("python-version", "rust-edition") for f in scan(self.root)["findings"]))

    def test_documentation_checks_and_test_directory_false_positive(self):
        self.write("README.md", "# Project\n\nDescription only.\n")
        self.write("tests/README.md", "No real tests yet.")
        result = scan(self.root)
        self.assertTrue({"readme-install", "readme-usage", "tests"} <= {f["check"] for f in result["findings"]})
        self.write("README.md", "# Project\n\n## Installation\n\nSet up.\n\n## Usage\n\nRun.\n")
        self.write("tests/app.test.tsx", "export {}")
        self.assertFalse(any(f["check"] in ("readme-install", "readme-usage", "tests") for f in scan(self.root)["findings"]))

    def test_config_auto_discovery_cli_overrides_and_merge(self):
        self.write("repopulse.toml", '[scan]\nlarge_bytes=10\nmax_markers=0\nexclude=["vendor"]\nenabled_checks=["large-files"]\n')
        self.write("vendor/a.py", "# TODO ignored")
        self.write("cache/b.py", "# TODO ignored")
        self.write("app.py", "# TODO visible")
        code, output, _ = self.cli("--format", "json", "--max-markers", "1", "--exclude", "cache", "--large-bytes", "1000")
        report = json.loads(output)
        self.assertEqual(code, 0)
        self.assertEqual(report["settings"]["exclude"], ["cache", "vendor"])
        self.assertEqual(report["marker_count"], 1)
        self.assertEqual(len(report["markers"]), 1)
        self.assertIsNone(report["score"])
        self.assertEqual(report["findings"], [])

    def test_explicit_config_and_no_config(self):
        config = self.write("custom.toml", '[scan]\nenabled_checks=[]\n')
        self.write("repopulse.toml", "invalid = [")
        self.assertEqual(self.cli("--config", str(config))[0], 0)
        self.assertEqual(self.cli("--no-config")[0], 0)
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(self.cli("--config", str(self.root / "missing"))[0], 2)

    def test_invalid_config_types_and_unknown_keys(self):
        cases = ({"large_bytes": True}, {"max_read_bytes": -1}, {"max_markers": 1.5}, {"exclude": "vendor"}, {"exclude": ["../vendor"]}, {"enabled_checks": ["unknown"]}, {"fail_under": 101}, {"fail_on": "fatal"}, {"made_up": 1})
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate(settings)
        self.write("repopulse.toml", "enabled_checks = []")
        with self.assertRaises(ValueError):
            load_config(self.root)

    def test_checks_and_severity_exit_codes(self):
        self.write("package.json", "not json")
        self.assertEqual(self.cli("--fail-on", "error")[0], 1)
        self.assertEqual(self.cli("--check", "readme", "--fail-on", "error")[0], 0)
        self.assertEqual(self.cli("--check", "readme", "--fail-on", "warning")[0], 1)
        self.assertEqual(self.cli("--check", "large-files", "--fail-under", "50")[0], 2)
        self.write("repopulse.toml", '[scan]\nfail_on="warning"\n')
        self.assertEqual(self.cli("--fail-on", "none")[0], 0)
        self.assertEqual(self.cli("--list-checks")[1].splitlines(), list(CHECK_IDS))

    def test_changes_markers_duplicates_line_shifts_and_size_growth(self):
        path = self.write("app.py", "# TODO: same\n# TODO: same\n# FIXME: old\n")
        before = scan(self.root, max_markers=0)
        path.write_text("\n\n# TODO: same\n# FIXME: new\n" + "x" * 100)
        after = scan(self.root, max_markers=20)
        diff = compare(before, after)
        self.assertEqual(sum(m["count"] for m in diff["new_markers"]), 1)
        self.assertEqual(sum(m["count"] for m in diff["resolved_markers"]), 2)
        self.assertTrue(any(m["kind"] == "TODO" and m["count"] == 1 for m in diff["resolved_markers"]))
        self.assertGreater(diff["grown_files"][0]["delta"], 0)

    def test_line_shift_alone_does_not_change_marker(self):
        self.write("app.py", "# TODO: same\n")
        before = scan(self.root)
        self.write("app.py", "\n\n# TODO: same\n")
        diff = compare(before, scan(self.root))
        self.assertEqual(diff["new_markers"], [])
        self.assertEqual(diff["resolved_markers"], [])

    def test_findings_resolve_and_inventory_changes(self):
        path = self.write("app.py", "# TODO: old\n")
        before = scan(self.root)
        path.unlink()
        self.write("README.md", "## Installation\n\n## Usage\n")
        after = scan(self.root)
        diff = compare(before, after)
        self.assertEqual(diff["removed_files"], ["app.py"])
        self.assertEqual(diff["added_files"], ["README.md"])
        self.assertEqual(diff["resolved_findings"][0]["check"], "readme")
        self.assertEqual(diff["resolved_markers"][0]["kind"], "TODO")
        self.assertGreater(diff["score_delta"], 0)
        self.assertIn("Resolved finding", render({**after, "comparison": diff}))

    def test_unread_content_does_not_claim_marker_resolution(self):
        self.write("app.py", "# TODO: old\n")
        before = scan(self.root, max_read_bytes=100)
        self.write("app.py", "x" * 101)
        diff = compare(before, scan(self.root, max_read_bytes=100))
        self.assertEqual(diff["resolved_markers"], [])
        self.assertEqual(diff["uncompared_content_files"], ["app.py"])
        self.assertTrue(diff["warnings"])

    def test_unread_readme_does_not_claim_content_finding_resolution(self):
        self.write("README.md", "Project only")
        before = scan(self.root, max_read_bytes=100)
        self.write("README.md", "x" * 101)
        self.assertFalse(any(f["check"].startswith("readme-") for f in compare(before, scan(self.root, max_read_bytes=100))["resolved_findings"]))

    def test_rejects_incompatible_baselines(self):
        before = scan(self.root)
        for after in (scan(self.root, exclude=["vendor"]), scan(self.root, max_read_bytes=100), scan(self.root, enabled_checks=[])):
            with self.assertRaises(ValueError):
                compare(before, after)
        other = copy.deepcopy(before)
        other["project"] = "other"
        with self.assertRaises(ValueError):
            compare(before, other)
        legacy = self.write("legacy.json", '{"schema_version":1}')
        with self.assertRaises(ValueError):
            load_snapshot(legacy)

    def test_corrupt_and_malicious_baseline_validation(self):
        self.write("app.py", "# TODO: hi\n")
        report = scan(self.root)
        changes = [
            lambda r: r.update(file_count=10),
            lambda r: r["files"][0].update(path="../outside"),
            lambda r: r["files"][0].update(bytes=-1),
            lambda r: r["marker_index"][0].update(count=0),
            lambda r: r["marker_index"][0].update(kind=[]),
            lambda r: r.update(findings={}),
            lambda r: r.update(score=101),
            lambda r: r.update(settings=[]),
        ]
        for mutate in changes:
            broken = copy.deepcopy(report)
            mutate(broken)
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_snapshot(broken)
        bad_json = self.write("bad.json", "{")
        with self.assertRaises(ValueError):
            load_snapshot(bad_json)

    def test_snapshot_and_html_cli_round_trip(self):
        folder = self.root / ".repopulse"
        folder.mkdir()
        snapshot = folder / "baseline.json"
        code, _, error = self.cli("--snapshot", str(snapshot))
        self.assertEqual((code, error), (0, ""))
        self.write("app.py", "# TODO: new\n")
        html = folder / "report.html"
        code, _, error = self.cli("--baseline", str(snapshot), "--format", "html", "-o", str(html))
        self.assertEqual((code, error), (0, ""))
        self.assertIn("report-data", html.read_text())
        self.assertNotIn("baseline.json", [f["path"] for f in scan(self.root)["files"]])

    def test_conflicting_outputs_do_not_leave_partial_reports(self):
        output = self.root / "report.md"
        baseline = self.write("existing.json", "do not touch")
        self.assertEqual(self.cli("-o", str(output), "--snapshot", str(baseline))[0], 2)
        self.assertFalse(output.exists())
        self.assertEqual(baseline.read_text(), "do not touch")
        self.assertEqual(self.cli("-o", str(output), "--snapshot", str(output))[0], 2)
        self.assertFalse(output.exists())

    def test_html_escapes_script_injection_and_preserves_csp_hash(self):
        self.write("app.py", '# TODO: </script><script>globalThis.pwned=1</script> __REPORT_SCRIPT__\n')
        html = render_html(scan(self.root), self.root)
        self.assertNotIn("<script>globalThis.pwned", html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("__REPORT_SCRIPT__", html)  # User content stays literal.
        script = html.split("<script>", 1)[1].split("</script>", 1)[0]
        import base64
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn("sha256-" + digest, html)
        self.assertNotIn("https://", html)

    def test_git_failure_falls_back_without_executing_project(self):
        self.write("app.py", "hello")
        with patch("repopulse.scanner.subprocess.run", side_effect=OSError("git unavailable")):
            result = scan(self.root)
        self.assertFalse(result["git_ignore_applied"])
        self.assertEqual(result["file_count"], 1)

    def test_read_failure_reports_warning_and_inventory(self):
        self.write("app.py", "# TODO: private")
        original = Path.open
        def unread(path, *args, **kwargs):
            if path.name == "app.py":
                raise PermissionError(13, "Permission denied")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", unread):
            result = scan(self.root)
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["marker_count"], 0)
        self.assertFalse(result["files"][0]["content_scanned"])
        self.assertIn("Permission denied", result["warnings"][0])

    def test_config_symlink_is_rejected(self):
        self.write("real.toml", "[scan]\n")
        try:
            (self.root / "repopulse.toml").symlink_to(self.root / "real.toml")
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual(self.cli()[0], 2)

    def test_non_ascii_paths_and_json_escaping(self):
        path = "caf\u00e9/app.py"
        self.write(path, "# TODO: review")
        report = scan(self.root)
        validate_snapshot(report)
        output = render_html(report, self.root)
        self.assertIn("caf%C3%A9", output)
        self.assertIn("caf\\u00e9", output)
        self.assertEqual(compare(report, report)["new_markers"], [])

    def test_snapshot_is_saved_without_comparison_history(self):
        folder = self.root / ".repopulse"
        folder.mkdir()
        before = folder / "before.json"
        after = folder / "after.json"
        self.assertEqual(self.cli("--snapshot", str(before))[0], 0)
        code, output, _ = self.cli("--baseline", str(before), "--snapshot", str(after), "--format", "json")
        self.assertEqual(code, 0)
        self.assertIn("comparison", json.loads(output))
        self.assertNotIn("comparison", load_snapshot(after))

    def test_failing_threshold_still_writes_report(self):
        report = self.root / "report.json"
        self.assertEqual(self.cli("--fail-under", "100", "--format", "json", "-o", str(report))[0], 1)
        self.assertEqual(json.loads(report.read_text())["score"], 0)

    def test_snapshot_requires_full_settings(self):
        report = scan(self.root)
        del report["settings"]["exclude"]
        with self.assertRaises(ValueError):
            validate_snapshot(report)


if __name__ == "__main__":
    unittest.main()
