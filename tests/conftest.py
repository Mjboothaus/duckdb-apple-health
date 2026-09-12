"""Shared fixtures for extension correctness tests."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ZIP = REPO_ROOT / "test" / "data" / "export.zip"
FIXTURE_XML = REPO_ROOT / "test" / "data" / "export.xml"
GOLDEN_RECORDS = REPO_ROOT / "test" / "data" / "golden" / "records.csv"

EXT_CANDIDATES = [
    REPO_ROOT / "build/debug/extension/healthkit_export/healthkit_export.duckdb_extension",
    REPO_ROOT / "build/debug/healthkit_export.duckdb_extension",
    REPO_ROOT / "build/release/extension/healthkit_export/healthkit_export.duckdb_extension",
]


def find_extension() -> Path:
    for path in EXT_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "healthkit_export.duckdb_extension not found. Run `just debug` before tests."
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def extension_path() -> Path:
    return find_extension()


@pytest.fixture(scope="session")
def fixture_zip() -> Path:
    assert FIXTURE_ZIP.is_file(), f"missing fixture zip: {FIXTURE_ZIP}"
    return FIXTURE_ZIP


@pytest.fixture(scope="session")
def fixture_xml() -> Path:
    assert FIXTURE_XML.is_file(), f"missing fixture xml: {FIXTURE_XML}"
    return FIXTURE_XML


@pytest.fixture(scope="session")
def golden_records_csv() -> Path:
    assert GOLDEN_RECORDS.is_file(), f"missing golden csv: {GOLDEN_RECORDS}"
    return GOLDEN_RECORDS


@pytest.fixture
def con(extension_path: Path):
    """Fresh in-memory DuckDB with the unsigned healthkit_export extension loaded."""
    connection = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    connection.execute(f"LOAD '{extension_path.as_posix()}'")
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def real_export_zip() -> Path | None:
    """Optional real Health zip via APPLE_HEALTH_EXPORT_ZIP (never committed)."""
    raw = os.environ.get("APPLE_HEALTH_EXPORT_ZIP", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_file():
        pytest.skip(f"APPLE_HEALTH_EXPORT_ZIP set but not a file: {path}")
    return path
