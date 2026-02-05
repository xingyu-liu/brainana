# Template zoo subfolders: code update plan

**Goal:** Make existing code work with the new `template_zoo/` layout (subfolders) instead of the old flat layout.

**Current layout (after refactor):**
```
template_zoo/
├── atlas/
│   └── ARM/
│       ├── atlas-ARM2_space-MEBRAIN_res-04.nii.gz
│       ├── atlas-ARM2_space-NMT2Sym_res-025.nii.gz
│       ├── atlas-ARM2_space-NMT2Sym_res-05.nii.gz
│       └── atlas-ARM2.tsv
└── template/
    ├── MEBRAINS/
    │   └── tpl-MEBRAIN_res-04_*.nii.gz
    └── NMT2Sym/
        └── tpl-NMT2Sym_res-*.nii.gz, etc.
```

**Out of scope:** `fastsurfer_surfrecon`’s `registration_template: template_zoo/fastsurfer/sub-MEBRAIN` is a separate concept (full FreeSurfer-style subject with `surf/`, `label/`, `atlas/`). No change needed there for this plan.

---

## 1. nhp_mri_prep — TemplateManager discovery

**File:** `src/nhp_mri_prep/utils/templates.py`

**Current behavior:** `_discover_templates()` uses `self.template_dir.glob('*.nii.gz')`, so it only sees files directly under `template_zoo/`. With the new layout, no files are found.

**Changes:**

1. **Discovery scope**
   - Restrict discovery to **volume templates** under `template_zoo/template/` (do not discover files under `template_zoo/atlas/`).
   - Use a recursive glob, e.g. `(self.template_dir / "template").glob("**/*.nii.gz")`.
   - If `template_zoo/template/` is missing, keep current behavior as fallback: `self.template_dir.glob('*.nii.gz')` so old flat layouts still work (optional backward compatibility).

2. **Path used as template_dir**
   - Keep `self.template_dir` pointing at `template_zoo` (repo root of the zoo). Only the **glob** should look under `template_zoo/template/`.

3. **Parsing**
   - No change: filenames still follow `tpl-{name}_res-{resolution}[_...]_T1w[_desc].nii.gz`; parsing stays the same. Discovery just feeds more files from subfolders.

4. **Docstring**
   - Update `_discover_templates` docstring to state that templates are discovered under `template_zoo/template/` (and optionally at root for backward compatibility).

**Result:** `resolve_template()`, `list_available_templates()`, and the rest of the API stay the same; they just see all volume templates under `template/`.

---

## 2. fastsurfer_nn — Template and atlas paths

**Files:**  
- `src/fastsurfer_nn/utils/constants.py`  
- `src/fastsurfer_nn/inference/segmentation.py`

**Current behavior:** Paths are built as:
- `TEMPLATE_DIR / "tpl-NMT2Sym_res-05_T1w_brain.nii.gz"`
- `TEMPLATE_DIR / f"atlas-{atlas_name}_space-NMT2Sym_res-05.nii.gz"`
- `TEMPLATE_DIR / f"tpl-NMT2Sym_res-05_T1w_WM_{roi_name}.nii.gz"`

So everything is assumed directly under `template_zoo/`. With the new layout these files live under `template_zoo/template/NMT2Sym/` and `template_zoo/atlas/ARM/`.

**Changes:**

1. **constants.py**
   - Add two optional path constants (or keep only one root and resolve below):
     - `TEMPLATE_ZOO_TEMPLATES = TEMPLATE_DIR / "template"`  (volume templates)
     - `TEMPLATE_ZOO_ATLAS = TEMPLATE_DIR / "atlas"`         (atlas NIfTIs)
   - Keep `TEMPLATE_DIR = REPO_ROOT / "template_zoo"` as the single entry point for the zoo.

2. **segmentation.py**
   - **Template NIfTIs (NMT2Sym):** Resolve by filename under `template/`, e.g.:
     - `tpl_T1w_f`: first match of `TEMPLATE_ZOO_TEMPLATES.glob("**/tpl-NMT2Sym_res-05_T1w_brain.nii.gz")`, or explicitly `TEMPLATE_ZOO_TEMPLATES / "NMT2Sym" / "tpl-NMT2Sym_res-05_T1w_brain.nii.gz"` if we fix the subfolder name.
     - `tpl_roi_wm_f`: same idea for `tpl-NMT2Sym_res-05_T1w_WM_{roi_name}.nii.gz`.
   - **Atlas NIfTI:** Resolve under `atlas/` by filename, e.g.:
     - `tpl_seg_f`: first match of `TEMPLATE_ZOO_ATLAS.glob(f"**/atlas-{atlas_name}_space-NMT2Sym_res-05.nii.gz")`.
   - Prefer **glob-by-filename** under the two roots so that:
     - Subfolder names (e.g. `NMT2Sym`, `ARM`) don’t need to be hardcoded in many places.
     - Adding new spaces or atlases doesn’t require code changes.
   - After resolving, keep the same validation (`if not tpl_*_f.exists(): raise FileNotFoundError(...)`).

3. **Convention**
   - Atlas folder name vs `atlas_name`: current layout has `atlas/ARM/` with files `atlas-ARM2_*`. So `atlas_name` from checkpoint is e.g. `ARM2`; the folder can stay `ARM`. Using a glob `**/atlas-{atlas_name}_space-NMT2Sym_res-05.nii.gz` under `TEMPLATE_ZOO_ATLAS` avoids depending on folder name.

**Result:** fastsurfer_nn finds the same files without assuming a flat `template_zoo/`.

---

## 3. fastsurfer_surfrecon

**Files:** `src/fastsurfer_surfrecon/config/default.yaml`, `stages/s17_registration.py`

**Action:** No code or path layout change for the subfolder refactor. `registration_template` points to a subject-like directory (e.g. `template_zoo/fastsurfer/sub-MEBRAIN` with `surf/`, `label/`, `atlas/`). That can live alongside the new `template/` and `atlas/` volume layout. If `fastsurfer/` is not present in the repo, that’s a separate asset/deployment concern.

---

## 4. Config and defaults

**File:** `src/nhp_mri_prep/config/defaults.yaml` (and any other config that references template paths)

**Action:** Confirm that user-facing options (e.g. `template.output_space`) only use logical names (e.g. `NMT2Sym:res-05`), not filesystem paths. If so, no change. If any config explicitly points at `template_zoo/*.nii.gz`, update to the new layout or remove in favor of logical names.

---

## 5. Tests

**Current state:** No tests in `tests/` reference `resolve_template`, `TemplateManager`, or `template_zoo` paths.

**Suggested additions (optional but recommended):**
- **TemplateManager:** A small test that instantiates `TemplateManager` with a test directory shaped like `template_zoo/template/<Space>/tpl-*.nii.gz`, and checks that `list_available_templates()` or `resolve_template("NMT2Sym:res-05:brain")` returns expected paths.
- **fastsurfer_nn:** If there is an integration test that runs segmentation with template/atlas files, ensure it uses the new paths (or a test fixture with the same subfolder structure).

---

## 6. Documentation and repo metadata

- **README / README_Docker.md:** If they describe a flat `template_zoo/` or “place templates here”, update to the new layout (`template/`, `atlas/`).
- **.gitignore:** Already has `# template_zoo/`; no change needed unless you start ignoring specific subdirs.

---

## 7. Implementation order

1. **nhp_mri_prep/utils/templates.py** — switch discovery to `template_zoo/template/**/*.nii.gz`, add fallback if desired.
2. **fastsurfer_nn/utils/constants.py** — add `TEMPLATE_ZOO_TEMPLATES` and `TEMPLATE_ZOO_ATLAS`.
3. **fastsurfer_nn/inference/segmentation.py** — resolve template and atlas paths via the new constants and glob-by-filename under those roots.
4. **Config/docs** — quick pass to ensure no hardcoded flat paths; update README if needed.
5. **Tests** — add or adjust tests for template discovery and, if applicable, segmentation paths.

---

## 8. Backward compatibility (optional)

- **TemplateManager:** If you still support a flat `template_zoo/` (no `template/` subdir), you can do:  
  `if (self.template_dir / "template").exists(): glob "template/**/*.nii.gz"; else: glob "*.nii.gz"`.
- **fastsurfer_nn:** Similarly, if `TEMPLATE_ZOO_TEMPLATES` doesn’t exist or the glob finds nothing, fall back to `TEMPLATE_DIR / <filename>`. Reduces breakage for anyone who hasn’t restructured their zoo yet.

This plan keeps the refactor as “subfolders are the source of truth” and keeps optional fallbacks small and explicit.
