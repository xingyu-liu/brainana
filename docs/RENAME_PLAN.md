# Package rename plan

Rename the four top-level packages in `banana/` to PEP 8–style lowercase-with-underscores:

| Current (directory / import) | New (directory / import) |
|-----------------------------|---------------------------|
| `macacaMRIprep`             | `nhp_mri_prep`            |
| `NHPskullstripNN`          | `nhp_skullstrip_nn`       |
| `FastSurferCNN`            | `fastsurfer_nn`           |
| `FastSurferRecon`          | `fastsurfer_surfrecon`    |

**Note:** Inside `FastSurferRecon` the subpackage stays `fastsurfer_recon`. After the rename, imports become `fastsurfer_surfrecon.fastsurfer_recon.*`.

---

## Phase 1: Rename directories

From repo root `banana/`:

```bash
cd /home/star/github/banana
mv macacaMRIprep    nhp_mri_prep
mv NHPskullstripNN  nhp_skullstrip_nn
mv FastSurferCNN    fastsurfer_nn
mv FastSurferRecon  fastsurfer_surfrecon
```

---

## Phase 2: Root `pyproject.toml`

**File:** `banana/pyproject.toml`

- **[tool.setuptools.packages.find]**  
  - `include = ["macacaMRIprep*", "FastSurferCNN*", "FastSurferRecon*", "NHPskullstripNN*"]`  
  → `include = ["nhp_mri_prep*", "fastsurfer_nn*", "fastsurfer_surfrecon*", "nhp_skullstrip_nn*"]`

- **[tool.setuptools.package-data]**  
  - Keys `"macacaMRIprep"`, `"FastSurferCNN"`, `"FastSurferRecon"`, `"NHPskullstripNN"`  
  → `"nhp_mri_prep"`, `"fastsurfer_nn"`, `"fastsurfer_surfrecon"`, `"nhp_skullstrip_nn"`

---

## Phase 3: Python imports and string references

### 3.1 Global replace (imports and package names)

In **all** files under `banana/` (including `.nf`, `.html`, `.md`, `.yaml`, `.sh`, `.groovy`), replace:

| Find (exact)     | Replace (exact)       |
|------------------|------------------------|
| `macacaMRIprep`  | `nhp_mri_prep`         |
| `NHPskullstripNN`| `nhp_skullstrip_nn`    |
| `FastSurferCNN`  | `fastsurfer_nn`        |
| `FastSurferRecon`| `fastsurfer_surfrecon` |

**Important:** Do **not** change the **class name** `FastSurferCNN` in `fastsurfer_nn/models/networks.py` (the neural network class). Only change **package** names and **imports**. If your replace is global, exclude that one line or do a second pass to restore the class name in the dict, e.g. keep `"FastSurferCNN": FastSurferCNN` or change to `"fastsurfer_nn": FastSurferCNN` as desired.

### 3.2 Path literals (directory names in code)

Update any string that refers to the **old directory names** (e.g. for `Path(...)` or `sys.path`):

| File | Current | New |
|------|---------|-----|
| `nhp_mri_prep/steps/anatomical.py` | `project_root / "FastSurferRecon"` | `project_root / "fastsurfer_surfrecon"` |
| `fastsurfer_nn/utils/constants.py` | `FASTSURFER_ROOT / "FastSurferCNN"` | `FASTSURFER_ROOT / "fastsurfer_nn"` |
| `fastsurfer_nn/scripts/02_freesurfer_prep.py` | `FASTSURFER_ROOT / "FastSurferCNN"` | `FASTSURFER_ROOT / "fastsurfer_nn"` |
| `fastsurfer_nn/inference/segmentation.py` | `FASTSURFER_ROOT / "FastSurferCNN"` (both occurrences) | `FASTSURFER_ROOT / "fastsurfer_nn"` |
| `fastsurfer_surfrecon/fastsurfer_recon/config.py` | `... parent.parent / "FastSurferCNN" / "atlas" ...` and `import FastSurferCNN` / `Path(FastSurferCNN.__file__)` | `... parent.parent / "fastsurfer_nn" / "atlas" ...` and `import fastsurfer_nn` / `Path(fastsurfer_nn.__file__)` |

### 3.3 File-by-file checklist (high level)

- **`nhp_mri_prep/`**  
  - All `from macacaMRIprep.*` / `import macacaMRIprep` → `nhp_mri_prep`.  
  - Docstrings/comments that say "macacaMRIprep" → "nhp_mri_prep" (or "NHP MRI Prep" for display).  
  - `steps/anatomical.py`: path `"FastSurferRecon"` → `"fastsurfer_surfrecon"`; imports `FastSurferRecon.fastsurfer_recon.*` → `fastsurfer_surfrecon.fastsurfer_recon.*`; `FastSurferCNN` → `fastsurfer_nn`.  
  - `operations/preprocessing.py`: `FastSurferCNN` / `NHPskullstripNN` in imports and log messages → `fastsurfer_nn` / `nhp_skullstrip_nn`.  
  - `quality_control/reports.py`: `"pipeline_name": "macacaMRIprep"` and HTML title/generator text → `nhp_mri_prep` (or keep display name "NHP MRI Prep" in user-facing strings).  
  - `quality_control/mri_plotting.py`, `snapshots.py`, `config/config_validation.py`, `config/config_generator.html`, `utils/bids.py`: macacaMRIprep → nhp_mri_prep in comments/strings.  
  - `scripts/comform_input2template.py`, `generate_report_only.py`, `test_surface_qc.py`, `run_antsregistration.py`: update imports and comments.

- **`nhp_skullstrip_nn/`**  
  - No internal `from NHPskullstripNN` in Python (only external callers).  
  - Scripts and configs that reference the package or paths: `run_prediction_single.sh`, `run_prediction_batch.py`, `run_training_pipeline.sh`, `config_example/*.yaml`, `tests/test_prediction.sh` — replace `NHPskullstripNN` with `nhp_skullstrip_nn` in paths and `python -m NHPskullstripNN.*` → `python -m nhp_skullstrip_nn.*`.

- **`fastsurfer_nn/`**  
  - Every `from FastSurferCNN.*` / `import FastSurferCNN` → `fastsurfer_nn`.  
  - `utils/constants.py`: `"FastSurferCNN"` in path → `"fastsurfer_nn"`.  
  - `inference/segmentation.py`, `scripts/02_freesurfer_prep.py`, `postprocessing/prepping_for_surfrecon.py`, `models/networks.py`, `models/optimizer.py`, `utils/misc.py`: update imports and path literals; leave **class** `FastSurferCNN` (and `FastSurferVINN`) as-is unless you explicitly want to rename those too.  
  - Config YAMLs under `config/` and scripts under `scripts/`: paths containing `FastSurferCNN` → `fastsurfer_nn` (e.g. `/home/star/github/banana/FastSurferCNN/...` → `.../fastsurfer_nn/...`).

- **`fastsurfer_surfrecon/`**  
  - `fastsurfer_recon/config.py`: comment "parent of FastSurferRecon" → "parent of fastsurfer_surfrecon"; path `"FastSurferCNN"` → `"fastsurfer_nn"`; `import FastSurferCNN` → `import fastsurfer_nn`.  
  - Scripts under `scripts/`: they use `from fastsurfer_recon.*` (no top-level package in import); ensure they are run with `fastsurfer_surfrecon` on `PYTHONPATH` or installed so that `fastsurfer_recon` is found under `fastsurfer_surfrecon`.  
  - No change to the **subpackage** name `fastsurfer_recon` (directory and imports stay `fastsurfer_recon`).

- **`banana/modules/`**  
  - `anatomical.nf`, `functional.nf`, `qc.nf`: every `from macacaMRIprep.*` → `from nhp_mri_prep.*`; comment "macacaMRIprep" → "nhp_mri_prep".

- **`banana/tests/`**  
  - `surf_recon_t1wt2wcombined.py`, `test_skullstripping.py`: macacaMRIprep → nhp_mri_prep, FastSurferCNN → fastsurfer_nn in imports and comments.

- **`banana/main.nf`**  
  - `"${projectDir}/macacaMRIprep/..."` → `"${projectDir}/nhp_mri_prep/..."`.

- **`banana/run_nextflow.sh`**  
  - `$SCRIPT_DIR/macacaMRIprep/...` → `$SCRIPT_DIR/nhp_mri_prep/...`.

- **`banana/workflows/param_resolver.groovy`**  
  - `"${projectDir}/macacaMRIprep/..."` → `"${projectDir}/nhp_mri_prep/..."`.

- **`banana/docs/`**  
  - Update all references in `.md`, `.puml` (e.g. `PROJECT_STRUCTURE.md`, `LOGGING_SYSTEM.md`, `macacaMRIprep_component_diagram.puml`, etc.) from macacaMRIprep / FastSurferCNN / NHPskullstripNN / FastSurferRecon to the new names.

- **`banana/tests/test_primede*.sh`**  
  - Optional: paths like `macacaMRIprep_%j.out` and `source ~/macacaMRIprep/bin/activate` — only if you want to rename the env/artifacts; otherwise leave as-is.

---

## Phase 4: FastSurferRecon’s own `pyproject.toml`

**File:** `banana/fastsurfer_surfrecon/pyproject.toml`

- This file defines the **installable** name and the **subpackage** `fastsurfer_recon`.  
- You can keep `name = "fastsurfer-recon"` for PyPI or change to e.g. `name = "fastsurfer-surfrecon"`.  
- No change needed for `include = ["fastsurfer_recon*"]` — the inner package remains `fastsurfer_recon`.

---

## Phase 5: Optional / follow-up

- **Class name `FastSurferCNN`** in `fastsurfer_nn/models/networks.py`: keep for compatibility with checkpoint/configs, or rename in a later PR.  
- **Display name**: In user-facing strings (e.g. QC report title), you can keep "NHP MRI Prep" or "macacaMRIprep" as the product name while the package is `nhp_mri_prep`.  
- **Hardcoded paths** in example configs (e.g. `/home/star/github/banana/...`) and shell scripts: update to use `fastsurfer_nn`, `nhp_skullstrip_nn`, etc., or make them relative/configurable.

---

## Order of operations (recommended)

1. **Phase 1** – Rename the four directories.  
2. **Phase 2** – Update root `pyproject.toml`.  
3. **Phase 3** – Global replace package names (being careful with the class name in `networks.py`), then fix path literals and file-by-file items above.  
4. **Phase 4** – Adjust `fastsurfer_surfrecon/pyproject.toml` if desired.  
5. Run tests and Nextflow from `banana/` to confirm imports and paths.

---

## Quick replace commands (use with care)

From `banana/`:

```bash
# Replace in all text files (review before committing)
find . -type f \( -name '*.py' -o -name '*.nf' -o -name '*.html' -o -name '*.md' -o -name '*.yaml' -o -name '*.yml' -o -name '*.sh' -o -name '*.groovy' -o -name '*.puml' -o -name '*.toml' \) -not -path './.venv/*' -not -path './.git/*' | xargs sed -i \
  -e 's/macacaMRIprep/nhp_mri_prep/g' \
  -e 's/NHPskullstripNN/nhp_skullstrip_nn/g' \
  -e 's/FastSurferRecon/fastsurfer_surfrecon/g' \
  -e 's/FastSurferCNN/fastsurfer_nn/g'
```

Then **manually**:

- Restore or fix the **class**/dict in `fastsurfer_nn/models/networks.py` (e.g. keep `"FastSurferCNN": FastSurferCNN` or set to `"fastsurfer_nn": FastSurferCNN`).  
- Fix any docstrings/display names where you want to keep "FastSurfer CNN" or "NHP MRI Prep" for users.  
- Re-run the file-by-file checks above so no path or import was missed.

After that, run the test suite and a minimal Nextflow run to validate.
