# Changelog

All notable changes to this project are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versioning: early **0.x** beta tags; breaking changes allowed until 1.0.

## [Unreleased]

### Fixed

- Zip DEFLATE inflate no longer stops early on `Z_BUF_ERROR` when the output buffer fills; require `Z_STREAM_END` and honour central-directory sizes for data-descriptor members. Real `export.zip` record counts now match bare `export.xml` (closes the HRV SDNN −2 gap).

### Changed

- justfile: `bootstrap`, auto-build debug before demos/`pytest-ext`, `demo-real export_zip=…`, clearer comments (Makefile still owns CMake/metadata).

### Planned

- Workout routes / GPX table functions (product focus — see ROADMAP)
- Streaming table-function execute (bounded memory)
- Named `types` / `start` / `end` parameters
- DuckDB 2.0 community packaging when C-API CI is ready

See [ROADMAP.md](ROADMAP.md).

## [0.1.0-beta] — 2026-08-29

First public **developer beta**.

### Added

- C extension on DuckDB stable C API (`apple_health`)
- `read_apple_health(path)` with TIMESTAMPTZ dates and value / value_text split
- `apple_health_workouts(path)` and `apple_health_activity_summaries(path)`
- Zip / directory / XML path support
- Synthetic fixtures, golden CSV, pytest vs `healthkit-to-sqlite`
- `just` recipes: build, demo, pytest-ext
- Optional marimo explorer notebook
- DESIGN, ROADMAP, RELEASE_NOTES, CONTRIBUTING, SECURITY

### Known limitations

- Parse buffers in bind (high RAM on multi-GB exports)
- Unsigned local load only
- Named scan filters not implemented
- Nested Correlation `Record` children intentionally skipped

Full notes: [RELEASE_NOTES.md](RELEASE_NOTES.md).

[Unreleased]: https://github.com/DataBooth/duckdb-apple-health/compare/v0.1.0-beta...HEAD
[0.1.0-beta]: https://github.com/DataBooth/duckdb-apple-health/releases/tag/v0.1.0-beta
