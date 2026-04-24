"""
Centralized version resolution for the brainana/nhp_mri_prep package.

Priority order:
1. BRAINANA_IMAGE_TAG env var — baked in at Docker build time via
   ``--build-arg BRAINANA_VERSION=<tag>``, so Docker-run reports show the
   actual image tag rather than the generic Python package version.
2. importlib.metadata — installed package version from pyproject.toml.
3. "0.0.0" fallback — uninstalled editable-src runs (e.g. bare ``python -c``).

All internal code should call ``get_version()`` rather than reading
``__version__`` or importing from ``importlib.metadata`` directly.
"""

import os
from importlib.metadata import version, PackageNotFoundError


def get_version() -> str:
    """Return the effective brainana version string."""
    tag = os.environ.get("BRAINANA_IMAGE_TAG", "").strip()
    if tag:
        return tag
    try:
        return version("brainana")
    except PackageNotFoundError:
        return "0.0.0"
