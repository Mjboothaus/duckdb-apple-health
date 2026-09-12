# Changelog

## [0.2.0] — 2026-09-12

### Changed (breaking)
- Extension id and binary renamed **`apple_health` → `healthkit_export`**.
- Table functions renamed (no aliases):
  - `read_healthkit_export`
  - `healthkit_workouts`
  - `healthkit_activity_summaries`
  - `healthkit_workout_routes`
  - `healthkit_workout_route_points`
- Community listing will move to `extensions/healthkit_export/` (replace short-lived `apple_health` publish).

### Notes
- Repo remains `Mjboothaus/duckdb-healthkit-export`; optional local DB path remains `output/healthkit_store.duckdb`.
- Python package remains `healthkit-store`.

## [0.1.1] — 2026-09-10

### Added
- DuckDB **community extension** on **macOS** (`INSTALL healthkit_export FROM community`).
- Listing: [duckdb/community-extensions#2653](https://github.com/duckdb/community-extensions/pull/2653) (merged).
- `healthkit_store.connect_with_healthkit_export` / `load_healthkit_export` (community first, local unsigned fallback).
- Docs + `explore_export` notebook updated for community install.

### Fixed
- C extension ABI stamp: `TARGET_DUCKDB_VERSION=v1.2.0` (was incorrectly v1.5.6, which community hosts reject).

### Platforms
- Community CDN: `osx_arm64`, `osx_amd64` for DuckDB **v1.5.5**.

## [0.1.0] — 2026-09-06

### Added
- Core extension release tag path: `VERSION` = `0.1.0`, git tag `v0.1.0` for extension metadata.
- `just pytest-ext` / `pytest-ext-real` recipes for extension pytest.
- Docs: [CREATE_COMM_EXT.md](docs/CREATE_COMM_EXT.md) (community INSTALL migration).
- Companion package name **healthkit-store** (optional; not required for extension use).

### Extension (Layer A)
- Table functions: `read_healthkit_export`, `healthkit_workouts`, `healthkit_activity_summaries`,
  `healthkit_workout_routes`, `healthkit_workout_route_points`.
- SQLLogic + fixture golden + healthkit-to-sqlite top-level compare green on freeze.

### Changed
- README / RELEASE_NOTES promote **v0.1.0** core vs optional add-ons.
- Honest performance limits retained (bind buffer; materialise for fast path).

### Not included in core binary
- Python maps/Photos/journeys/marimo (same repo, optional).
- Streaming execute, named scan filters (community install arrived in **0.1.1**).

All notable changes to this project are documented here.
Format inspired by [Keep a Changelog](https://keepachangelog.com/).
Versioning: early **0.x** beta tags; breaking changes allowed until 1.0.

## [Unreleased]

### Planned

- Streaming table-function execute (bounded memory)
- Named `types` / `start` / `end` parameters
- Widen community platforms beyond macOS
- DuckDB 2.0 packaging when ready

See [ROADMAP.md](docs/ROADMAP.md).

## [0.1.0-beta] — 2026-08-29

First public **developer beta**.

### Added

- C extension on DuckDB stable C API (`healthkit_export`)
- `read_healthkit_export(path)` with TIMESTAMPTZ dates and value / value_text split
- `healthkit_workouts(path)` and `healthkit_activity_summaries(path)`
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

[Unreleased]: https://github.com/Mjboothaus/duckdb-healthkit-export/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Mjboothaus/duckdb-healthkit-export/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Mjboothaus/duckdb-healthkit-export/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Mjboothaus/duckdb-healthkit-export/compare/v0.1.0-beta...v0.1.0
[0.1.0-beta]: https://github.com/Mjboothaus/duckdb-healthkit-export/releases/tag/v0.1.0-beta
