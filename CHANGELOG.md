# Changelog

## 0.3.0

- SARIF 2.1.0 export with rule metadata, severity, stable fingerprints, relative
  file locations, scan warnings, and baseline states for reliably compared findings.
- `--fail-on-new` severity thresholds for newly introduced findings, using a
  compatible baseline while preserving report exports and existing thresholds.
- `--init-config` creates a starter configuration without scanning or overwriting
  existing files. Config initialization is separate from scan/report options.
- Ten new regression tests and installed-package smoke checks for these features.
  JSON snapshot schema remains version 2; existing baselines remain compatible.

## 0.2.0

- Actionable findings with stable identities, evidence, severity, and suggested fixes.
- Python, Node, Rust, and Go manifest detection, including nested projects and
  framework evidence from Python/Node dependency declarations.
- Strict root or explicit TOML configuration with CLI overrides and selectable checks.
- Schema v2 JSON snapshots and baseline comparisons for inventory, file growth,
  findings, and marker counts. Marker identity is independent of line shifts and
  output caps; incomplete content coverage is reported instead of assumed resolved.
- Standalone HTML reports with source links, searchable findings, severity filters,
  sorted/paginated files, markers, changes, keyboard tabs, and responsive layout.
- Installed-wheel smoke checks and a Windows/macOS/Linux CI matrix, plus Chromium
  report tests and screenshot artifacts. All 10 GitHub Actions jobs passed;
  see [verification results](docs/VERIFICATION.md).
- Python 3.10 uses the conditional tomli dependency; Python 3.11+ uses stdlib TOML.

Schema v1 snapshots are not compatible with comparisons. Generate a new baseline.
Existing terminal, Markdown, score threshold, and non-overwriting output behavior remain.

## 0.1.0

- Initial local inventory, repository basics score, markers, and text/Markdown/JSON reports.
