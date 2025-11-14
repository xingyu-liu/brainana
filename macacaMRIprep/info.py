"""
Package metadata and version information.
"""

import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

def get_version_from_pyproject():
    """Get version from pyproject.toml."""
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]
    return "0.1.0"  # fallback

# Package version
__version__ = get_version_from_pyproject()

# For backward compatibility
VERSION = __version__ 