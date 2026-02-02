# Import Management Improvement Plan

This document outlines a phased plan to standardize and improve import handling across the brainana project. It addresses the issues identified in the import review: inconsistent `sys.path` manipulation, library code that modifies import paths, and scripts without a consistent execution strategy.

---

## Guiding Principles

1. **Library code never modifies `sys.path`** — assume the package is installed or `PYTHONPATH` is set correctly.
2. **Scripts run as installed entry points** — users run `brainana-xyz` commands, not `python path/to/script.py`.
3. **Single source of truth for paths** — no duplicated `Path(__file__).parent.parent...` logic.
4. **Backward compatibility** — Nextflow, Docker, and tests continue to work throughout the migration.

---

## Phase 1: Fix Incorrect sys.path Targets (Low Risk)

**Goal:** Correct scripts that add the wrong directory to `sys.path`, causing fragile or broken imports when run from the repo without an editable install.

**Files to update:**

| File | Current | Correct |
|------|---------|---------|
| `src/nhp_mri_prep/scripts/generate_report_only.py` | `brainana/` (project root) | `src/` |
| `src/nhp_mri_prep/scripts/correct_orientation_mismatch.py` | `brainana/` | `src/` |

**Approach:** Replace `Path(__file__).parent.parent.parent.parent` with logic that resolves `src/` (e.g., `Path(__file__).parent.parent.parent` since scripts/ → nhp_mri_prep → src).

**Verification:** Run each script from project root with `python src/nhp_mri_prep/scripts/<script>.py` (without editable install) and confirm imports succeed.

---

## Phase 2: Add Console Script Entry Points (Medium Risk)

**Goal:** Expose key scripts as `brainana-*` commands so users run them as installed tools, not as raw Python files.

**1. Identify scripts to expose**

| Script | Suggested command | Priority |
|--------|-------------------|----------|
| `scripts/generate_surface_qc.py` | `brainana-generate-surface-qc` | High (commonly used) |
| `scripts/generate_report_only.py` | `brainana-generate-report` | High |
| `scripts/correct_orientation_mismatch.py` | `brainana-correct-orientation` | Medium |
| `scripts/run_antsregistration.py` | `brainana-run-ants` | Low (looks like dev/debug) |
| `nextflow_scripts/discover_bids_for_nextflow.py` | `brainana-discover-bids` | High (pipeline entry) |
| `nextflow_scripts/read_yaml_config.py` | Internal to Nextflow | Skip (called by .nf) |

**2. Refactor scripts for entry point pattern**

Each script needs a `main()` (or similar) and an `if __name__ == "__main__":` guard. The entry point will call that function.

**3. Add to pyproject.toml**

```toml
[project.scripts]
brainana-generate-surface-qc = "nhp_mri_prep.scripts.generate_surface_qc:main"
brainana-generate-report = "nhp_mri_prep.scripts.generate_report_only:main"
brainana-correct-orientation = "nhp_mri_prep.scripts.correct_orientation_mismatch:main"
brainana-discover-bids = "nhp_mri_prep.nextflow_scripts.discover_bids_for_nextflow:main"
```

**4. Remove sys.path manipulation from these scripts** — they will run as installed modules.

**Verification:** After `uv sync` or `pip install -e .`, run `brainana-generate-surface-qc --help` (or equivalent) from anywhere. Confirm Nextflow still invokes `discover_bids_for_nextflow.py` correctly (Nextflow may need to call `brainana-discover-bids` instead of `python path/to/discover_bids_for_nextflow.py`).

---

## Phase 3: Remove sys.path from Library Code (Medium Risk)

**Goal:** Library modules (`steps/`, `operations/`) must not modify `sys.path`. Cross-package imports should work because the environment is set up correctly.

**Files to update:**

| File | Current behavior | Change |
|------|------------------|--------|
| `nhp_mri_prep/operations/preprocessing.py` | Adds `src/` before importing fastsurfer_nn, nhp_skullstrip_nn | Remove sys.path block; use direct `from fastsurfer_nn...`, `from nhp_skullstrip_nn...` |
| `nhp_mri_prep/steps/anatomical.py` | Adds `src/` inside `anat_surface_reconstruction()` before importing fastsurfer_surfrecon | Remove sys.path block; move imports to top of file with direct `from fastsurfer_surfrecon...` |

**Prerequisite:** Ensure Docker `PYTHONPATH` and local dev setup both include `src/` (or the package is installed). Docker already sets `PYTHONPATH=/opt/brainana/src`; local dev should use `uv sync` or `pip install -e .`.

**Verification:** Run full anatomical pipeline (or at least surface reconstruction) in Docker and locally with editable install. Run tests.

---

## Phase 4: Standardize Remaining Scripts and Tests (Lower Priority)

**Goal:** Consistent patterns across `fastsurfer_nn`, `fastsurfer_surfrecon`, `nhp_skullstrip_nn` scripts and tests.

**1. fastsurfer_nn scripts**

- `scripts/01_skullstrip_fastsurfercnn.py`
- `scripts/02_freesurfer_prep.py`
- `postprocessing/prepping_for_surfrecon.py`
- `postprocessing/reduce_to_aseg.py`, `postprocessing/postseg_utils.py`
- `training/step1_split_data.py`, `step2_create_hdf5.py`

**Options:**
- Add entry points for user-facing scripts.
- For modules like `postseg_utils.py` and `prepping_for_surfrecon.py` that are imported by other code: remove sys.path and rely on installed package.
- For training scripts: add entry points (e.g. `fastsurfer-split-data`) or document that they must be run with `python -m fastsurfer_nn.training.step1_split_data` from project root.

**2. fastsurfer_surfrecon scripts**

- `scripts/test_pipeline*.py` — development scripts; can keep sys.path or add `python -m` usage in README.

**3. nhp_skullstrip_nn train scripts**

- `train/step1_split_data.py`, `step2_create_hdf5.py`, `step3_train_model.py` — add entry points or document `python -m` usage.

**4. Tests**

- `tests/test_skullstripping.py`, `tests/surf_recon_t1wt2wcombined.py`, etc. — they add `src/` to path. With `pytest` and `pip install -e .`, tests typically run from the project root with the package on path. Consider removing sys.path from tests if the package is always installed in the test env; otherwise keep for `pytest tests/` without install.

---

## Phase 5: Optional Hardening

**1. Shared bootstrap helper (only if needed)**

If some scripts must remain runnable as `python script.py` (e.g. from Nextflow without installing), add a single helper:

```python
# nhp_mri_prep/_bootstrap.py (or similar)
def ensure_src_on_path() -> None:
    """Add src/ to sys.path if running from repo without install."""
    if "nhp_mri_prep" in sys.modules:
        return  # Already importable
    src = Path(__file__).resolve().parent.parent.parent  # nhp_mri_prep -> src
    if src not in sys.path:
        sys.path.insert(0, str(src))
```

Scripts that need it call `ensure_src_on_path()` before other imports. Prefer entry points so this is rarely needed.

**2. Add import-linter or similar**

Configure `import-linter` or `layer-linter` to enforce:
- No cross-package imports in the wrong direction.
- No `sys.path` manipulation in library code.

---

## Implementation Order

| Phase | Effort | Risk | Dependency |
|-------|--------|------|------------|
| 1. Fix wrong sys.path | ~30 min | Low | None |
| 2. Entry points | 1–2 hrs | Medium | Phase 1 |
| 3. Remove sys.path from library | ~1 hr | Medium | None (can run parallel to 2) |
| 4. Standardize other scripts | 2–3 hrs | Low | Phases 2–3 |
| 5. Hardening | Optional | Low | Phases 1–4 |

**Suggested sequence:** 1 → 3 → 2 → 4 → 5 (or 1 → 2 → 3 if entry points are higher priority).

---

## Nextflow Integration Notes

- **discover_bids_for_nextflow.py:** Nextflow workflows call this before the main pipeline. Update the workflow to invoke `brainana-discover-bids` (or `python -m nhp_mri_prep.nextflow_scripts.discover_bids_for_nextflow`) instead of a raw script path, once entry points are in place.
- **read_yaml_config.py:** Similar consideration if it is invoked as a subprocess.
- **Docker:** Keep `PYTHONPATH=/opt/brainana/src`; it aligns with the `src` layout and works for both installed and non-installed runs.

---

## Checklist Before Each Merge

- [ ] `uv sync` or `pip install -e .` succeeds
- [ ] `pytest tests/` passes
- [ ] Key scripts run via entry points (where added)
- [ ] Docker build and at least one pipeline run succeed
- [ ] No new `sys.path` manipulation in library code
