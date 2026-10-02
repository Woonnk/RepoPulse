import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from repopulse.cli import main
from repopulse.config import load_config
from repopulse.sarif import render_sarif
from repopulse.scanner import scan


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".repopulse").mkdir()
        self.baseline = self.root / ".repopulse" / "baseline.json"

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(self.root), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def save_baseline(self):
        self.baseline.write_text(json.dumps(scan(self.root)), encoding="utf-8")

    def test_init_config_is_valid_and_does_not_scan(self):
        (self.root / "package.json").write_text("invalid", encoding="utf-8")
        code, output, error = self.cli("--init-config")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Created", output)
        settings = load_config(self.root)
        self.assertEqual(settings["max_markers"], 200)
        self.assertIsNone(settings["fail_on"])
        self.assertEqual(self.cli("--format", "json")[0], 0)

    def test_init_config_preserves_existing_or_symlink_targets(self):
        config = self.root / "repopulse.toml"
        config.write_text("keep me", encoding="utf-8")
        self.assertEqual(self.cli("--init-config")[0], 2)
        self.assertEqual(config.read_text(), "keep me")
        config.unlink()
        target = self.root / "existing.toml"
        target.write_text("keep target", encoding="utf-8")
        try:
            config.symlink_to(target)
        except OSError:
            return  # Existing regular-file protection was still verified.
        self.assertEqual(self.cli("--init-config")[0], 2)
        self.assertEqual(target.read_text(), "keep target")

    def test_init_config_rejects_scan_options_before_writing(self):
        for args in (("--format", "json"), ("--fail-on", "warning"), ("--max-markers", "0"), ("--check", "readme")):
            with self.subTest(args=args):
                self.assertEqual(self.cli("--init-config", *args)[0], 2)
                self.assertFalse((self.root / "repopulse.toml").exists())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / "missing"), "--init-config"]), 2)

    def test_new_threshold_requires_baseline_without_writing(self):
        output = self.root / ".repopulse" / "result.json"
        code, _, error = self.cli("--fail-on-new", "warning", "-o", str(output))
        self.assertEqual(code, 2)
        self.assertIn("requires --baseline", error)
        self.assertFalse(output.exists())

    def test_new_threshold_ignores_existing_findings(self):
        self.save_baseline()
        self.assertEqual(self.cli("--baseline", str(self.baseline), "--fail-on-new", "warning")[0], 0)
        self.assertEqual(self.cli("--baseline", str(self.baseline), "--fail-on-new", "warning", "--fail-on", "warning")[0], 1)

    def test_new_threshold_severity_and_report_export(self):
        self.save_baseline()
        (self.root / "package.json").write_text("invalid", encoding="utf-8")
        output = self.root / ".repopulse" / "report.sarif"
        code, _, error = self.cli("--baseline", str(self.baseline), "--fail-on-new", "error", "--format", "sarif", "-o", str(output))
        self.assertEqual((code, error), (1, ""))
        results = json.loads(output.read_text())["runs"][0]["results"]
        self.assertTrue(any(r["ruleId"] == "manifest-valid" and r["baselineState"] == "new" for r in results))
        self.assertTrue(any(r["ruleId"] == "readme" and r["baselineState"] == "unchanged" for r in results))
        (self.root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        self.assertEqual(self.cli("--baseline", str(self.baseline), "--fail-on-new", "error")[0], 0)
        self.assertEqual(self.cli("--baseline", str(self.baseline), "--fail-on-new", "warning")[0], 1)

    def test_incompatible_baseline_cannot_bypass_new_threshold(self):
        self.save_baseline()
        code, _, error = self.cli("--baseline", str(self.baseline), "--fail-on-new", "warning", "--check", "readme")
        self.assertEqual(code, 2)
        self.assertIn("different enabled_checks", error)

    def test_sarif_preserves_rules_levels_fingerprints_and_relative_paths(self):
        folder = self.root / "café #space"
        folder.mkdir()
        (folder / "package.json").write_text("invalid", encoding="utf-8")
        report = scan(self.root)
        sarif = render_sarif(report)
        self.assertEqual(sarif["version"], "2.1.0")
        run = sarif["runs"][0]
        self.assertEqual(len(run["results"]), len(report["findings"]))
        self.assertEqual({r["level"] for r in run["results"]}, {"note", "warning", "error"})
        for result, finding in zip(run["results"], report["findings"]):
            self.assertEqual(run["tool"]["driver"]["rules"][result["ruleIndex"]]["id"], result["ruleId"])
            self.assertEqual(result["partialFingerprints"]["repopulse/v1"], finding["id"])
            self.assertIn(finding["suggestion"], result["message"]["text"])
            self.assertNotIn("baselineState", result)
            if finding["path"]:
                self.assertEqual(result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "caf%C3%A9%20%23space/package.json")
            else:
                self.assertNotIn("locations", result)
        self.assertNotIn(str(self.root), json.dumps(sarif))

    def test_sarif_empty_results_and_scan_warnings(self):
        report = scan(self.root, enabled_checks=[])
        report["warnings"] = ["Unread file"]
        run = render_sarif(report)["runs"][0]
        self.assertEqual(run["results"], [])
        self.assertEqual(run["tool"]["driver"]["rules"], [])
        self.assertEqual(run["invocations"][0]["toolExecutionNotifications"][0]["message"]["text"], "Unread file")

    def test_unread_baseline_coverage_is_not_marked_unchanged(self):
        (self.root / "package.json").write_text("invalid", encoding="utf-8")
        report = scan(self.root)
        report["comparison"] = {"new_findings": [], "uncompared_content_files": ["package.json"]}
        result = next(r for r in render_sarif(report)["runs"][0]["results"] if r["ruleId"] == "manifest-valid")
        self.assertNotIn("baselineState", result)
        finding = next(f for f in report["findings"] if f["check"] == "manifest-valid")
        finding["line"] = 3
        result = next(r for r in render_sarif(report)["runs"][0]["results"] if r["ruleId"] == "manifest-valid")
        self.assertEqual(result["locations"][0]["physicalLocation"]["region"]["startLine"], 3)


if __name__ == "__main__":
    unittest.main()
