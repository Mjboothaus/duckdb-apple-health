# Contributing

Thanks for interest in `duckdb-apple-health`. This is a **v0.1.0-beta** C extension; small, focused changes are preferred.

## Before you start

1. Read [docs/DESIGN.md](docs/DESIGN.md) (locked decisions and hard rules).
2. Skim [ROADMAP.md](docs/ROADMAP.md) so work is not duplicated.
3. Never commit a real Apple Health export or other PHI.

## Dev setup (macOS)

```bash
git clone --recurse-submodules git@github.com:mjboothaus/duckdb-apple-health.git
cd duckdb-apple-health
brew install cmake ninja ccache just
just configure
just debug
just fixture
just pytest-ext
```

Optional notebook tooling:

```bash
uv sync
uv run marimo edit notebooks/explore_export.py
```

## Rules of thumb

- Parser (`parse_health.c`) and zip (`zip_source.c`) must **not** include DuckDB headers.
- Do not enable `USE_UNSTABLE_C_API` without maintainers agreeing.
- Do not switch to the unstable C++ `extension-template` as the default.
- Prefer the smallest diff that fixes or advances one concern.
- Australian English in docs; usual US-ish spelling in code identifiers is fine.

## Tests

```bash
just pytest-ext
```

Behavioural changes need fixture tests green. Optional real-export checks:

```bash
APPLE_HEALTH_EXPORT_ZIP=/path/to/export.zip just pytest-ext-real export_zip=/path/to/export.zip
```

Keep real zips **outside** the repo.

## Pull requests

- Feature/fix branch off `main`.
- Clear commit messages (what + why).
- Describe how you tested (`just debug`, `just pytest-ext`, manual SQL).
- Do not expand scope into routes/ECG/Wasm/community INSTALL unless the issue asks for it.

## Code layout

| Path | Role |
|---|---|
| `src/parse_health.*` | Streaming XML (no DuckDB) |
| `src/zip_source.*` | Zip/dir/file open (no DuckDB) |
| `src/apple_health_tf.c` | Table functions (DuckDB C API only) |
| `src/apple_health_extension.c` | Extension entrypoint |
| `tests/` | pytest correctness |
| `test/sql/` | SQLLogic samples |
| `scripts/make_fixture.py` | Synthetic export (no PHI) |

## Licence

By contributing you agree your changes are Apache-2.0, same as the project.
