"""Validate and compare versioned JSON snapshots without executing content."""

from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re

from .config import CHECK_IDS, validate


def _path(value):
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("Snapshot contains an invalid relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value == ".":
        raise ValueError("Snapshot contains an invalid relative path")


def validate_snapshot(report):
    if not isinstance(report, dict) or report.get("schema_version") != 2:
        raise ValueError("Baseline must be a RepoPulse schema_version 2 JSON snapshot; generate a new baseline")
    try:
        if not isinstance(report["project"], str) or not report["project"]:
            raise ValueError("Invalid snapshot project")
        for key in ("file_count", "total_bytes", "marker_count"):
            if type(report[key]) is not int or report[key] < 0:
                raise ValueError(f"Invalid snapshot {key}")
        if report["score"] is not None and (type(report["score"]) is not int or not 0 <= report["score"] <= 100):
            raise ValueError("Invalid snapshot score")
        if type(report["git_ignore_applied"]) is not bool:
            raise ValueError("Invalid snapshot ignore status")
        if not isinstance(report["settings"], dict):
            raise ValueError("Invalid snapshot settings")
        validate(report["settings"])
        if any(key not in report["settings"] for key in ("exclude", "max_read_bytes", "enabled_checks", "large_bytes", "max_markers")):
            raise ValueError("Snapshot is missing effective scan settings")
        for key in ("files", "markers", "marker_index", "findings"):
            if not isinstance(report[key], list):
                raise ValueError(f"Invalid snapshot {key}")
        paths = set()
        for file in report["files"]:
            _path(file["path"])
            if file["path"] in paths or type(file["bytes"]) is not int or file["bytes"] < 0 or type(file["content_scanned"]) is not bool:
                raise ValueError("Invalid or duplicate snapshot file")
            paths.add(file["path"])
        if len(paths) != report["file_count"] or sum(f["bytes"] for f in report["files"]) != report["total_bytes"]:
            raise ValueError("Snapshot file totals do not match inventory")
        identities = set()
        for marker in report["marker_index"]:
            _path(marker["path"])
            identity = (marker["path"], marker["kind"], marker["fingerprint"])
            if marker["path"] not in paths or marker["kind"] not in ("TODO", "FIXME") or not isinstance(marker["fingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", marker["fingerprint"]) or type(marker["count"]) is not int or marker["count"] <= 0 or identity in identities:
                raise ValueError("Invalid or duplicate snapshot marker")
            identities.add(identity)
        if sum(m["count"] for m in report["marker_index"]) != report["marker_count"]:
            raise ValueError("Snapshot marker totals do not match index")
        for marker in report["markers"]:
            if (marker["path"], marker["kind"], marker["fingerprint"]) not in identities or not isinstance(marker["text"], str) or type(marker["line"]) is not int or marker["line"] < 1:
                raise ValueError("Invalid snapshot marker sample")
        ids = set()
        for finding in report["findings"]:
            if not isinstance(finding["id"], str) or not finding["id"] or finding["id"] in ids or finding["check"] not in CHECK_IDS or finding["severity"] not in ("info", "warning", "error"):
                raise ValueError("Invalid or duplicate snapshot finding")
            ids.add(finding["id"])
            for key in ("title", "suggestion"):
                if not isinstance(finding[key], str):
                    raise ValueError("Invalid snapshot finding text")
            if finding["path"] is not None:
                _path(finding["path"])
                if finding["path"] not in paths:
                    raise ValueError("Finding path is absent from inventory")
            if finding.get("evidence") is not None and not isinstance(finding["evidence"], str):
                raise ValueError("Invalid snapshot finding evidence")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Baseline is missing required fields or contains invalid field types") from error
    return report


def load_snapshot(path):
    path = Path(path).expanduser()
    with path.open("rb") as handle:
        data = handle.read(50_000_001)
    if len(data) > 50_000_000:
        raise ValueError("Baseline exceeds 50 MB")
    try:
        report = json.loads(data)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError(f"Could not parse baseline JSON: {error}") from error
    return validate_snapshot(report)


def compare(before, after):
    validate_snapshot(before)
    validate_snapshot(after)
    if before["project"] != after["project"]:
        raise ValueError("Baseline project name differs from the scanned directory")
    for key in ("exclude", "max_read_bytes", "enabled_checks", "large_bytes"):
        if before["settings"].get(key) != after["settings"].get(key):
            raise ValueError(f"Baseline uses different {key}; rescan with the same settings")
    if before["git_ignore_applied"] != after["git_ignore_applied"]:
        raise ValueError("Baseline uses different Git ignore behavior; rescan in the same Git context")
    old_files = {f["path"]: f for f in before["files"]}
    new_files = {f["path"]: f for f in after["files"]}
    common = old_files.keys() & new_files.keys()
    unread = {p for p in common if not old_files[p]["content_scanned"] or not new_files[p]["content_scanned"]}

    def index(report):
        return Counter({(m["path"], m["kind"], m["fingerprint"]): m["count"] for m in report["marker_index"] if m["path"] not in unread})

    old_markers, new_markers = index(before), index(after)

    def details(changes, report):
        samples = {(m["path"], m["kind"], m["fingerprint"]): m for m in report["markers"]}
        return [{"path": path, "kind": kind, "fingerprint": fingerprint, "count": count,
                 "text": samples.get((path, kind, fingerprint), {}).get("text"),
                 "line": samples.get((path, kind, fingerprint), {}).get("line")}
                for (path, kind, fingerprint), count in sorted(changes.items())]

    old_findings = {f["id"]: f for f in before["findings"]}
    new_findings = {f["id"]: f for f in after["findings"]}
    content_checks = {"readme-install", "readme-usage", "manifest-valid", "python-version", "node-test-script", "rust-edition", "go-version"}
    def reliable(finding):
        return finding["check"] not in content_checks or finding["path"] not in unread

    warnings = []
    if unread:
        warnings.append("Marker/content-finding changes were not compared for files whose content was unread in either scan.")
    if before.get("warnings") or after.get("warnings"):
        warnings.append("One or both scans reported read errors; inventory changes may be incomplete.")
    return {
        "score_delta": after["score"] - before["score"] if after["score"] is not None and before["score"] is not None else None,
        "bytes_delta": after["total_bytes"] - before["total_bytes"],
        "added_files": sorted(new_files.keys() - old_files.keys()),
        "removed_files": sorted(old_files.keys() - new_files.keys()),
        "grown_files": sorted([{"path": p, "before_bytes": old_files[p]["bytes"], "after_bytes": new_files[p]["bytes"], "delta": new_files[p]["bytes"] - old_files[p]["bytes"]} for p in common if new_files[p]["bytes"] > old_files[p]["bytes"]], key=lambda f: (-f["delta"], f["path"])),
        "new_markers": details(new_markers - old_markers, after),
        "resolved_markers": details(old_markers - new_markers, before),
        "new_findings": [new_findings[key] for key in sorted(new_findings.keys() - old_findings.keys()) if reliable(new_findings[key])],
        "resolved_findings": [old_findings[key] for key in sorted(old_findings.keys() - new_findings.keys()) if reliable(old_findings[key])],
        "uncompared_content_files": sorted(unread), "warnings": warnings,
    }
