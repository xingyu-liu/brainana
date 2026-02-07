# brainana documentation plan

This guide describes how to build documentation similar to [DeepPrep](https://deepprep.readthedocs.io/en/latest/usage_local.html) and [fMRIPrep](https://fmriprep.org/en/stable/usage.html): Sphinx-based docs hosted on Read the Docs, with clear **Installation** and **Usage (Local)** sections including BIDS, FreeSurfer, Docker, and command-line arguments.

---

## Step 1: Choose the doc stack

- **Sphinx** – Same as DeepPrep and fMRIPrep. Generates HTML (and PDF/LaTeX if needed), supports RST and Markdown (via MyST), versioned docs, and Read the Docs integration.
- **Read the Docs (RtD)** – Free hosting for public repos, automatic builds on push, version selector (e.g. `stable`, `latest`).
- **Optional later:** Custom domain (e.g. `brainana.org`) like fMRIPrep; RtD supports this.

**Recommendation:** Sphinx + MyST (Markdown) so you can keep writing `.md` and reuse `README_Docker.md` content.

---

## Step 2: Add Sphinx and doc dependencies

In `pyproject.toml`, add an optional dependency group for docs:

```toml
[project.optional-dependencies]
dev = [ ... ]
docs = [
    "sphinx>=7.0",
    "myst-parser>=2.0",
    "sphinx-rtd-theme>=2.0",
]
```

Then install:

```bash
uv pip install -e ".[docs]"
# or: pip install -e ".[docs]"
```

---

## Step 3: Create the docs layout

Create a **dedicated Sphinx source tree** (so built HTML lives in one place and RtD can point at it):

```
docs/
  doc/                    # Sphinx source (or use docs/ and build in docs/_build)
    conf.py               # Sphinx config
    index.rst             # Home page
    installation.rst      # Installation
    usage_local.rst       # Usage (Local) – main user-facing page
    usage_cluster.rst     # Optional: Usage on HPC/cluster
    docker.rst            # Docker details (can be under usage_local)
    command_line.rst      # Command-line arguments
    outputs.rst           # Outputs / derivatives
    faq.rst               # FAQ / troubleshooting
    _static/              # Optional: custom CSS/images
  _build/                 # Generated HTML (gitignore this)
```

**Alternative:** Keep current `docs/` for design/planning and add `doc/` (or `docs/source/`) for Sphinx; index can link to “Other docs” (paper, plans) if you want.

---

## Step 4: Configure Sphinx (`doc/conf.py`)

Create `doc/conf.py` with:

- **Extensions:** `sphinx.ext.autodoc`, `sphinx.ext.viewcode`, `myst_parser` (if using `.md`), `sphinx.ext.intersphinx` (for Python/NumPy links).
- **Theme:** `sphinx_rtd_theme` (Read the Docs theme).
- **Version:** Read from `pyproject.toml` or set in `conf.py` (e.g. `release = "0.1.0"`).
- **Project:** `brainana`, `html_title`, `html_short_title`.
- **Options:** `html_show_sourcelink`, `html_copy_source = False`, etc.

Example (minimal):

```python
project = "brainana"
copyright = "2025, brainana developers"
release = "0.1.0"
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.intersphinx"]
templates_path = ["_templates"]
exclude_patterns = []
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
```

Use `myst_parser` so you can write `.md` and include `README_Docker.md` with `.. include::` or by copying sections.

---

## Step 5: Write the main pages (mirroring DeepPrep/fMRIPrep)

### 5.1 `index.rst`

- Short project description (macaque neuroimaging, BIDS, preprocessing).
- Links to: **Installation**, **Usage (Local)**, **Outputs**, **FAQ**, **Other info** (e.g. paper, design docs).
- Optional: “Quick start” one-liner (Docker + three mounts).

### 5.2 `installation.rst`

- How to get brainana: Docker (recommended), optionally build from source / `uv pip install -e .`, system deps (Nextflow, FreeSurfer, etc.).
- Link to **Usage (Local)** and **FreeSurfer license** section.

### 5.3 `usage_local.rst` (main usage page)

Structure it like the references:

1. **The BIDS format**  
   - Input must be valid BIDS; link to [BIDS Validator](https://bids-standard.github.io/bids-validator/) and NiPreps/BIDS-Apps if relevant.

2. **The FreeSurfer license**  
   - Required for surface reconstruction; how to get it; mount path: `-v <path>:/fs_license.txt`.

3. **Docker user guide**  
   - **Command-line arguments:** table or list of Docker invocation args and pipeline args (e.g. `[input_dir] [output_dir]`, `--config`, `--anat_only`, `--output_space`, `-profile minimal`, `--skip_bids_validation`, `--subjects`, `--sessions`, etc.).  
   - **Sample Docker command:**  
     - Minimal: `docker run -it --rm --gpus all -v <bids_dir>:/input -v <output_dir>:/output -v <fs_license>:/fs_license.txt xxxlab/brainana:latest`  
     - With options: custom config, anat-only, output space, resource limits.
   - **Quick start:**  
     - Optional: link to a small test dataset or one-line curl if you add one (like DeepPrep’s test_sample).

4. **Running as host user (file permissions)**  
   - `--user $(id -u):$(id -g)`, `NXF_WORK`, `NXF_HOME` (from `README_Docker.md`).

5. **Interactive / development mode**  
   - X11, mounting repo, config generator GUI, running Nextflow manually (short subsection).

6. **Optional: Singularity**  
   - If you support it: build from Docker image, `-B` mounts, `--nv` for GPU, equivalent of `--device cpu`/gpu.

### 5.4 `command_line.rst`

- Document **container interface:**  
  - Positional: `[input_dir]` (default `/input`), `[output_dir]` (default `/output`).  
  - Pipeline options passed after: `--config`, `--anat_only`, `--output_space`, `-profile minimal|recommended`, `--skip_bids_validation`, `--subjects`, `--sessions`, `--tasks`, `--runs`, etc.
- Pull from `param_resolver.groovy` (e.g. `output_space`, `anat_only`, `subjects`, `sessions`, `tasks`, `runs`) and from `run_brainana.sh` / `entrypoint.sh` so the doc is the single source of truth.
- Optional: add a “Reference” section that lists every option in a table (like fMRIPrep’s “Command-Line Arguments”).

### 5.5 `outputs.rst`

- Where outputs go: `output_dir`, layout (e.g. `sub-XXX/`, `nextflow_reports/`, `fastsurfer/`), main derivatives (anatomical, surfaces, functional if applicable).
- Link to any existing internal docs (e.g. pipeline design) if useful.

### 5.6 `faq.rst` or **Troubleshooting** in `usage_local.rst`

- From `README_Docker.md`: X server, GPU, config file, FreeSurfer license, Docker vs Nextflow resource limits.
- Add: “Where are logs?” (e.g. `output_dir/nextflow_reports/`), “How to resume?” if supported.

---

## Step 6: Build HTML locally

From repo root:

```bash
sphinx-build -b html doc doc/_build
```

Open `doc/_build/index.html`. Fix any warnings (missing refs, wrong paths). Add `doc/_build/` to `.gitignore` if not already.

---

## Step 7: Connect Read the Docs

1. **Sign up:** [readthedocs.org](https://readthedocs.org), log in with GitHub.
2. **Import project:** “Import a Project” → select your `brainana` repo.
3. **Configure:**
   - **Documentation type:** Sphinx.
   - **Config file:** `doc/conf.py` (or leave default and set “Docs directory” to `doc` and “Config file” to `doc/conf.py`; RtD expects `conf.py` inside the docs dir).
   - **Python interpreter:** Install dependency group `docs` (e.g. “Install your project inside a virtualenv using `pip install -e .[docs]`” in the RtD “Admin” → “Advanced settings”).
4. **Build:** Trigger a build; fix any failing builds (paths, missing deps).
5. **URL:** You’ll get `brainana.readthedocs.io` (or similar). Enable “Show version warning” for `stable` if you use version tags.

---

## Step 8: Optional – versioning and custom domain

- **Versioning:** In RtD, under “Versions”, activate branches/tags (e.g. `stable` → latest release tag, `latest` → default branch). In Sphinx, set `release` from env or from `pyproject.toml` so each build gets the right version.
- **Custom domain:** In RtD “Admin” → “Domains”, add a CNAME (e.g. `docs.brainana.org`). Then in your DNS, point that host to RtD. fMRIPrep uses `fmriprep.org` for the main site; you can do “docs.brainana.org” → RtD.

---

## Step 9: Keep docs in sync

- **Single source:** Prefer one place for “how to run” (e.g. `usage_local.rst` or a `usage_local.md` included from RST). Reuse content from `README_Docker.md` via include or copy; when you change Docker usage, update the doc and optionally a short summary in `README_Docker.md` that links to the full doc.
- **CLI reference:** When you add or change pipeline parameters (in Nextflow or `param_resolver.groovy`), update `command_line.rst` (and the “Command-line arguments” section in `usage_local.rst`).
- **CI:** Optional: add a “docs” job that runs `sphinx-build -b html doc doc/_build` and fails on warnings (`-W`) so broken refs don’t get merged.

---

## Summary checklist

| Step | Action |
|------|--------|
| 1 | Choose Sphinx + Read the Docs (+ optional MyST) |
| 2 | Add `docs` optional deps and install |
| 3 | Create `doc/` layout (conf.py, index, usage_local, etc.) |
| 4 | Configure `conf.py` (theme, extensions, version) |
| 5 | Write index, installation, usage_local (BIDS, FreeSurfer, Docker, CLI, quick start), command_line, outputs, faq |
| 6 | Build locally and fix warnings |
| 7 | Import project on Read the Docs, set docs dir and config, install `.[docs]`, build |
| 8 | (Optional) Versioning and custom domain |
| 9 | Keep usage and CLI docs in sync with code and README |

After this, you’ll have a doc site similar to DeepPrep’s “Usage Notes (Local)” and fMRIPrep’s “Usage Notes”, with a clear path from installation to Docker and command-line reference.
