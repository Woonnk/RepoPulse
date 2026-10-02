# Verification

## Local Environment

Linux, Python 3.12.14, Node 24.19.0. Local checks are listed below;
the GitHub Actions results are recorded separately.

## Passed

- Version 0.3.0 adds tests for starter config creation/overwrite protection,
  new-finding thresholds and incompatible baselines, SARIF rule indices,
  severity, fingerprints, encoded paths, empty results, and unread coverage.
- SARIF exports with locationless, file, baseline, and empty results were
  validated locally against the [official OASIS SARIF 2.1.0 JSON schema](https://github.com/oasis-tcs/sarif-spec/blob/main/sarif-2.1/schema/sarif-schema-2.1.0.json).
  Actual uploads to third-party code-scanning services have not been tested.
- All 50 unit/integration tests pass, covering Python/Node/Rust/Go fixtures, nested project detection,
  malformed/unread manifests, documentation checks, config precedence/validation,
  selective checks, score/severity exit codes, Git ignore fallback, symlinks,
  binary/read limits, capped marker counts, and non-overwriting report exports.
- Snapshot tests cover duplicate marker counts, line shifts, file growth,
  inventory additions/removals, finding resolution, unread coverage, invalid or
  incompatible baselines, and independent snapshots without comparison history.
- HTML export tests verify script-injection escaping, literal placeholder data,
  trusted-script CSP hashing, and percent-encoded local source links.
- A wheel was built and installed into a clean virtual environment. Isolated
  imports from outside the source directory verified JSON, packaged HTML assets,
  baseline loading/comparison, threshold exit codes, and overwrite rejection.
- The source distribution was also built, installed with the available local
  build backend, and passed the same isolated-import smoke checks.
- JavaScript syntax checks pass for the report and browser test runner.
- RepoPulse's self-scan passes `--fail-under 100 --fail-on warning` using the
  included configuration to exclude deliberately incomplete test fixtures.

## GitHub Actions (0.2.0)

[Release checks run 37036562782](https://github.com/Woonnk/RepoPulse/actions/runs/37036562782)
passed all 10 jobs for commit `6187b005cf17227e62d53890dce40a0c77752505`.

- The nine-job matrix passed on Windows, macOS, and Ubuntu with Python
  3.10, 3.11, and 3.13, including all 40 tests, wheel/source-distribution
  installation smoke checks, and the repository self-scan.
- Chromium browser checks passed at 1440/390/320-pixel widths: page overflow, severity/search
  filters, file pagination/sorting, source links, marker rendering, comparison and
  empty states, keyboard tabs, script injection, and absence of HTTP requests.
  Generated reports and screenshots are available in the run's browser-evidence artifact.
- The first browser run exposed narrow-screen overflow. The report layout was
  corrected and the passing run above verified the fix. Browser verification
  was performed in CI because local Chromium installation was unavailable.

## Reproduce

```sh
python -m unittest discover -s tests -v
node --check repopulse/report.js
node --check scripts/verify_browser.cjs
python -m pip install build
python -m build
# Run the following two commands inside a clean activated virtual environment:
python -m pip install dist/repopulse-0.3.0-py3-none-any.whl
python scripts/verify_install.py
python -m repopulse . --fail-under 100 --fail-on warning
```

For browser setup and commands, see [CONTRIBUTING.md](../CONTRIBUTING.md).
Output directories for the fixture generator/browser runner must be fresh.
Current remote results are available in [GitHub Actions](https://github.com/Woonnk/RepoPulse/actions/workflows/tests.yml).

Reports are heuristic and may be partial. A passing repository basics score or
test suite is not a security audit, proof of coverage, or a verified license review.
