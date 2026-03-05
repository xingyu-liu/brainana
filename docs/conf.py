# Configuration file for the Sphinx documentation builder.
# See https://www.sphinx-doc.org/en/master/usage/configuration.html
from pathlib import Path
import tomllib

project = "brainana"
copyright = "2025, brainana developers"
author = "brainana developers"

# Version from pyproject.toml (single source of truth)
_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
with open(_pyproject, "rb") as f:
    _project = tomllib.load(f).get("project", {})
release = _project.get("version", "0.0.0")
version = ".".join(release.split(".")[:2])  # e.g. "1.0" from "1.0.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Logo is optional so RTD (and local docs-only) builds succeed without the asset
_logo = Path(__file__).resolve().parent / "_static" / "brainana_logo_side.png"
html_logo = str(_logo) if _logo.exists() else None
html_theme_options = {"logo_only": True} if html_logo else {}
html_show_sourcelink = False
html_title = "brainana"
html_short_title = "brainana"

myst_enable_extensions = ["deflist"]

# Intersphinx for Python/NumPy links
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}
