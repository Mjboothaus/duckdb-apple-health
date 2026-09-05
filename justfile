# DataBooth/duckdb-apple-health
# Portable workflows (bash). Makefile remains the source of truth for CMake /
# extension metadata; this file is the developer front door.
#
#   just              # list recipes
#   just bootstrap    # configure (if needed) + debug + fixture
#   just debug / just debug-alpha   # stable C API; 2.0-alpha headers+CLI
#   just pytest-ext   # builds debug extension when missing
#   just demo         # unsigned LOAD + fixture scan (set DUCKDB=… for alpha CLI)
#   just duckdb-alpha # interactive shell with alpha CLI if installed
#   just build-db export_zip=/path/to/export.zip
#   just map-walks    # map from output/apple_health.duckdb
#   just geocode-places          # fill route_places (Nominatim)
#   just geocode-places limit=50
#
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

python := env_var_or_default("PYTHON", "python3")
# DuckDB CLI: override with DUCKDB=/path/to/duckdb. Default prefers 2.x alpha install if present.
duckdb := env_var_or_default("DUCKDB", if path_exists(home_directory() / ".duckdb/cli/latest/duckdb") == "true" { home_directory() / ".duckdb/cli/latest/duckdb" } else { "duckdb" })
gen    := env_var_or_default("GEN", "ninja")

ext_debug   := "build/debug/extension/apple_health/apple_health.duckdb_extension"
ext_release := "build/release/extension/apple_health/apple_health.duckdb_extension"

# Prefer debug binary if present.
# path_exists returns the strings "true"/"false"; if requires a comparison.
ext := if path_exists(ext_debug) == "true" { ext_debug } else { ext_release }

# ── meta ────────────────────────────────────────────────────────────────────

default:
    @just --list

# Host toolchain check (does not require a built extension).
check-tools:
    @echo "== tools =="
    @command -v {{python}} >/dev/null && {{python}} --version
    @command -v cmake >/dev/null && cmake --version | head -1
    @command -v clang >/dev/null && clang --version | head -1
    @command -v just >/dev/null && just --version
    @if command -v {{duckdb}} >/dev/null; then {{duckdb}} --version; else echo "duckdb: MISSING (install a CLI that loads unsigned extensions)"; fi
    @command -v ninja >/dev/null && echo "ninja: $(ninja --version)" || echo "ninja: optional"
    @command -v ccache >/dev/null && echo "ccache: $(ccache --version | head -1)" || echo "ccache: optional"
    @test -f Makefile && echo "template Makefile: present" || echo "template Makefile: MISSING"

# ── fixtures (Python only) ──────────────────────────────────────────────────

# Write test/data/export.xml, export.zip, and golden CSVs.
fixture:
    {{python}} scripts/make_fixture.py

# ── C-API template build ────────────────────────────────────────────────────

[private]
need-template:
    @test -f Makefile || { echo "No Makefile. Vendor duckdb/extension-template-c and rename the extension to apple_health."; exit 1; }

# Configure once after clone (venv, platform, extension version).
configure: need-template
    make configure

# Build debug extension binary + metadata under build/debug/.
debug: need-template
    GEN={{gen}} make debug

# Fetch DuckDB 2.0-alpha (cyanoptera) C API headers and rebuild debug extension.
# Metadata uses parseable TARGET_DUCKDB_VERSION (default v1.5.6). Requires alpha-capable CLI to LOAD.
debug-alpha: need-template
    GEN={{gen}} make debug-alpha

# Interactive unsigned shell using preferred duckdb CLI (alpha if installed).
duckdb-alpha: fixture ensure-ext
    @echo "Using: {{duckdb}}"
    @{{duckdb}} -c "SELECT version() AS duckdb_version;"
    {{duckdb}} -unsigned -cmd "LOAD '{{justfile_directory()}}/{{ext_debug}}';"


# Build release extension binary.
release: need-template
    GEN={{gen}} make release

# DuckDB SQLLogic / template tests (debug).
test: need-template
    make test_debug

test-release: need-template
    make test_release

# configure (if configure/ missing) + debug + fixture — first-time / CI-ish loop.
bootstrap: need-template
    @if [ ! -d configure ]; then just configure; else echo "configure/: present (skip make configure)"; fi
    just debug
    just fixture
    @echo "bootstrap ok — extension: {{ext_debug}}"

# Ensure debug extension exists (used by demos / pytest).
[private]
ensure-ext: need-template
    @if [ ! -f "{{ext_debug}}" ]; then \
      echo "Extension missing; running just debug…"; \
      just debug; \
    fi

clean:
    @if test -f Makefile; then make clean; else echo "nothing to clean (no template Makefile)"; fi
    rm -rf test/data/export.xml test/data/export.zip test/data/golden

# ── DuckDB unsigned ─────────────────────────────────────────────────────────

# Interactive unsigned shell with the extension loaded when the binary exists.
duckdb: fixture ensure-ext
    {{duckdb}} -unsigned -cmd "LOAD '{{justfile_directory()}}/{{ext_debug}}';"

# One-shot scan of the synthetic zip.
demo: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{justfile_directory()}}/{{ext_debug}}'; SELECT type_short, unit, value, value_text, start_date FROM read_apple_health('test/data/export.zip') ORDER BY start_date, type_short;"

demo-xml: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{justfile_directory()}}/{{ext_debug}}'; SELECT count(*) AS n FROM read_apple_health('test/data/export.xml');"

# Streaming parser CLI (no DuckDB). Builds if missing. Accepts xml/zip/dir.
parse-cli path="test/data/export.xml": fixture
    @if ! test -x build/debug/parse_health; then make parse_health_cli; fi
    build/debug/parse_health {{path}}

parse-cli-zip: fixture
    @just parse-cli test/data/export.zip

parse-cli-dir: fixture
    @just parse-cli test/data

demo-workouts: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{justfile_directory()}}/{{ext_debug}}'; SELECT activity_type_short, duration, total_distance, total_energy FROM apple_health_workouts('test/data/export.zip');"

demo-routes: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{justfile_directory()}}/{{ext_debug}}'; SELECT workout_activity_type_short, gpx_path, source_name FROM apple_health_workout_routes('test/data/export.zip');"



# ── Local workout / GPS database ────────────────────────────────────────────

# Build output/apple_health.duckdb from a real export (Walking+Hiking by default).
build-db export_zip activities="Walking,Hiking": ensure-ext
    uv run python scripts/build_health_db.py {{export_zip}} --activities {{activities}}

# List walks/hikes from the local DB (build-db first). Includes places when geocoded.
list-walks limit="30":
    @test -f output/apple_health.duckdb || { echo "Missing output/apple_health.duckdb — run: just build-db export_zip=/path/to/export.zip"; exit 1; }
    @{{duckdb}} output/apple_health.duckdb -c "SELECT r.activity_type_short AS activity, r.workout_start_date AS start, round(date_diff('second', r.workout_start_date, r.workout_end_date)/60.0, 1) AS mins, pl.start_place, pl.end_place, r.gpx_path FROM routes r LEFT JOIN route_places pl USING (gpx_path) ORDER BY r.workout_start_date DESC NULLS LAST LIMIT {{limit}};" 2>/dev/null \
      || {{duckdb}} output/apple_health.duckdb -c "SELECT activity_type_short AS activity, workout_start_date AS start, round(date_diff('second', workout_start_date, workout_end_date)/60.0, 1) AS mins, gpx_path FROM routes ORDER BY workout_start_date DESC NULLS LAST LIMIT {{limit}};"

# Reverse-geocode route start/end into gps.route_places (Nominatim + cache).
# Examples: just geocode-places   |   just geocode-places -- --limit 50   |   just geocode-places -- --all
geocode-places *args:
    @test -f output/apple_health.duckdb || { echo "Missing output/apple_health.duckdb — run: just build-db export_zip=/path/to/export.zip"; exit 1; }
    PYTHONPATH="{{justfile_directory()}}/python${PYTHONPATH:+:$PYTHONPATH}" uv run --project . python scripts/geocode_route_places.py {{args}}

