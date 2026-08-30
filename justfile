# DataBooth/duckdb-apple-health
# Portable workflows (bash). Makefile remains the source of truth for CMake /
# extension metadata; this file is the developer front door.
#
#   just              # list recipes
#   just bootstrap    # configure (if needed) + debug + fixture
#   just debug
#   just pytest-ext   # builds debug extension when missing
#   just demo         # unsigned LOAD + fixture scan
#   just build-db export_zip=/path/to/export.zip
#   just map-walks    # map from output/apple_health.duckdb
#
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

python := env_var_or_default("PYTHON", "python3")
duckdb := env_var_or_default("DUCKDB", "duckdb")
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
    {{duckdb}} -unsigned -cmd "LOAD '{{ext_debug}}';"

# One-shot scan of the synthetic zip.
demo: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT type_short, unit, value, value_text, start_date FROM read_apple_health('test/data/export.zip') ORDER BY start_date, type_short;"

demo-xml: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT count(*) AS n FROM read_apple_health('test/data/export.xml');"

# Streaming parser CLI (no DuckDB). Builds if missing. Accepts xml/zip/dir.
parse-cli path="test/data/export.xml": fixture
    @if ! test -x build/debug/parse_health; then make parse_health_cli; fi
    build/debug/parse_health {{path}}

parse-cli-zip: fixture
    @just parse-cli test/data/export.zip

parse-cli-dir: fixture
    @just parse-cli test/data

demo-workouts: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT activity_type_short, duration, total_distance, total_energy FROM apple_health_workouts('test/data/export.zip');"

demo-routes: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT workout_activity_type_short, gpx_path, source_name FROM apple_health_workout_routes('test/data/export.zip');"



# ── Local workout / GPS database ────────────────────────────────────────────

# Build output/apple_health.duckdb from a real export (Walking+Hiking by default).
build-db export_zip activities="Walking,Hiking": ensure-ext
    uv run python scripts/build_health_db.py {{export_zip}} --activities {{activities}}

# List walks/hikes from the local DB (build-db first).
list-walks limit="30":
    @test -f output/apple_health.duckdb || { echo "Missing output/apple_health.duckdb — run: just build-db export_zip=/path/to/export.zip"; exit 1; }
    {{duckdb}} output/apple_health.duckdb -c "SELECT activity_type_short AS activity, workout_start_date AS start, round(date_diff('second', workout_start_date, workout_end_date)/60.0, 1) AS mins, gpx_path FROM routes ORDER BY workout_start_date DESC NULLS LAST LIMIT {{limit}};"

# Map walks/hikes from the local DB (no zip scan).
map-walks:
    @test -f output/apple_health.duckdb || { echo "Missing output/apple_health.duckdb — run: just build-db export_zip=/path/to/export.zip"; exit 1; }
    uv run marimo edit notebooks/map_walks.py


demo-route-points: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT point_index, lat, lon, ele, time FROM apple_health_workout_route_points('test/data/export.zip') ORDER BY point_index;"

demo-summaries: fixture ensure-ext
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT date_components, apple_move_minutes, apple_move_time, active_energy_burned FROM apple_health_activity_summaries('test/data/export.xml') ORDER BY date_components;"

# Ad-hoc counts on a real export (path stays outside the repo).
demo-real export_zip: ensure-ext
    @test -f "{{export_zip}}" || { echo "export_zip not found: {{export_zip}}"; exit 1; }
    {{duckdb}} -unsigned -c "LOAD '{{ext_debug}}'; SELECT count(*) AS records FROM read_apple_health('{{export_zip}}'); SELECT count(*) AS workouts FROM apple_health_workouts('{{export_zip}}'); SELECT count(*) AS activity_summaries FROM apple_health_activity_summaries('{{export_zip}}');"

# Extension correctness tests (fixture). Builds debug extension if missing.
pytest-ext: ensure-ext
    uv run pytest -q

# Optional real-export smoke (path must stay outside the repo).
pytest-ext-real export_zip: ensure-ext
    APPLE_HEALTH_EXPORT_ZIP={{export_zip}} uv run pytest -q -m slow
