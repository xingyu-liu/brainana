"""Version consistency guards for brainana.

Ensures ``get_version()`` reflects ``pyproject.toml`` and that installed
dist-info metadata stays aligned after editable installs.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest
import tomllib

from nhp_mri_prep.version import get_version

REPO = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    with open(REPO / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_get_version_reads_pyproject():
    """get_version() must match pyproject.toml when running from the source tree."""
    assert get_version() == _pyproject_version()


def test_dist_info_matches_pyproject():
    """Editable dist-info must match pyproject.toml (run ``uv pip install -e .`` if stale)."""
    expected = _pyproject_version()
    try:
        installed = version("brainana")
    except PackageNotFoundError:
        pytest.skip("brainana not installed")
    assert installed == expected, (
        f"dist-info stale: {installed!r} != {expected!r}; run: uv pip install -e ."
    )
