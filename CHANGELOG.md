# Changelog

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
  report tests and screenshot artifacts. Remote CI results are pending publication.
- Python 3.10 uses the conditional tomli dependency; Python 3.11+ uses stdlib TOML.

Schema v1 snapshots are not compatible with comparisons. Generate a new baseline.
Existing terminal, Markdown, score threshold, and non-overwriting output behavior remain.

## 0.1.0

- Initial local inventory, repository basics score, markers, and text/Markdown/JSON reports.
