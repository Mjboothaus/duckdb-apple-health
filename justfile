# DataBooth/duckdb-apple-health
# Mac-first workflows. Recipes that need the C-API template no-op with a hint
# until `Makefile` from extension-template-c is in the tree.
#
#   just              # list
#   just fixture      # synthetic export.xml + zip + golden csv
#   just configure    # template venv + platform (after template is vendored)
#   just debug
#   just test
#   just demo         # unsigned LOAD + scan fixture

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

python := env_var_or_default("PYTHON", "python3")
duckdb := env_var_or_default("DUCKDB", "duckdb")
gen    := env_var_or_default("GEN", "ninja")

ext_debug   := "build/debug/extension/apple_health/apple_health.duckdb_extension"
ext_release := "build/release/extension/apple_health/apple_health.duckdb_extension"

# Prefer debug binary if present.
ext := if path_exists(ext_debug) { ext_debug } else { ext_release }

# ── meta ────────────────────────────────────────────────────────────────────

default:
    @just --list

# Host toolchain check (does not require the C template).
check-tools:
    @echo "== tools =="
    @command -v {{python}} >/dev/null && {{python}} --version
    @command -v cmake >/dev/null && cmake --version | head -1
    @command -v clang >/dev/null && clang --version | head -1
    @command -v just >/dev/null && just --version
    @if command -v {{duckdb}} >/dev/null; then {{duckdb}} --version; else echo "duckdb: MISSING (install 2.0-dev / preview)"; fi
    @command -v ninja >/dev/null && echo "ninja: $(ninja --version)" || echo "ninja: optional"
    @command -v ccache >/dev/null && echo "ccache: $(ccache --version | head -1)" || echo "ccache: optional"
    @test -f Makefile && echo "template Makefile: present" || echo "template Makefile: NOT YET (vendor extension-template-c)"

# ── fixtures (Python only) ──────────────────────────────────────────────────

# Write test/data/export.xml, export.zip, and golden CSVs.
fixture:
    {{python}} scripts/make_fixture.py

# ── C-API template build ────────────────────────────────────────────────────

[private]
need-template:
    @test -f Makefile || { echo "No Makefile. Vendor duckdb/extension-template-c and rename the extension to apple_health."; exit 1; }

configure: need-template
    make configure

debug: need-template
    GEN={{gen}} make debug

release: need-template
    GEN={{gen}} make release

test: need-template
    make test_debug

test-release: need-template
    make test_release

clean:
    @if test -f Makefile; then make clean; else echo "nothing to clean (no template Makefile)"; fi
    rm -rf test/data/export.xml test/data/export.zip test/data/golden

# ── DuckDB 2.0-dev, unsigned ────────────────────────────────────────────────

# Interactive unsigned shell with the extension loaded when the binary exists.
duckdb: fixture
    @if test -f "{{ext}}"; then \
      {{duckdb}} -unsigned -cmd "LOAD '{{ext}}';"; \
    else \
      echo "Extension binary not built. {{ext}} missing."; \
      echo "Running unsigned duckdb without LOAD. After week-1 spike: just debug && just duckdb"; \
      {{duckdb}} -unsigned; \
    fi

# One-shot scan of the synthetic zip (fails until TFs exist — that is the spike).
demo: fixture
    @test -f "{{ext}}" || { echo "Build first: just debug"; exit 1; }
    {{duckdb}} -unsigned -c "LOAD '{{ext}}'; SELECT type_short, unit, value, value_text, start_date FROM read_apple_health('test/data/export.zip') ORDER BY start_date, type_short;"

demo-xml: fixture
    @test -f "{{ext}}" || { echo "Build first: just debug"; exit 1; }
    {{duckdb}} -unsigned -c "LOAD '{{ext}}'; SELECT count(*) AS n FROM read_apple_health('test/data/export.xml');"

# Parser CLI path if the TF spike is blocked (src/parse_health as a standalone later).
parse-cli:
    @test -x build/debug/parse_health || { echo "No parse_health CLI yet."; exit 1; }
    build/debug/parse_health test/data/export.xml
