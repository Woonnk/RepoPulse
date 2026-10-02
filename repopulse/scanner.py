"""Read-only inventory. No project code or dependency installers are executed."""

from collections import Counter
from pathlib import Path
import os
import re
import subprocess
import hashlib

from .checks import analyze
from .config import validate


EXCLUDED = {".git", ".repopulse", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache", ".mypy_cache"}
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".c": "C", ".swift": "Swift",
    ".kt": "Kotlin", ".html": "HTML", ".css": "CSS", ".sh": "Shell",
}
MANIFESTS = {"pyproject.toml", "requirements.txt", "setup.py", "package.json", "Cargo.toml", "go.mod", "Gemfile", "composer.json", "pom.xml", "build.gradle"}
MARKER = re.compile(r"\b(TODO|FIXME)\b[:\s-]*(.*)")


def _git_files(root):
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, check=True, timeout=10)
        if Path(os.fsdecode(top.stdout).strip()).resolve() != root:
            return None
        result = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"], capture_output=True, check=True, timeout=30)
        return sorted({os.fsdecode(p) for p in result.stdout.split(b"\0") if p})
    except (OSError, subprocess.SubprocessError):
        return None


def scan(path, *, large_bytes=1_000_000, max_read_bytes=1_000_000, max_markers=200, exclude=(), enabled_checks=None):
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    settings = validate({"large_bytes": large_bytes, "max_read_bytes": max_read_bytes,
                         "max_markers": max_markers, "exclude": list(exclude),
                         **({"enabled_checks": list(enabled_checks)} if enabled_checks is not None else {})})
    excluded = EXCLUDED | set(exclude)
    def is_excluded(name):
        return name in excluded or name.endswith(".egg-info")

    warnings = []
    candidates = _git_files(root)
    git_aware = candidates is not None
    if candidates is None:
        candidates = []
        def walk_error(error):
            warnings.append(f"Could not list directory: {error.filename}")
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if not is_excluded(d) and not (Path(directory) / d).is_symlink())
            candidates.extend((Path(directory) / name).relative_to(root).as_posix() for name in sorted(files))

    files = []
    languages = Counter()
    large_files = []
    markers = []
    marker_count = 0
    skipped_content = 0
    total_bytes = 0
    contents = {}
    inventory = []
    marker_index = Counter()
    for name in sorted(candidates):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or any(is_excluded(p) for p in relative.parts):
            continue
        target = root / relative
        # Reject symlinked ancestors as well as files, including tracked symlinks.
        if any((root.joinpath(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
            continue
        try:
            if not target.is_file():
                continue
            size = target.stat().st_size
            name = relative.as_posix()
            files.append(name)
            record = {"path": name, "bytes": size, "content_scanned": False}
            inventory.append(record)
            total_bytes += size
            if relative.suffix.lower() in LANGUAGES:
                languages[LANGUAGES[relative.suffix.lower()]] += 1
            if size >= large_bytes:
                large_files.append({"path": name, "bytes": size})
            if size > max_read_bytes:
                skipped_content += 1
                continue
            with target.open("rb") as handle:
                data = handle.read(max_read_bytes + 1)
            if len(data) > max_read_bytes or b"\0" in data:
                skipped_content += 1
                continue
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                skipped_content += 1
                continue
            record["content_scanned"] = True
            if relative.name in MANIFESTS or relative.name.lower() in ("readme", "readme.md", "readme.rst", "readme.txt"):
                contents[name] = content
            for line_number, line in enumerate(content.splitlines(), 1):
                match = MARKER.search(line)
                if match:
                    marker_count += 1
                    fingerprint = hashlib.sha256(match[2].strip().encode("utf-8")).hexdigest()
                    marker_index[(name, match[1], fingerprint)] += 1
                    if len(markers) < max_markers:
                        markers.append({"path": name, "line": line_number, "kind": match[1], "text": match[2][:240], "fingerprint": fingerprint})
        except OSError as error:
            warnings.append(f"Could not read {name}: {error.strerror}")

    checks, score, projects, findings = analyze(files, contents, large_files, settings["enabled_checks"])
    return {
        "schema_version": 2, "project": root.name,
        "file_count": len(files), "total_bytes": total_bytes,
        "git_ignore_applied": git_aware,
        "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
        "dependency_files": [n for n in files if Path(n).name in MANIFESTS],
        "top_level": dict(sorted(Counter(n.split("/")[0] if "/" in n else "(root files)" for n in files).items())),
        "large_files": sorted(large_files, key=lambda f: (-f["bytes"], f["path"])),
        "markers": markers, "marker_count": marker_count,
        "skipped_content_files": skipped_content, "warnings": warnings,
        "checks": checks, "score": score,
        "projects": projects, "findings": findings, "files": inventory,
        "marker_index": [{"path": path, "kind": kind, "fingerprint": fingerprint, "count": count}
                         for (path, kind, fingerprint), count in sorted(marker_index.items())],
        "settings": {key: value for key, value in settings.items() if key not in ("fail_on", "fail_under")},
    }
