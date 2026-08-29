.PHONY: clean clean_all

PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Main extension configuration
EXTENSION_NAME=apple_health

# Set to 1 to enable Unstable API (binaries will only work on TARGET_DUCKDB_VERSION, forwards compatibility will be broken)
# WARNING: When set to 1, the duckdb_extension.h from the TARGET_DUCKDB_VERSION must be used, using any other version of
#          the header is unsafe.
USE_UNSTABLE_C_API=0

# The DuckDB version to target
TARGET_DUCKDB_VERSION=v1.2.0

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
