"""
Centralized version resolution for the brainana/nhp_mri_prep package.

Priority order:
1. BRAINANA_IMAGE_TAG env var — baked in at Docker build time via
   ``--build-arg BRAINANA_VERSION=<tag>``, so Docker-run reports show the
   actual image tag rather than the generic Python package version.
2. pyproject.toml at repo root — when running from the source tree (editable
   dev / local Nextflow without Docker); avoids stale dist-info after a bump.
3. importlib.metadata — installed package version from pyproject.toml.
4. "0.0.0" fallback — uninstalled editable-src runs (e.g. bare ``python -c``).

All internal code should call ``get_version()`` rather than reading
``__version__`` or importing from ``importlib.metadata`` directly.
"""

import os
import tomllib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path


def _pyproject_version() -> str | None:
    """Return version from repo-root pyproject.toml, or None if unavailable."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return None


def get_version() -> str:
    """Return the effective brainana version string."""
    tag = os.environ.get("BRAINANA_IMAGE_TAG", "").strip()
    if tag:
        return tag
    pyproject_version = _pyproject_version()
    if pyproject_version:
        return pyproject_version
    try:
        return version("brainana")
    except PackageNotFoundError:
        return "0.0.0"
