# brainana documentation (Sphinx)

This directory is the Sphinx source for the user-facing documentation (Installation, Usage, Command-line reference, etc.), intended for **Read the Docs** or local HTML builds.

## Build locally

From the **repository root**:

```bash
uv pip install -e ".[docs]"   # or: pip install -e ".[docs]"
sphinx-build -b html doc doc/_build
```

Then open `doc/_build/index.html` in a browser.

## Structure

- `conf.py` — Sphinx configuration (theme, extensions, version).
- `index.rst` — Home page and table of contents.
- `installation.rst`, `usage_local.rst`, `command_line.rst`, `outputs.rst`, `faq.rst` — User guide.
- `other_docs.rst` — Links to design/planning docs in `docs/`.

Full plan (step-by-step for Read the Docs, versioning, custom domain): see **docs/DOCUMENTATION_PLAN.md**.
