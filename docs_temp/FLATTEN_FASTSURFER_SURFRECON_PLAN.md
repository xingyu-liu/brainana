# Flattening plan: fastsurfer_recon → fastsurfer_surfrecon

Move all code from `src/fastsurfer_surfrecon/fastsurfer_recon/` up into `src/fastsurfer_surfrecon/` so the installable package is a single layer. No implementation—plan only.

---

## 1. Target layout (after)

```
src/fastsurfer_surfrecon/
├── __init__.py          # (from fastsurfer_recon/__init__.py)
├── cli.py
├── config.py
├── pipeline.py
├── atlas/
│   ├── __init__.py
│   └── lut/ARM2/...
├── io/
├── processing/
├── stages/
├── utils/
├── wrappers/
├── config/               # existing data dir (default.yaml)
├── README.md
└── scripts/
```

All Python modules and subpackages live directly under `fastsurfer_surfrecon/`. The existing `config/` directory (with `default.yaml`) stays; it is a data dir, not a Python package, so no clash with `config.py`.

---

## 2. Move steps (file operations)

- **Move** (not copy) every file and directory from `fastsurfer_recon/` into `fastsurfer_surfrecon/`:
  - `fastsurfer_recon/__init__.py` → `fastsurfer_surfrecon/__init__.py`
  - `fastsurfer_recon/cli.py` → `fastsurfer_surfrecon/cli.py`
  - `fastsurfer_recon/config.py` → `fastsurfer_surfrecon/config.py`
  - `fastsurfer_recon/pipeline.py` → `fastsurfer_surfrecon/pipeline.py`
  - `fastsurfer_recon/atlas/` → `fastsurfer_surfrecon/atlas/`
  - `fastsurfer_recon/io/` → `fastsurfer_surfrecon/io/`
  - `fastsurfer_recon/processing/` → `fastsurfer_surfrecon/processing/`
  - `fastsurfer_recon/stages/` → `fastsurfer_surfrecon/stages/`
  - `fastsurfer_recon/utils/` → `fastsurfer_surfrecon/utils/`
  - `fastsurfer_recon/wrappers/` → `fastsurfer_surfrecon/wrappers/`
- **Remove** the now-empty `fastsurfer_recon/` directory.

Internal imports use relative form (`from .base`, `from ..wrappers...`). Package-relative layout (stages, io, wrappers, etc.) is unchanged, so **no changes to relative imports** inside the package.

---

## 3. Edits inside the package

### 3.1 `config.py`

- **`_BRAINANA_ROOT`**  
  Currently: `Path(__file__).resolve().parent.parent.parent.parent`  
  (config.py → fastsurfer_recon → fastsurfer_surfrecon → src → brainana)  
  After: config.py lives in fastsurfer_surfrecon, so use **one fewer** `.parent`:  
  `Path(__file__).resolve().parent.parent.parent`

- **`find_default_config()`**  
  Currently: `package_root = Path(__file__).parent.parent` (fastsurfer_surfrecon).  
  After: package root is the directory containing config.py, so:  
  `package_root = Path(__file__).parent`  
  Then `default_config = package_root / "config" / "default.yaml"` still points at `fastsurfer_surfrecon/config/default.yaml`.

- **Comment (line ~13)**  
  Update from:  
  `# Brainana repo root (config.py -> fastsurfer_recon -> fastsurfer_surfrecon -> src -> brainana)`  
  To:  
  `# Brainana repo root (config.py -> fastsurfer_surfrecon -> src -> brainana)`

- **Comment (line ~42)**  
  "Try fastsurfer_surfrecon package default" can stay as-is.

- **Docstrings mentioning `fastsurfer_recon.cmd`** (lines ~232, 144 in pipeline, 121 in scripts, wrappers/base)  
  Optional: leave as "fastsurfer_recon.cmd" (filename on disk) or standardize to "fastsurfer_surfrecon" in prose only; no code change required for the actual path (still `scripts/fastsurfer_recon.cmd` if you keep that filename).

---

## 4. Build and package config

### 4.1 `pyproject.toml`

- **Package data** for `fastsurfer_surfrecon`:  
  Change  
  `"fastsurfer_recon/atlas/**/*"`  
  to  
  `"atlas/**/*"`  
  (and keep `"config/*.yaml"` as-is).

---

## 5. External and script imports

### 5.1 `src/nhp_mri_prep/steps/anatomical.py`

- Replace:
  - `from fastsurfer_surfrecon.fastsurfer_recon.config import ...`  
    → `from fastsurfer_surfrecon.config import ...`
  - `from fastsurfer_surfrecon.fastsurfer_recon.pipeline import ...`  
    → `from fastsurfer_surfrecon.pipeline import ...`
- Docstrings that say "fastsurfer_surfrecon" or "fastsurfer_surfrecon's AtlasConfig" can stay or be tightened; no functional change.

### 5.2 Scripts under `src/fastsurfer_surfrecon/scripts/`

- **test_pipeline.py**, **test_pipeline_stage.py**, **test_pipeline_1stage.py**

  - **Path setup**  
    Scripts currently add `parent.parent` (i.e. `fastsurfer_surfrecon/`) to `sys.path` and import `fastsurfer_recon.*`.  
    After flattening, the package is `fastsurfer_surfrecon` and lives in `src/`. So add **`src`** to the path: e.g.  
    `_src = Path(__file__).resolve().parent.parent.parent`  
    and `sys.path.insert(0, str(_src))` (so that `import fastsurfer_surfrecon` resolves to `src/fastsurfer_surfrecon`).

  - **Imports**  
    - `from fastsurfer_recon.config import ...` → `from fastsurfer_surfrecon.config import ...`
    - `from fastsurfer_recon.pipeline import ...` → `from fastsurfer_surfrecon.pipeline import ...`
    - `from fastsurfer_recon.utils.logging import ...` → `from fastsurfer_surfrecon.utils.logging import ...`
    - `from fastsurfer_recon.io.subjects_dir import ...` → `from fastsurfer_surfrecon.io.subjects_dir import ...`
    - `from fastsurfer_recon.stages import ...` → `from fastsurfer_surfrecon.stages import ...`
    - `from fastsurfer_recon.wrappers.base import ...` → `from fastsurfer_surfrecon.wrappers.base import ...`

  - **Logger name**  
    `logging.getLogger("fastsurfer_recon")` → `logging.getLogger("fastsurfer_surfrecon")` (optional; can keep "fastsurfer_recon" for log continuity).

  - **Comments**  
    Update "Add fastsurfer_surfrecon/ to path for fastsurfer_recon imports" to something like "Add src/ to path for fastsurfer_surfrecon package".

---

## 6. Logger and docstring names (optional)

- **stages/base.py**: `logging.getLogger(f"fastsurfer_recon.stages.{self.name}")` → `fastsurfer_surfrecon.stages.{self.name}`.
- **utils/logging.py**: `getLogger(f"fastsurfer_recon.{name}")` → `getLogger(f"fastsurfer_surfrecon.{name}")`.
- **pipeline.py**: `logging.getLogger("fastsurfer_recon")` → `"fastsurfer_surfrecon"`.
- **stages/base.py** docstring: `'fastsurfer_recon.stages.s##_name'` → `'fastsurfer_surfrecon.stages.s##_name'`.
- **wrappers/base.py** docstrings: "fastsurfer_recon.cmd" can stay (it’s the log filename) or be rephrased; no requirement to change.

Either do all of these for consistency or leave logger names as "fastsurfer_recon" to avoid changing log aggregation/filters.

---

## 7. Docs and README (non-code)

- **docs/paper/04-core-components-and-methods.md**: Update "fastsurfer_recon/atlas/" to "fastsurfer_surfrecon/atlas/" (or "atlas/ under fastsurfer_surfrecon").
- **docs/IMPORT_IMPROVEMENT_PLAN.md**: Update "fastsurfer_surfrecon scripts" / import examples to use `fastsurfer_surfrecon` (no `.fastsurfer_recon`).
- **README_Docker.md**: Already refers to "fastsurfer_surfrecon"; no change needed unless you add examples.

---

## 8. Order of operations (recommended)

1. **Edits in place (before move)**  
   - In `fastsurfer_recon/config.py`: fix `_BRAINANA_ROOT`, `find_default_config()`, and comments (Section 3.1).  
   - This way the moved file is already correct when it lands in `fastsurfer_surfrecon/`.

2. **Move** all contents of `fastsurfer_recon/` into `fastsurfer_surfrecon/` (Section 2).  
   - Resolve any tool/IDE conflicts: only one `config` entity at package root—`config.py` (module) and `config/` (data dir) coexist.

3. **Delete** empty `fastsurfer_recon/`.

4. **Build/config**: Update `pyproject.toml` package data (Section 4.1).

5. **External and scripts**: Update `nhp_mri_prep` and the three test scripts (Section 5).

6. **Optional**: Logger and docstring renames (Section 6).

7. **Docs**: Update paper and IMPORT_IMPROVEMENT_PLAN (Section 7).

8. **Smoke test**: From repo root, `pip install -e .` and run:
   - `python -c "from fastsurfer_surfrecon import ReconSurfConfig, ReconSurfPipeline; print('ok')"`
   - One of the scripts under `scripts/` (e.g. dry run or one stage).
   - A minimal path that uses `nhp_mri_prep` and calls into surface recon (if available).

---

## 9. Rollback

- Keep a branch or stash before step 2; restore `fastsurfer_recon/` from that branch and revert import/path/config edits if needed.
- No database or external API changes; rollback is file and config only.

---

## 10. Summary checklist

| Item | Action |
|------|--------|
| Move fastsurfer_recon/* → fastsurfer_surfrecon/ | Move all files/dirs |
| config.py: _BRAINANA_ROOT | `.parent.parent.parent` |
| config.py: find_default_config package_root | `Path(__file__).parent` |
| config.py: comments | Update path description |
| pyproject.toml: package data | `atlas/**/*` (drop fastsurfer_recon/) |
| nhp_mri_prep/steps/anatomical.py | fastsurfer_surfrecon.* imports |
| scripts: sys.path | Add src, not fastsurfer_surfrecon |
| scripts: imports | fastsurfer_surfrecon.* |
| Optional: logger names | fastsurfer_surfrecon in getLogger() |
| Optional: docs | Paper + IMPORT_IMPROVEMENT_PLAN |
| Remove fastsurfer_recon/ | After move |

End of plan.
