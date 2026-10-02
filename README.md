# RepoPulse

Find out what a repository needs before you share it. RepoPulse scans local files
and explains missing documentation, project metadata, test setup, and dependency
lockfiles with concrete suggestions. Export to text, Markdown, JSON, or a standalone
HTML report, and compare scans to see what changed.

No accounts, API keys, network requests during scanning, or project code execution.
Python 3.11+ needs no runtime dependencies; Python 3.10 uses `tomli` for TOML parsing.

## Installation

Requires Python 3.10+. Download or clone this repository, open a terminal in it,
and install the local package:

```sh
python -m pip install .
repopulse /path/to/project
```

The project is not yet on PyPI. `pip install .` installs your local checkout.
From the checkout, Python 3.11+ can also run `python -m repopulse` without installing;
on Python 3.10, install the package first to obtain the TOML parser dependency.

## Usage

```sh
repopulse .
repopulse . --format markdown --output ../report.md
repopulse . --format json
repopulse . --format html --output ../report.html
repopulse . --exclude vendor --exclude coverage --large-bytes 500000
repopulse . --fail-under 80 --fail-on error
```

Open the HTML output in a browser. It has findings with fix suggestions, severity
and text filters, source-file links, file sorting/pagination, marker locations, and
baseline changes. Everything is embedded; no web server or CDN is required. Source
links use local file URLs and display line numbers; browsers do not jump to those
lines. Moved reports may need to be regenerated to refresh their source links.

All output files must be new. RepoPulse never overwrites source files or an existing
report. Reports are produced even when a CI threshold returns exit code 1.

## Actionable Findings

Each finding includes a check ID, severity, stable identity, available evidence,
and a suggested fix. Findings are advisory presence/text heuristics, not proof of
correct behavior. Examples:

| Evidence | Finding | Suggested next step |
| --- | --- | --- |
| README without a usage section | Documentation gap | Add a runnable example and expected output |
| Node project without a test script | Test setup gap | Add a command that runs the actual test suite |
| Node project without a lockfile | Reproducibility gap | Commit your package manager's lockfile |
| Python package without `requires-python` | Compatibility gap | Declare supported Python versions |
| Malformed project manifest | Parse error | Correct syntax or field types and rescan |

Python (`pyproject.toml`, `requirements.txt`, `setup.py`), Node (`package.json`),
Rust (`Cargo.toml`), and Go (`go.mod`) projects are detected at any depth. Python
and Node frameworks are reported only from recognized dependency declarations,
including FastAPI, Flask, Django, React, Vue, Next.js, and Express.
`requirements.txt` and `setup.py` identify Python projects but are not parsed or run.
Go checks recognize module/go directives; RepoPulse is not a full Go manifest validator.

```sh
repopulse --list-checks
repopulse . --check readme --check readme-install --check node-lockfile
```

Repeated `--check` options replace the configured check list. Disabling a check
removes its findings; disabling a repository basic also removes it from the score.

## Configuration

Place `repopulse.toml` at the root of the directory being scanned:

```toml
[scan]
exclude = ["vendor", "coverage"]
large_bytes = 1000000
max_read_bytes = 1000000
max_markers = 200
fail_under = 80
fail_on = "error"
# Optional: replace the default set of all checks.
# enabled_checks = ["readme", "readme-install", "tests", "node-lockfile"]
```

Use `--config path/to/custom.toml` for another file, or `--no-config` to ignore
automatic configuration. Numeric/threshold CLI options override config values;
`--exclude` entries are added to configured basename exclusions. `--fail-on none`
disables a configured severity threshold. Unknown keys and invalid types fail
with an error. An empty `enabled_checks = []` disables all findings and scoring.

The config included in this repository excludes `fixtures`: those test projects
intentionally omit metadata so the test suite can exercise findings.

## Compare Scans

Store snapshots under `.repopulse`, which is always excluded from scans:

```sh
mkdir .repopulse
repopulse . --snapshot .repopulse/before.json
# Make changes to your project, then:
repopulse . --baseline .repopulse/before.json --format html --output .repopulse/after.html
repopulse . --baseline .repopulse/before.json --format json --snapshot .repopulse/after.json
```

Comparisons show added/removed inventory entries, growing files, new/resolved
findings, new/resolved markers, and score/size changes. Marker identity uses path,
kind, and a hash of the full trimmed marker message, with duplicate counts.
Moving a marker to a different line does not count as a new marker; editing its
message or moving it to another file counts as resolution plus addition.
The complete hashed marker index is retained even when displayed snippets are capped.

Baselines must use schema version 2, the same project directory name, exclusions,
read limit, large-file threshold, enabled checks, and Git inventory mode. Directory
names are a lightweight check, not a unique repository identity. Choose the correct
baseline. Schema v1 snapshots need to be regenerated. Comparisons omit content
changes for files unread in either scan and report those paths.
Inventory removals mean deleted **or no longer included**: changed Git ignore rules
can also make a file disappear. Findings disappearing from the scan scope do not
prove the underlying issue was fixed. Review warnings from partial scans.

## Score and CI

Six repository basics contribute equally to readiness: root README, root license,
root `.gitignore`, contributing guide, test files, and a GitHub Actions workflow.
The percentage is rounded; it covers only enabled basics. If none are enabled,
the score is `null` and `--fail-under` is an error. Project-specific findings do not
change the score; use `--fail-on` to enforce them independently.

**A score of 100 does not establish code quality, security, test coverage, license
validity, or a working CI pipeline.** Tests are recognized by source filenames or
test directories containing recognized source files; tests are never executed.

```sh
repopulse . --fail-under 100 --fail-on warning
```

`--fail-on warning` fails for warning/error findings. `--fail-on info` fails for
any finding. Exit codes: `0` success; `1` failed score/severity threshold; `2` invalid
arguments, configuration, baseline, scan directory, or output write failure.
Read warnings do not change the exit code; inspect them when completeness matters.

## Scan Behavior

- At a Git repository root, tracked and untracked/non-ignored files are used.
  Tracked files remain included even when an ignore pattern matches.
- Without Git, outside a repo, or within a repo subdirectory, built-in exclusions
  apply. Custom `.gitignore` patterns are not parsed in that fallback. Every report
  states whether Git ignore rules were applied.
- `.git`, `.repopulse`, dependency/build directories, `*.egg-info`, and common
  caches are excluded. Custom exclusions are basenames, not glob patterns.
- Symlinks are not followed. Files over the read limit, binary files, and non-UTF-8
  files still contribute to inventory but are not searched for markers or parsed.
- TODO/FIXME matching is textual, not a comment parser. Strings/docs can match.
  One marker per matching line is counted. Default read limit: 1,000,000 bytes/file;
  default displayed marker cap: 200. Inventory and marker identities grow with
  repository size; RepoPulse targets source repositories, not entire drives.
- Scans are read-only but not atomic. Avoid concurrent modifications. Git commands
  have timeouts, and unreadable files/directories produce warnings.
- Reports/snapshots may contain private filenames, snippets, and manifest parser
  evidence; HTML also includes absolute local source links. Review before sharing.
  This is not a secrets detector or security audit.

JSON reports have `schema_version: 2`. They include inventory, markers/hashed marker
index, checks, findings, detected projects, effective scan settings, and optional
`comparison`. `--snapshot` writes the current scan without comparison history.

## Development and Verification

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The release workflow builds a wheel/sdist and runs fixture tests and installed-package
checks on Windows, macOS, and Linux with Python 3.10, 3.11, and 3.13. A separate
Chromium job verifies the standalone report on desktop/mobile and uploads screenshots.
See [verification notes](docs/VERIFICATION.md) for local results and pending remote
checks, and [CONTRIBUTING.md](CONTRIBUTING.md) for development commands.

Licensed under [MIT](LICENSE). Changes are recorded in [CHANGELOG.md](CHANGELOG.md).
