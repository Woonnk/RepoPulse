"""Command line interface and human-readable reports."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .scanner import scan
from .checks import SEVERITIES
from .compare import compare, load_snapshot
from .config import CHECK_IDS, load_config, validate
from .html_report import render_html


def _safe(value):
    return "".join(c if c.isprintable() else " " for c in str(value))


def render(report, markdown=False):
    def text(value):
        value = _safe(value)
        if markdown:
            for char in ("\\", "`", "*", "_", "[", "]", "<", ">", "#", "|"):
                value = value.replace(char, "\\" + char)
        return value
    def heading(value):
        return f"## {value}" if markdown else value
    lines = [f"# RepoPulse: {text(report['project'])}" if markdown else f"RepoPulse: {text(report['project'])}", "",
             f"Readiness: {str(report['score']) + '/100' if report['score'] is not None else 'not scored'} (repository basics, not code quality)",
             f"Files: {report['file_count']} | Size: {report['total_bytes']:,} bytes",
             f"Git ignore rules applied: {'yes' if report['git_ignore_applied'] else 'no (built-in exclusions only)'}", "", heading("Repository basics")]
    for check in report["checks"]:
        if not check.get("enabled", True):
            lines.append(f"- Disabled: {check['label']}")
            continue
        lines.append(f"- [{'x' if check['passed'] else ' '}] {check['label']}" if markdown else f"  {'PASS' if check['passed'] else 'MISS'}  {check['label']}")
    lines.extend(["", heading("Detected projects")])
    for project in report["projects"]:
        frameworks = ", ".join(project["frameworks"])
        lines.append(f"- {project['type']}: {text(project['path'])} (manifest: {project['manifest_status']})" + (f"; {frameworks}" if frameworks else ""))
    if not report["projects"]:
        lines.append("No supported project manifests detected.")
    lines.extend(["", heading(f"Actionable findings ({len(report['findings'])})")])
    for finding in report["findings"]:
        lines.append(f"- [{finding['severity'].upper()}] {text(finding['title'])}" + (f" ({text(finding['path'])})" if finding["path"] else ""))
        if finding["evidence"]:
            lines.append(f"  Evidence: {text(finding['evidence'])}")
        lines.append(f"  Fix: {text(finding['suggestion'])}")
    if not report["findings"]:
        lines.append("No enabled checks produced findings.")
    lines.extend(["", heading("Languages (file counts)")])
    lines.extend(f"- {language}: {count}" for language, count in report["languages"].items())
    if not report["languages"]:
        lines.append("No recognized source files.")
    lines.extend(["", heading("Project structure")])
    lines.extend(f"- {text(name)}: {count} files" for name, count in report["top_level"].items())
    lines.extend(["", heading("Dependency manifests")])
    lines.extend(f"- {text(name)}" for name in report["dependency_files"])
    if not report["dependency_files"]:
        lines.append("None detected.")
    lines.extend(["", heading("Large files")])
    lines.extend(f"- {text(item['path'])}: {item['bytes']:,} bytes" for item in report["large_files"])
    if not report["large_files"]:
        lines.append("None detected.")
    lines.extend(["", heading(f"TODO / FIXME markers ({report['marker_count']})")])
    lines.extend(f"- {text(item['path'])}:{item['line']} [{item['kind']}] {text(item['text'])}" for item in report["markers"])
    if report["marker_count"] > len(report["markers"]):
        lines.append(f"Showing first {len(report['markers'])} markers.")
    if not report["marker_count"]:
        lines.append("None detected.")
    lines.extend(["", f"Content skipped (binary, non-UTF-8, or over read limit): {report['skipped_content_files']}"])
    if report["warnings"]:
        lines.extend(["", heading("Warnings")])
        lines.extend(f"- {text(warning)}" for warning in report["warnings"])
    if "comparison" in report:
        diff = report["comparison"]
        lines.extend(["", heading("Changes since baseline"),
                      f"Score change: {diff['score_delta'] if diff['score_delta'] is not None else 'not comparable'} | Size change: {diff['bytes_delta']:+,} bytes"])
        for key, label in (("added_files", "Added to inventory"), ("removed_files", "Removed from inventory")):
            lines.extend(f"- {label}: {text(path)}" for path in diff[key])
        for file in diff["grown_files"]:
            lines.append(f"- Grew: {text(file['path'])} (+{file['delta']:,} bytes)")
        for key, label in (("new_findings", "New finding"), ("resolved_findings", "Resolved finding")):
            lines.extend(f"- {label}: {text(f['title'])}" + (f" ({text(f['path'])})" if f["path"] else "") for f in diff[key])
        for key, label in (("new_markers", "New marker"), ("resolved_markers", "Resolved marker")):
            lines.extend(f"- {label}: {text(m['path'])} [{m['kind']}] x{m['count']}: {text(m['text'] or '(snippet omitted by output limit)')}" for m in diff[key])
        lines.append(f"Content not compared: {len(diff['uncompared_content_files'])} files")
        lines.extend(f"- {text(warning)}" for warning in diff["warnings"])
    return "\n".join(lines) + "\n"


def write_outputs(outputs):
    """Reserve all new outputs before writing; undo only files created here."""
    handles = []
    try:
        for path, content in outputs:
            handle = path.open("x", encoding="utf-8", newline="\n")
            handles.append((path, handle, content))
        for _, handle, content in handles:
            handle.write(content)
        for _, handle, _ in handles:
            handle.close()
    except OSError:
        for path, handle, _ in handles:
            handle.close()
            path.unlink(missing_ok=True)
        raise


def bounded_int(minimum, maximum=None):
    def parse(value):
        number = int(value)
        if number < minimum or (maximum is not None and number > maximum):
            raise argparse.ArgumentTypeError(f"must be >= {minimum}" + (f" and <= {maximum}" if maximum is not None else ""))
        return number
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan local repository basics without executing project code.")
    parser.add_argument("path", nargs="?", default=".", help="directory to scan (default: current directory)")
    parser.add_argument("--version", action="version", version=f"RepoPulse {__version__}")
    parser.add_argument("--format", choices=("text", "markdown", "json", "html"), default="text")
    parser.add_argument("-o", "--output", type=Path, help="write report to a NEW file (existing files are never overwritten)")
    parser.add_argument("--exclude", action="append", default=[], metavar="NAME", help="exclude a file or directory basename; repeatable")
    parser.add_argument("--large-bytes", type=bounded_int(1))
    parser.add_argument("--max-read-bytes", type=bounded_int(1))
    parser.add_argument("--max-markers", type=bounded_int(0))
    parser.add_argument("--fail-under", type=bounded_int(0, 100), metavar="SCORE", help="exit 1 when readiness is below SCORE")
    parser.add_argument("--fail-on", choices=("info", "warning", "error", "none"), help="exit 1 when findings reach this severity; none disables configured threshold")
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument("--config", type=Path, help="explicit TOML config (default: repopulse.toml in scan root)")
    config_group.add_argument("--no-config", action="store_true", help="ignore automatic configuration")
    parser.add_argument("--check", action="append", choices=CHECK_IDS, help="enable only these checks; repeat to include several")
    parser.add_argument("--list-checks", action="store_true", help="list supported check IDs and exit")
    parser.add_argument("--snapshot", type=Path, help="also save a NEW schema v2 JSON baseline")
    parser.add_argument("--baseline", type=Path, help="compare with a previous schema v2 JSON snapshot")
    args = parser.parse_args(argv)
    if args.list_checks:
        print("\n".join(CHECK_IDS))
        return 0
    try:
        root = Path(args.path).expanduser().resolve()
        settings = load_config(root, args.config, args.no_config)
        for name in ("large_bytes", "max_read_bytes", "max_markers", "fail_under", "fail_on"):
            value = getattr(args, name)
            if value is not None:
                settings[name] = None if name == "fail_on" and value == "none" else value
        settings["exclude"] = settings["exclude"] + args.exclude
        if args.check is not None:
            settings["enabled_checks"] = args.check
        settings = validate(settings)
        baseline = load_snapshot(args.baseline) if args.baseline else None
        report = scan(root, **{key: settings[key] for key in ("large_bytes", "max_read_bytes", "max_markers", "exclude", "enabled_checks")})
        if settings["fail_under"] is not None and report["score"] is None:
            raise ValueError("--fail-under requires at least one enabled repository basic check")
        snapshot = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        if baseline is not None:
            report["comparison"] = compare(baseline, report)
        if args.format == "json":
            output = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        elif args.format == "html":
            output = render_html(report, root)
        else:
            output = render(report, args.format == "markdown")
        outputs = []
        if args.output:
            outputs.append((args.output.expanduser(), output))
        if args.snapshot:
            outputs.append((args.snapshot.expanduser(), snapshot))
        write_outputs(outputs)
        if not args.output:
            sys.stdout.write(output)
    except (ValueError, OSError, RecursionError) as error:
        print(f"repopulse: {error}", file=sys.stderr)
        return 2
    below_score = settings["fail_under"] is not None and report["score"] < settings["fail_under"]
    severe = settings["fail_on"] is not None and any(SEVERITIES[f["severity"]] >= SEVERITIES[settings["fail_on"]] for f in report["findings"])
    return 1 if below_score or severe else 0
