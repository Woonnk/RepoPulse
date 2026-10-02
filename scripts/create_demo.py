"""Generate disposable report fixtures for browser QA."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repopulse.compare import compare
from repopulse.html_report import render_html
from repopulse.scanner import scan


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def create(output):
    root = output / "demo-project"
    root.mkdir(parents=True)
    write(root / "README.md", "# Demo project\n\nA small API and web workspace.\n")
    write(root / "web/package.json", '{"name":"web","dependencies":{"react":"18","vite":"5"}}')
    write(root / "api/pyproject.toml", '[project]\nname="api"\nversion="0.1.0"\ndependencies=["fastapi>=0.100"]\n')
    write(root / "api/app.py", "# TODO: replace legacy endpoint\n")
    for i in range(60):
        write(root / f"src/module_{i:02}.py", f"value = {i}\n")
    baseline = scan(root)
    # Deliberate fixture mutations exercise the comparison view.
    (root / "api/app.py").unlink()
    write(root / "api/routes.py", "# TODO: add endpoint tests\n# FIXME: handle empty requests\n")
    write(root / "assets/data.txt", "x" * 1200)
    write(root / "src/unsafe.py", "# TODO: </script><script>globalThis.pwned=1</script> & <img src=x onerror=alert(1)>\n")
    report = scan(root)
    report["comparison"] = compare(baseline, report)
    write(output / "report.html", render_html(report, root))
    write(output / "no-baseline.html", render_html(scan(root), root))
    empty = output / "empty-project"
    empty.mkdir()
    write(output / "empty.html", render_html(scan(empty, enabled_checks=[]), empty))
    print(output / "report.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for disposable fixtures")
    create(parser.parse_args().output_dir.resolve())
