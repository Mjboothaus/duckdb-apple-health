.PHONY: clean clean_all

PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Main extension configuration
EXTENSION_NAME=apple_health

# Set to 1 to enable Unstable API (binaries will only work on TARGET_DUCKDB_VERSION, forwards compatibility will be broken)
# WARNING: When set to 1, the duckdb_extension.h from the TARGET_DUCKDB_VERSION must be used, using any other version of
#          the header is unsafe.
USE_UNSTABLE_C_API=0

# DuckDB C-API version baked into extension metadata (must be a parseable vMAJOR.MINOR.PATCH).
# Headers are refreshed from DUCKDB_HEADER_REF (branch/tag). DuckDB 2.0 alpha still exposes
# stable C API 1.5.6 on the v2.0-cyanoptera branch — see docs/ROADMAP.md.
# Override: make debug TARGET_DUCKDB_VERSION=v1.2.0 DUCKDB_HEADER_REF=v1.2.0
TARGET_DUCKDB_VERSION ?= v1.5.6
DUCKDB_HEADER_REF ?= v2.0-cyanoptera

all: configure release

# Include makefiles from DuckDB
include extension-ci-tools/makefiles/c_api_extensions/base.Makefile
include extension-ci-tools/makefiles/c_api_extensions/c_cpp.Makefile

configure: venv platform extension_version

debug: build_extension_library_debug build_extension_with_metadata_debug
release: build_extension_library_release build_extension_with_metadata_release

test: test_debug
test_debug: test_extension_debug
test_release: test_extension_release

clean: clean_build clean_cmake
	@rm -f build/debug/parse_health build/release/parse_health
clean_all: clean clean_configure

# Standalone streaming XML parser CLI (no DuckDB). Used for Gate 4+.
# zlib: system -lz; optional Homebrew prefix via ZLIB_PREFIX.
ZLIB_PREFIX ?= $(shell brew --prefix zlib 2>/dev/null)
ZLIB_CFLAGS = $(if $(ZLIB_PREFIX),-I$(ZLIB_PREFIX)/include,)
ZLIB_LIBS = $(if $(ZLIB_PREFIX),-L$(ZLIB_PREFIX)/lib,) -lz

.PHONY: parse_health_cli
parse_health_cli:
	@mkdir -p build/debug
	$(CC) -std=c11 -Wall -Wextra -O2 -I src $(ZLIB_CFLAGS) -o build/debug/parse_health \
		src/parse_health.c src/zip_source.c src/parse_health_main.c $(ZLIB_LIBS)

# ── DuckDB 2.0-alpha helpers ────────────────────────────────────────────────
# Headers come from DUCKDB_HEADER_REF; metadata uses TARGET_DUCKDB_VERSION (semver).
.PHONY: headers-alpha debug-alpha release-alpha
headers-alpha: check_configure
	@echo "Fetching C API headers from duckdb/$(DUCKDB_HEADER_REF)…"
	$(PYTHON_VENV_BIN) -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/duckdb/duckdb/$(DUCKDB_HEADER_REF)/src/include/duckdb.h', 'duckdb_capi/duckdb.h')"
	$(PYTHON_VENV_BIN) -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/duckdb/duckdb/$(DUCKDB_HEADER_REF)/src/include/duckdb_extension.h', 'duckdb_capi/duckdb_extension.h')"
	@rg -n "DUCKDB_EXTENSION_API_VERSION_(MAJOR|MINOR|PATCH)" duckdb_capi/duckdb_extension.h | head -5 || true

debug-alpha: headers-alpha
	$(MAKE) debug TARGET_DUCKDB_VERSION=$(TARGET_DUCKDB_VERSION)

# SQLLogic (`make test_debug`) needs configure/venv duckdb that can load C API ≥ TARGET.
# After switching to 2.0-alpha metadata, upgrade the template venv once:
#   ./configure/venv/bin/python -m pip install --pre --upgrade "duckdb>=1.6.0.dev0"

release-alpha: headers-alpha
	$(MAKE) release TARGET_DUCKDB_VERSION=$(TARGET_DUCKDB_VERSION)

