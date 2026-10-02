"""Validated TOML settings shared by the CLI and snapshots."""

from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10 uses the conditional package dependency.
    import tomli as tomllib


CHECK_IDS = (
    "readme", "license", "gitignore", "contributing", "tests", "ci",
    "readme-install", "readme-usage", "manifest-valid", "python-version",
    "node-test-script", "node-lockfile", "rust-edition", "go-version", "large-files",
)
DEFAULTS = {
    "large_bytes": 1_000_000,
    "max_read_bytes": 1_000_000,
    "max_markers": 200,
    "exclude": [],
    "enabled_checks": list(CHECK_IDS),
    "fail_under": None,
    "fail_on": None,
}


def validate(settings):
    unknown = set(settings) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown config keys: " + ", ".join(sorted(unknown)))
    result = {**DEFAULTS, **settings}
    for name in ("large_bytes", "max_read_bytes", "max_markers", "fail_under"):
        value = result[name]
        if name == "fail_under" and value is None:
            continue
        minimum = 0 if name in ("max_markers", "fail_under") else 1
        if type(value) is not int or value < minimum or (name == "fail_under" and value > 100):
            raise ValueError(f"{name} must be an integer >= {minimum}" + (" and <= 100" if name == "fail_under" else ""))
    excludes = result["exclude"]
    if not isinstance(excludes, list) or any(not isinstance(v, str) or not v or v in (".", "..") or any(c in v for c in "/\\\0") for v in excludes):
        raise ValueError("exclude must be an array of nonempty file/directory basenames")
    checks = result["enabled_checks"]
    if not isinstance(checks, list) or any(not isinstance(v, str) or v not in CHECK_IDS for v in checks):
        raise ValueError("enabled_checks must be an array of supported check IDs; use --list-checks")
    if result["fail_on"] not in (None, "info", "warning", "error"):
        raise ValueError("fail_on must be info, warning, or error")
    result["exclude"] = sorted(set(excludes))
    result["enabled_checks"] = sorted(set(checks))
    return result


def load_config(root, explicit=None, disabled=False):
    if disabled:
        return validate({})
    path = Path(explicit).expanduser() if explicit else Path(root) / "repopulse.toml"
    if explicit is None and not path.exists():
        return validate({})
    if path.is_symlink():
        raise ValueError(f"Configuration cannot be a symlink: {path}")
    try:
        if path.stat().st_size > 100_000:
            raise ValueError("Configuration exceeds 100,000 bytes")
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError(f"Could not load configuration {path}: {error}") from error
    if set(data) != {"scan"} or not isinstance(data["scan"], dict):
        raise ValueError("Configuration must contain only a [scan] table")
    return validate(data["scan"])
