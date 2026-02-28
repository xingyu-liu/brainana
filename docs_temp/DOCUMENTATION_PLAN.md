# brainana documentation plan

This guide is a step-by-step plan to complete and publish the brainana user docs (Sphinx, Read the Docs), with a clear split between **internal materials** (paper, methods text) and **user-facing docs**.

---

## Content model

| Location | Role |
|----------|------|
| **`docs_temp/paper/`** | Internal materials for writing the paper and QC boilerplate. You author here (e.g. `methods_reference.md`, `04-core-components-and-methods.md`). |
| **`docs/`** | User-facing Sphinx docs (Read the Docs). Single place users see installation, usage, and pipeline/methods. |
| **Rule** | User docs **mirror** the latest internal materials. When you change methods or steps, update `docs_temp/paper/` first, then propagate into `docs/` (and QC boilerplate). |

**Processing/methods:** All pipeline and methods content for users lives in **one page**: `docs/processing.rst`. It is kept in sync with `docs_temp/paper/methods_reference.md` (and optionally `04-core-components-and-methods.md`).

---

## Step-by-step plan

### Phase 1 – Content and structure (done or in progress)

| Step | Action | Status |--config_file
|------|--------|--------|
| 1.1 | Ensure `docs_temp/paper/methods_reference.md` is the canonical methods reference (paper + QC boilerplate). | ✓ |
| 1.2 | Single pipeline/methods page: `docs/processing.rst` contains full methods (overview, discovery, anatomical, functional, QC, summary table). No separate “methods reference” page. | ✓ |
| 1.3 | Point at internal materials from `processing.rst` (e.g. “See `docs_temp/paper/` for design and manuscript text”). | ✓ |
| 1.4 | When you add or change a pipeline step: update `methods_reference.md` → then `processing.rst` → then QC boilerplate (`boilerplate_methods.txt` / `reports.py`) so everything stays aligned. | Ongoing |

---

### Phase 2 – Sphinx setup

| Step | Action |
|------|--------|
| 2.1 | **Dependencies.** In `pyproject.toml`, add (or confirm) optional group: `docs = ["sphinx>=7.0", "myst-parser>=2.0", "sphinx-rtd-theme>=2.0"]`. |
| 2.2 | **Install.** Run `pip install -e ".[docs]"` (or `uv pip install -e ".[docs]"`) from repo root. |
| 2.3 | **Layout.** Sphinx source is `docs/`. |
| 2.4 | **Config.** In `docs/conf.py`: set project/version, `html_theme = "sphinx_rtd_theme"`, extensions (e.g. `myst_parser`, `sphinx.ext.autodoc`, `sphinx.ext.intersphinx`). |
| 2.5 | **Toctree.** `index.rst` lists: installation, usage_local, command_line, configuration, outputs, processing, faq; plus “Other” (e.g. other_docs). No separate methods_reference. |

---

### Phase 3 – Local build and fix

| Step | Action |
|------|--------|
| 3.1 | From repo root: `sphinx-build -b html docs docs/_build`. |
| 3.2 | Open `docs/_build/index.html` and click through all pages. Fix broken `:doc:` refs, wrong paths, RST warnings. |
| 3.3 | Add `docs/_build/` to `.gitignore` if not already. |
| 3.4 | (Optional) Run with `-W` to treat warnings as errors: `sphinx-build -b html docs docs/_build -W`. |

---

### Phase 4 – Read the Docs

| Step | Action |
|------|--------|
| 4.1 | Sign up at [readthedocs.org](https://readthedocs.org) and connect GitHub. |
| 4.2 | **Import project:** “Import a Project” → select the `brainana` repo. |
| 4.3 | **Configure build:** Documentation type = Sphinx. Docs directory = `docs`. Config file = `docs/conf.py`. |
| 4.4 | **Install deps:** In project Admin → Advanced settings, set “Install your project” with `pip install -e .[docs]` (or equivalent so the `docs` extra is installed). |
| 4.5 | Trigger a build. Fix any failures (paths, missing deps, Python version). |
| 4.6 | Note the URL (e.g. `brainana.readthedocs.io`). Optionally add a “Documentation” link in the repo `README.md`. |

---

### Phase 5 – Optional enhancements

| Step | Action |
|------|--------|
| 5.1 | **Versioning:** In RtD “Versions”, activate `stable` (e.g. latest release tag) and `latest` (default branch). In `conf.py`, set `release` from package or env. |
| 5.2 | **Custom domain:** e.g. `docs.brainana.org` → RtD (Admin → Domains, then DNS CNAME). |
| 5.3 | **CI:** Add a job (e.g. GitHub Actions) that runs `sphinx-build -b html docs docs/_build -W` so broken docs fail the build. |

---

### Phase 6 – Keeping docs in sync (ongoing)

| When | Do this |
|------|---------|
| You change pipeline steps or tools | 1. Update `docs_temp/paper/methods_reference.md`. 2. Update `docs/processing.rst`. 3. Update QC boilerplate (`boilerplate_methods.txt`, `reports.py`) if the methods section text changed. |
| You change CLI or Docker usage | Update `docs/command_line.rst` and relevant parts of `docs/usage_local.rst`. |
| You change installation or config | Update `docs/installation.rst` and/or `docs/configuration.rst`. |

---

## Summary checklist

| # | Phase | Action |
|---|--------|--------|
| 1 | Content | methods_reference.md = canonical; processing.rst = single methods page; sync to boilerplate when methods change. |
| 2 | Sphinx | docs deps in pyproject.toml; install .[docs]; conf.py and toctree in docs/. |
| 3 | Local | sphinx-build docs → docs/_build; fix warnings; gitignore _build. |
| 4 | RtD | Import repo; set docs dir and conf; install .[docs]; build and fix. |
| 5 | Optional | Versioning, custom domain, CI docs build. |
| 6 | Ongoing | On method/CLI/install changes: update docs_temp/paper → docs/ (and boilerplate). |

After this, you have a single user-facing doc site that stays aligned with your internal paper materials and is published on Read the Docs.
