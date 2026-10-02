"""Smoke-test the installed package outside its source checkout."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run():
    with tempfile.TemporaryDirectory(prefix="repopulse-install-") as directory:
        root = Path(directory)
        project = root / "sample"
        project.mkdir()
        (project / "package.json").write_text('{"name":"sample","scripts":{"test":"node --test"}}', encoding="utf-8")
        command = [sys.executable, "-I", "-m", "repopulse", str(project)]
        result = subprocess.run(command + ["--format", "json"], cwd=root, check=True, capture_output=True, text=True)
        report = json.loads(result.stdout)
        assert report["schema_version"] == 2
        assert report["projects"][0]["type"] == "Node"
        subprocess.run(command + ["--format", "html", "--output", str(root / "report.html"), "--snapshot", str(root / "baseline.json")], cwd=root, check=True)
        assert "<script>" in (root / "report.html").read_text(encoding="utf-8")
        result = subprocess.run(command + ["--baseline", str(root / "baseline.json"), "--format", "json"], cwd=root, check=True, capture_output=True, text=True)
        assert not json.loads(result.stdout)["comparison"]["new_findings"]
        result = subprocess.run(command + ["--check", "readme", "--fail-on", "warning"], cwd=root, capture_output=True)
        assert result.returncode == 1
        result = subprocess.run(command + ["--format", "html", "-o", str(root / "report.html")], cwd=root, capture_output=True)
        assert result.returncode == 2
        print("Installed-wheel smoke checks passed (isolated imports, JSON, HTML assets, snapshots, exit codes).")


if __name__ == "__main__":
    run()
