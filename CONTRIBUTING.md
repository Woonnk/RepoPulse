# Contributing

Small, focused contributions are welcome. Open an issue describing the problem
before starting large changes. Include a reproducible example for bug reports;
remove secrets and private source code first.

## Development

Python 3.10 or newer is required. Python 3.10 installs `tomli`; newer versions
use the standard library TOML parser. No project dependencies are installed during scans.

```sh
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

Add regression tests for behavior changes. Keep reports deterministic and scans
read-only. Do not introduce network requests or execute scanned project code.
The score measures only the presence of repository basics, not security or quality.

## Release checks

Build and install the wheel, then run the smoke checks outside the source import path:

```sh
python -m pip install build
python -m build
python -m pip install --force-reinstall dist/repopulse-0.2.0-py3-none-any.whl
python scripts/verify_install.py
```

Browser checks use Playwright as a development-only dependency:

```sh
npm install --no-save --prefix .repopulse/browser playwright@1.62.1
node .repopulse/browser/node_modules/playwright/cli.js install chromium
```

Set `REPOPULSE_PLAYWRIGHT_MODULE` to the absolute path of
`.repopulse/browser/node_modules/playwright`, then run:

```sh
node scripts/verify_browser.cjs .repopulse/browser-results
```

The output directory must be fresh for each browser run. On Linux CI, use
`install --with-deps chromium` to install browser system dependencies too.
Use `REPOPULSE_PYTHON` to select the fixture generator's Python executable.
Browser tests cover local-file operation, filters, pagination, keyboard tabs,
responsive widths, comparison/empty states, safe rendering, and no network requests.
