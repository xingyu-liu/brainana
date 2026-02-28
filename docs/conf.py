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
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]
try:
    import myst_parser  # noqa: F401
    extensions.insert(0, "myst_parser")
except ImportError:
    pass

templates_path = ["_templates"]
source_suffix = {
    ".rst": "restructuredtext",
}
if "myst_parser" in extensions:
    source_suffix[".md"] = "markdown"

try:
    import sphinx_rtd_theme  # noqa: F401
    html_theme = "sphinx_rtd_theme"
except ImportError:
    html_theme = "alabaster"

html_static_path = ["_static"]
html_show_sourcelink = False
html_title = "brainana"
html_short_title = "brainana"

# MyST settings (Markdown in Sphinx) – only when myst_parser is loaded
# (linkify omitted: requires linkify-it-py; use deflist only for minimal deps)
if "myst_parser" in extensions:
    myst_enable_extensions = ["deflist"]

# Intersphinx for Python/NumPy/nibabel links
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}
