# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [1.2.0] - 2026-07-03

### Added

- **Functional confound regressors** — fMRIPrep-compatible nuisance regressors written per run as `*_desc-confounds_timeseries.tsv` (+ JSON sidecar), compatible with `nilearn...load_confounds`: 24-parameter motion, framewise displacement (macaque 27 mm radius) and RMSD, DVARS/std-DVARS, global-signal and (when a T1w segmentation is available) CSF/WM tissue regressors, plus non-steady-state and motion-outlier indicators. Regressors only — the BOLD image is never scrubbed ([docs](https://brainana.readthedocs.io/en/stable/processing.html))
- **Confounds QC** — fMRIPrep-style confounds panel (global signal, CSF, WM, DVARS, FD) in the HTML report
- **QC run-status badge** — reports are now always generated on completion and carry a status badge: **Pass**, **Pass with warnings** (an optional step failed; partial outputs), or **Fail** (early abort)
- `func.confounds.enabled` toggle and support for runs without motion correction
- Config-validation hardening with defaults/config-generator consistency tests

### Changed

- Confound computation is gated behind `func.confounds.enabled`

### Fixed

- Functional pipeline emits a dummy sentinel for skipped tSNR runs
- QC report: About/Methods headings wrapped in prose measure; confounds pipeline fixes

### Docs

- **SEO metadata** — canonical URLs, Open Graph / Twitter cards, per-page meta descriptions, `SoftwareApplication` JSON-LD, and Google Search Console verification
- Restructured functional processing docs: added confound-regressors, tSNR, and despike method sections and renumbered the functional steps
- Template/atlas zoo note that more atlases are bundled; documented the QC status badge

### Notes

- Install: `pip install "brainana[lite]"` (Lite); full pipeline: `docker pull liuxingyu987/brainana:1.2.0` ([Installation](https://brainana.readthedocs.io/en/stable/installation.html))

## [1.1.0] - 2026-06-03

### Added

- **Brainana Lite** — lightweight, notebook-driven T1w volumetric preprocessing for Jupyter and Google Colab (no Docker required): BIDS organization → synthesis → conform → skull strip/segment → bias correction → template registration → atlas backprojection, with inline QC figures ([`examples/BrainanaLite.ipynb`](examples/BrainanaLite.ipynb), [docs](https://brainana.readthedocs.io/en/stable/brainana_lite.html))
- Colab vs local Jupyter auto-detection; Google Drive mounts, T1w input validation/sync checks, demo mode (`RUN_DEMO`), and isolated env under `WORKING_DIR/brainana_lite_env/`
- Example T1w (`examples/exam_T1w_ple.nii.gz`) and local launcher (`examples/test_BrainanaLite_local_instruction.sh`)
- **SimpleITK rigid registration** — FSL-free alternative to FLIRT for anatomical conform; selectable via `anat.conform.rigid_method` (`flirt` | `sitk`)
- **ANTsPy fallback** (`antspyx_ops.py`) when ANTs CLI is absent; Lite uses `brainana[lite]` and `set_ants_backend("antspyx")`
- **FireANTs CPU syn** — `registration.fireants_allow_cpu` (default `true`) runs affine+greedy on CPU when no GPU (FireANTs 1.5.0)
- Optional dependency extras: `[lite]`, `[surf]`, `[func]`, `[train]`, `[full]` (see `pyproject.toml`)
- `tests/test_create_output_link.py`

### Changed

- Core Python dependencies slimmed; full Docker/runtime should install `brainana[full]` (surfaces, func/BIDS, psutil)
- Lite defaults: SimpleITK rigid (`rigid_method=sitk`), ANTsPy backend, FireANTs syn on CPU when no GPU
- **Logging** — `quiet_external_output()` suppresses third-party print/tqdm when not verbose; sibling package loggers deduplicated for Jupyter; `fix_roi_wm` uses logger instead of `print`
- Dev/scratch scripts moved from `tests/` to `scripts/scratch/` (Docker and local test scripts, surf recon helpers; `test_brainana_local.sh` adds `ENABLE_GPU` toggle)
- `.dockerignore` expanded (excludes `examples/`, `scripts/`, `docs_temp/`, notebooks, local venvs) for slimmer image builds
- Docs CI uses docs-only install in the Sphinx workflow

### Fixed

- **GPU scheduling** — skull stripping and functional brain-mask no longer claim GPU when `use_gpu=false` / CPU mode
- SimpleITK conform output matrix aligned with FLIRT-style convention; center-of-gravity direction and resume-directory bugs
- Colab FUSE / file-existence checks in the Lite notebook
- Sphinx `-W` build: RST warnings corrected; `brainana_lite` page added; README and installation updated for Lite vs full pipeline

### Removed

- Obsolete `scripts/brainana_lite.ipynb`, `scripts/bak_*`, and `tests/test_anat_conformation.py`

### Notes

- Full Nextflow/Docker pipeline defaults unchanged (`rigid_method=flirt`, ANTs CLI when present); Lite explicitly overrides to sitk + antspyx
- Install Lite: `pip install "brainana[lite]"`; full pipeline: `docker pull liuxingyu987/brainana:1.1.0` ([Installation](https://brainana.readthedocs.io/en/stable/installation.html))

## [1.0.0] - 2026-05-28

First public release of **Brainana**, a unified preprocessing framework for macaque MRI: BIDS in, anatomical and functional preprocessing, optional cortical surface reconstruction, and HTML QC reports.

- **Run via Docker** — `docker pull liuxingyu987/brainana:1.0.0` (see [Installation](https://brainana.readthedocs.io/en/stable/installation.html))
- **Nextflow pipeline** — parallel processing across subjects/sessions/runs with resume on failure
- **Anatomical** — synthesis, conform, skull strip/segmentation, bias correction, template registration, optional T2w coregistration and surface reconstruction
- **Functional** — slice timing (when metadata allow), motion correction, registration to anatomy/template, tSNR
- **QC** — per-step snapshots and a combined HTML report
- **Docs** — [Read the Docs](https://brainana.readthedocs.io/en/stable/) (usage, outputs, templates/atlases, FAQ)

Research software, beta stage — see README for license and citation.
