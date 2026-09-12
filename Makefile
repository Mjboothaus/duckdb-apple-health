.PHONY: clean clean_all

PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Main extension configuration
EXTENSION_NAME=healthkit_export

# Set to 1 to enable Unstable API (binaries will only work on TARGET_DUCKDB_VERSION, forwards compatibility will be broken)
# WARNING: When set to 1, the duckdb_extension.h from the TARGET_DUCKDB_VERSION must be used, using any other version of
#          the header is unsafe.
USE_UNSTABLE_C_API=0

# Stable C extension API version stamped into extension metadata (NOT the DuckDB release tag).
# Community CI hosts only load C-API extensions built for ≤ v1.2.0. Match extension-template-c.
# The DuckDB *release* used to build/test is set separately in MainDistributionPipeline.yml
# (duckdb_version, currently v1.5.5).
# Refresh vendored headers: make update_duckdb_headers
# Optional 2.0-alpha experiments: make headers-alpha debug-alpha (requires USE_UNSTABLE_C_API=1).
TARGET_DUCKDB_VERSION=v1.2.0
# Header ref for optional alpha helpers only (do not use for community/stable builds).
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

# ── DuckDB 2.0-alpha helpers (experimental; not for community publish) ──────
# These pull unstable headers and must be paired with USE_UNSTABLE_C_API=1.
# Stable community builds use TARGET_DUCKDB_VERSION=v1.2.0 + update_duckdb_headers.
.PHONY: headers-alpha debug-alpha release-alpha
headers-alpha: check_configure
	@echo "Fetching unstable C API headers from duckdb/$(DUCKDB_HEADER_REF)…"
	$(PYTHON_VENV_BIN) -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/duckdb/duckdb/$(DUCKDB_HEADER_REF)/src/include/duckdb.h', 'duckdb_capi/duckdb.h')"
	$(PYTHON_VENV_BIN) -c "import urllib.request;urllib.request.urlretrieve('https://raw.githubusercontent.com/duckdb/duckdb/$(DUCKDB_HEADER_REF)/src/include/duckdb_extension.h', 'duckdb_capi/duckdb_extension.h')"
	@rg -n "DUCKDB_EXTENSION_API_VERSION_(MAJOR|MINOR|PATCH)" duckdb_capi/duckdb_extension.h | head -5 || true

debug-alpha: headers-alpha
	$(MAKE) debug USE_UNSTABLE_C_API=1 TARGET_DUCKDB_VERSION=$(DUCKDB_HEADER_REF)

# SQLLogic after alpha metadata needs a matching pre-release duckdb in the venv, e.g.:
#   ./configure/venv/bin/python -m pip install --pre --upgrade "duckdb>=1.6.0.dev0"

release-alpha: headers-alpha
	$(MAKE) release USE_UNSTABLE_C_API=1 TARGET_DUCKDB_VERSION=$(DUCKDB_HEADER_REF)

