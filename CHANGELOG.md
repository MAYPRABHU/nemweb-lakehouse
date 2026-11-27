# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-25

### Added

- Incremental ingestion of AEMO NEMWeb `DispatchIS_Reports` and `Dispatch_SCADA` from
  `/Reports/Current` (latest 5-minute files) and `/Reports/Archive` (daily nested zips).
- Bronze layer: raw zips saved to disk exactly as downloaded.
- Silver layer in DuckDB: `dispatch_price`, `dispatch_regionsum` and `dispatch_unit_scada`,
  upserted on MMS natural keys, with automatic schema evolution when AEMO adds columns.
- Gold views: `daily_region_price`, `daily_region_demand` and `daily_unit_energy`.
- `meta.processed_files` manifest so re-runs skip already-loaded files (idempotent).
- Data quality checks: duplicate keys, 5-minute price interval completeness, null prices.
- `nemweb` CLI with `run`, `backfill`, `check`, `summary` and `sql` commands.
- HTTP fetching with retries and exponential backoff.
- Test suite using generated NEMWeb-style zips (no network needed).
- CI (lint, format check, tests with coverage) and a weekly live smoke test against NEMWeb.
- Pre-commit hooks (ruff lint + format, file hygiene) and Dependabot for pip and GitHub Actions.
- CI test matrix on both Ubuntu and Windows.
- CLI tests using `--source-dir` (no network needed)
### Fixed

- Windows: local file paths are now reduced to a bare file name, so bronze copies are written
  to `data/bronze/` instead of overwriting the source zip, and the manifest stores file names
  rather than full local paths.

### Changed

- `pyproject.toml` uses an SPDX `license` string (the table form is deprecated in setuptools).

[Unreleased]: https://github.com/MAYPRABHU/nemweb-lakehouse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MAYPRABHU/nemweb-lakehouse/releases/tag/v0.1.0
