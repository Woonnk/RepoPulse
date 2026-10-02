# Verification

## Local Environment

Linux, Python 3.12.14, Node 24.19.0. These results are local evidence, not a claim
that the GitHub Actions matrix has run.

## Passed

- All 40 unit/integration tests pass, covering Python/Node/Rust/Go fixtures, nested project detection,
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

## Pending

- Native Windows/macOS behavior and Python 3.10/3.11/3.13 are configured in the
  nine-job GitHub Actions matrix and remain unverified until those jobs run.
- Actual Chromium rendering/interaction, mobile screenshots, and CSP enforcement
  remain unverified locally. The available Playwright runner had no browser binary;
  downloading Chromium failed because the supplied download was not a valid ZIP.
  No browser success or visual QA is claimed.
- The browser CI job checks 1440/390/320-pixel widths, page overflow, severity/search
  filters, file pagination/sorting, source links, marker rendering, comparison and
  empty states, keyboard tabs, script injection, and absence of HTTP requests.
  It uploads generated reports/screenshots as evidence, including on failures.

## Reproduce

```sh
python -m unittest discover -s tests -v
node --check repopulse/report.js
node --check scripts/verify_browser.cjs
python -m pip install build
python -m build
# Run the following two commands inside a clean activated virtual environment:
python -m pip install dist/repopulse-0.2.0-py3-none-any.whl
python scripts/verify_install.py
python -m repopulse . --fail-under 100 --fail-on warning
```

For browser setup and commands, see [CONTRIBUTING.md](../CONTRIBUTING.md).
Output directories for the fixture generator/browser runner must be fresh.

Reports are heuristic and may be partial. A passing repository basics score or
test suite is not a security audit, proof of coverage, or a verified license review.
