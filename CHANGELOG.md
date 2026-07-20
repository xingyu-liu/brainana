# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [2.0.0] - 2026-07-20

### Added

- **Brainana Viewer companion docs** — a new [Brainana Viewer](https://brainana.readthedocs.io/en/stable/viewer.html) page introduces the cross-platform NiiVue desktop viewer for exploring per-subject pipeline output (anatomical volumes, cortical surfaces, atlas overlays, and functional maps), with a link to the [viewer's repository](https://github.com/arcaro-lab/brainana_tools)
- **Bundled demo dataset + "Try a demo" guide** — a small, ready-to-run BIDS dataset (`examples/dataset_example/`, one macaque subject: two T1w, one T2w, two resting-state runs) exercises the full pipeline end to end; the [Try a demo](https://brainana.readthedocs.io/en/stable/demo.html) page documents the run command, expected run time, and expected output
- **New bundled atlases** — **D99**, **MacBNA** (Macaque Brainnetome Atlas), and **FuncNetwork** (functional network parcellation) added to `template_zoo/atlas/`, with accompanying `.tsv`/`.md`/`.bib` metadata sidecars

### Changed

- **ARM atlas metadata** — ARM1–ARM6 TSVs now include a `color` column (hex RGB lookup) for consistent region coloring; rows reformatted to match


## [1.3.0] - 2026-07-13

### Added

- **Atlas surface projection (fsnative)** — when surface reconstruction is enabled, T1w-space atlases are projected into FastSurfer space and onto the cortical surface (nearest-neighbour throughout), published under `anat/atlas_space-fsnative/` as resampled label volumes `atlas-<name>_space-fsnative_<prefix>.nii.gz` and per-hemisphere maps `atlas-<name>_space-fsnative_hemi-<L|R>_<prefix>.func.gii`
- **Custom template files** — `--output_space` (`template.output_space`) accepts an absolute path to a `.nii/.nii.gz` file; outputs use the fixed BIDS space label `template`. Strict validation (wrong extension or missing file aborts at run start, no silent fallback); the resolved path is recorded in each sidecar and in `dataset_description.json` (`TemplateSource.Custom`). Custom templates have no bundled atlases, so atlas outputs are skipped for that space
- **JSON sidecars on derivatives** — anatomical *and* functional publish processes emit BIDS JSON sidecars (`write_derivative_sidecar`) recording `TemplateSource`, `SkullStripped`/`Type`/`Sources`, and BOLD timeseries fields; a `dataset_description.json` is written at run start
- **Engine-aware transform sidecars** — `*_xfm.json` `GeneratedBy` names the actual registration engine after any runtime fallback (FireANTs / ANTs / ANTsPy / FLIRT / SimpleITK)
- **Atlas metadata sidecars** — `atlas-{name}.tsv`, `.md`, and `.bib` are copied into every output space (T1w, scanner, fsnative)
- **Centralized CLI flag handling** — `flags.sh` + `known_flags.txt` as the single source of truth; `-h/--help` prints `USAGE.txt` before any heavy setup; unknown args are rejected fast; underscore is canonical with hyphenated aliases (`--work-dir` → `--work_dir`)

### Changed

- QC reports read the merged Nextflow config, so they reflect CLI overrides such as custom `output_space` templates
- `stc_enabled` default aligned to `defaults.yaml` (`false` → `true`)

### Fixed

- **Anisotropic skull strip** — resample a NIfTI-path input to isotropic (0.5 mm) before 2.5D U-Net inference, then map back to the native grid; previously an anisotropic T1w distorted the aspect ratio and collapsed the mask, breaking anatomical conform (native grid/affine/header unchanged)
- Atlas projected counter increments only when a hemisphere is actually projected
- Dropped the `template_dir` override; the bundled template manager is always used
- Clarified the `main.nf` hyphen-normalization error message


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


## [1.0.0] - 2026-05-28

First public release of **Brainana**, a unified preprocessing framework for macaque MRI: BIDS in, anatomical and functional preprocessing, optional cortical surface reconstruction, and HTML QC reports.

- **Run via Docker** — `docker pull liuxingyu987/brainana:1.0.0` (see [Installation](https://brainana.readthedocs.io/en/stable/installation.html))
- **Nextflow pipeline** — parallel processing across subjects/sessions/runs with resume on failure
- **Anatomical** — synthesis, conform, skull strip/segmentation, bias correction, template registration, optional T2w coregistration and surface reconstruction
- **Functional** — slice timing (when metadata allow), motion correction, registration to anatomy/template, tSNR
- **QC** — per-step snapshots and a combined HTML report
- **Docs** — [Read the Docs](https://brainana.readthedocs.io/en/stable/) (usage, outputs, templates/atlases, FAQ)

Research software, beta stage — see README for license and citation.
