"""Shared test setup: import path, config fixture, skip helper."""

import sys
from pathlib import Path

import pytest

# Make the package importable when running pytest from the repo root without
# installing it (pytest python/tests).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from irpanel.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def config():
    return load_config()


def skip_unless_exists(path, label):
    if not Path(path).exists():
        pytest.skip(f"{label} not present")
