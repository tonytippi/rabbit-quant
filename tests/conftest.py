"""Shared test fixtures for Rabbit-Quant."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _set_test_env(tmp_path: Path) -> None:
    """Set environment variables for testing."""
    os.environ["DUCKDB_PATH"] = str(tmp_path / "test.duckdb")
    os.environ["LOG_LEVEL"] = "DEBUG"
    os.environ["LOG_PATH"] = str(tmp_path / "test.log")
