# Changelog

## [0.1.0] — 2026-09-06

### Added
- Core extension release tag path: `VERSION` = `0.1.0`, git tag `v0.1.0` for extension metadata.
- `just pytest-ext` / `pytest-ext-real` recipes for extension pytest.
- Docs: [CREATE_COMM_EXT.md](docs/CREATE_COMM_EXT.md) (community INSTALL migration).
- Companion package name **health-data-store** (optional; not required for extension use).

### Extension (Layer A)
- Table functions: `read_apple_health`, `apple_health_workouts`, `apple_health_activity_summaries`,
  `apple_health_workout_routes`, `apple_health_workout_route_points`.
- SQLLogic + fixture golden + healthkit-to-sqlite top-level compare green on freeze.

### Changed
- README / RELEASE_NOTES promote **v0.1.0** core vs optional add-ons.
- Honest performance limits retained (bind buffer; materialise for fast path).

### Not included in core binary
- Python maps/Photos/journeys/marimo (same repo, optional).
- Community `INSTALL`, streaming execute, named scan filters.

All notable changes to this project are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versioning: early **0.x** beta tags; breaking changes allowed until 1.0.

## [Unreleased]

### Changed
- Target DuckDB **2.0-alpha** C API headers (`v2.0-cyanoptera`) with extension metadata `v1.5.6`; `just debug-alpha` / alpha CLI support.

### Added

- `apple_health_workout_routes(path)` — WorkoutRoute + FileReference `gpx_path` with parent workout type/dates for joins

### Fixed

- Zip DEFLATE inflate no longer stops early on `Z_BUF_ERROR` when the output buffer fills; require `Z_STREAM_END` and honour central-directory sizes for data-descriptor members. Real `export.zip` record counts now match bare `export.xml` (closes the HRV SDNN −2 gap).

### Changed

- justfile: `bootstrap`, auto-build debug before demos/`pytest-ext`, `demo-real export_zip=…`, clearer comments (Makefile still owns CMake/metadata).

### Planned

- `apple_health_workout_route_points` GPX trkpt stream (see docs/ROADMAP)
- Streaming table-function execute (bounded memory)
- Named `types` / `start` / `end` parameters
- DuckDB 2.0 community packaging when C-API CI is ready

See [ROADMAP.md](docs/ROADMAP.md).

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

Full notes: [RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

[Unreleased]: https://github.com/Mjboothaus/duckdb-apple-health/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Mjboothaus/duckdb-apple-health/compare/v0.1.0-beta...v0.1.0
[0.1.0-beta]: https://github.com/Mjboothaus/duckdb-apple-health/releases/tag/v0.1.0-beta
