# Docker Image Slim-Down Plan

**Date:** 2026-02-07 (revised)
**Current image size:** 40.2 GB (`brainana:latest`)
**Target:** ~18-20 GB

---

## Layer-by-layer size breakdown (from `docker history`)

| Layer                              | Size    | % of Total |
|------------------------------------|---------|------------|
| FreeSurfer 7.4.1 install           | 15.3 GB | 38%        |
| FSL 6.0.5.1 install                | 9.51 GB | 24%        |
| chmod layer (duplicates venv/proj) | 6.89 GB | 17%        |
| Python venv COPY                   | 6.63 GB | 16%        |
| Apt runtime packages               | 809 MB  | 2%         |
| ANTs COPY                          | 355 MB  | 1%         |
| brainana project COPY              | 266 MB  | <1%        |
| AFNI install                       | 263 MB  | <1%        |
| Debian bookworm-slim base          | 75 MB   | <1%        |
| Nextflow + uv + misc              | ~80 MB  | <1%        |

---

## What the pipeline actually uses

### FSL commands used (7 total)
- `flirt` -- registration
- `mcflirt` -- motion correction
- `fslmaths` -- image math (-Tmean, -mas, -mul, -div, -abs, -bin)
- `fslstats` -- statistics (-M)
- `fslroi` -- volume extraction
- `convert_xfm` -- transform matrix inversion
- `fslval` -- version info (Docker welcome msg only)

Source: all invoked via Python subprocess in `src/nhp_mri_prep/`

### FreeSurfer commands used (~30 total via fastsurfer_surfrecon)

**Direct ELF binaries:**
- `mri_convert`, `mri_mask`, `mri_normalize`, `mri_pretess`, `mri_mc`,
  `mri_cc`, `mri_fill`, `mri_add_xform_to_header`, `mri_surf2volseg`
- `mris_info`, `mris_extract_main_component`, `mris_remesh`, `mris_smooth`,
  `mris_inflate`, `mris_place_surface`, `mris_fix_topology`,
  `mris_remove_intersection`, `mris_autodet_gwstats`, `mris_curvature_stats`,
  `mris_volmask`, `mris_register`, `mris_ca_label`, `mris_curvature`,
  `mris_anatomical_stats`, `mris_euler_number`, `mris_convert`
- `talairach_avi`, `lta_convert` (tcsh scripts)

**recon-all sub-steps invoked:**
- `-autodetgwstats` (s13), `-cortex-label` (s14), `-curvHK` (s14),
  `-sphere` (s17), `-jacobian_white` (s17), `-avgcurv` (s17),
  `-cortribbon` (s18), `-curvstats` (s19),
  `-hyporelabel` (s20), `-apas2aseg` (s20)

Source: invoked via Python wrappers in `src/fastsurfer_surfrecon/`

### AFNI commands used (4 total)
- `3dTshift` -- slice timing correction
- `3dDespike` -- despiking
- `3dresample` -- resampling/reorientation
- `3dinfo` -- metadata (-n4, -ad3, -orient)

### FreeSurfer `average/` files needed at runtime

**By `talairach_avi` (s04_talairach):**
- `mni305.cor.mgz` and related `mni305.*`, `mni152.*` files
- `711-2C_as_mni_average_305.4dfp.*` (default registration target)
- `711-2B_as_mni_average_305*.4dfp.*` (alternate target)
- `3T18yoSchwartzReactN32_as_orig.4dfp.*` (atlas option from wrapper)
- `mni_average_305.4dfp.*`

**By `recon-all` substeps:**
- ALL `RB_all_*.gca` files -- volumetric segmentation atlas
  (confirmed needed: user hit runtime error for RB_all_2020-01-02.gca)
- `talairach_mixed_with_skull.gca` -- skull stripping
- `face.gca` -- skull stripping
- `aseg+spmhead+vermis+pons.ixi.gca` -- aseg atlas
- `wmsa_new_eesmith.gca` -- white matter annotation
- `colortable_*.txt` -- parcellation color tables

**By `mris_register` / `mris_ca_label` / `recon-all -avgcurv` (s17):**
- ALL `*.gcs` files -- surface classifier atlases
- ALL `*.tif` files -- folding/curvature atlases
- `surf/` -- surface templates

**Other small files likely needed:**
- `label_scales.dat`, `rigidly_aligned_brain_template.tif`,
  `tissue_parms.txt`, `pons.mni152.2mm.mgz`

---

## Changes to implement

### Change 1: Fix chmod layer duplication (~6.89 GB saved) -- LOW RISK

**Problem:** Dockerfile line 326 runs `chmod -R 755 /opt/brainana /opt/venv /home/neuro`.
In Docker, chmod on COPY'd files creates a full duplicate in a new layer.
This duplicates the 6.63 GB venv + 266 MB project = ~6.89 GB wasted.

**Fix:** Use `COPY --chmod=755` on the two COPY instructions (lines 320-321)
and remove `/opt/brainana` and `/opt/venv` from the chmod RUN command.

**Before (lines 320-327):**
```dockerfile
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=python-builder /opt/brainana /opt/brainana

RUN mkdir -p /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod 1777 /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod -R 755 /opt/brainana /opt/venv /home/neuro && \
    chmod +x /opt/brainana/entrypoint.sh
```

**After:**
```dockerfile
COPY --chmod=755 --from=python-builder /opt/venv /opt/venv
COPY --chmod=755 --from=python-builder /opt/brainana /opt/brainana

RUN mkdir -p /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod 1777 /tmp/matplotlib /tmp/pycache /tmp/.X11-unix /tmp/home && \
    chmod -R 755 /home/neuro && \
    chmod +x /opt/brainana/entrypoint.sh
```

**Risk:** None. Same permissions, just applied at COPY time instead of in a separate layer.

---

### Change 2: Prune FSL directories (~2.75 GB saved) -- LOW RISK

**Problem:** FSL is installed as a full 9.51 GB tarball with zero cleanup.

**Directories to remove** (pipeline does not reference any of these):

| Directory       | Size    | Purpose                    | Used? |
|-----------------|---------|----------------------------|-------|
| `data/`         | 2.3 GB  | Atlases, templates, models | No    |
| `src/`          | 257 MB  | Source code                | No    |
| `doc/`          | 188 MB  | Documentation              | No    |
| `tcl/`          | 2.4 MB  | Tcl/Tk scripts             | No    |
| `refdoc/`       | 324 KB  | Reference docs             | No    |
| **Total**       | **~2.75 GB** |                       |       |

**Leave untouched:**
- `bin/` (4.4 GB) -- per user request, do not prune individual binaries
- `lib/` (1.5 GB) -- shared libraries needed by FSL binaries
- `extras/` (339 MB) -- may contain runtime deps
- `etc/` (5 MB) -- FSL config

**Verification:** `grep -r 'FSLDIR.*data\|fsl.*standard\|MNI152' src/` returns zero matches.
The pipeline uses only `flirt`, `mcflirt`, `fslmaths`, `fslstats`, `fslroi`, `convert_xfm`
-- none of which require files from `$FSLDIR/data/`.

**Before (lines 180-181):**
```dockerfile
RUN curl -fsSL "https://fsl.fmrib.ox.ac.uk/fsldownloads/fsl-${FSL_VERSION}-centos7_64.tar.gz" \
    | tar xz -C /usr/local
```

**After:**
```dockerfile
RUN curl -fsSL "https://fsl.fmrib.ox.ac.uk/fsldownloads/fsl-${FSL_VERSION}-centos7_64.tar.gz" \
    | tar xz -C /usr/local && \
    rm -rf ${FSLDIR}/data \
           ${FSLDIR}/src \
           ${FSLDIR}/doc \
           ${FSLDIR}/refdoc \
           ${FSLDIR}/tcl
```

**Risk:** Low. None of these are runtime dependencies.
The `rm` is in the same `RUN` as the `tar`, so it won't create an extra layer.

---

### Change 3: Prune FreeSurfer (~11.6 GB saved) -- MEDIUM RISK

**Problem:** FreeSurfer is 15.3 GB with minimal pruning.
The current Dockerfile only removes `subjects/`, `docs/`, `matlab/`, `trctrain/`.
Also, the `|| true` on line 208 swallows rm errors and may have prevented
previous cleanup from actually working.

**FreeSurfer subdirectory analysis:**

| Directory    | Size    | Action                                                |
|--------------|---------|-------------------------------------------------------|
| `python/`    | 6.7 GB  | REMOVE -- all used FS commands are ELF binaries       |
| `average/`   | 4.0 GB  | PRUNE to ~1.45 GB -- remove standalone feature dirs   |
| `models/`    | 1.9 GB  | REMOVE -- pipeline uses own fastsurfer_nn models      |
| `bin/`       | 1.4 GB  | KEEP                                                  |
| `lib/`       | 371 MB  | KEEP                                                  |
| `mni-1.4/`   | 156 MB  | KEEP (safety)                                         |
| `mni/`       | 103 MB  | KEEP (referenced in ENV vars)                         |
| `subjects/`  | removed | Already removed (original Dockerfile)                 |
| `docs/`      | removed | Already removed (original Dockerfile)                 |
| `matlab/`    | removed | Already removed (original Dockerfile)                 |
| `trctrain/`  | removed | Already removed (original Dockerfile)                 |
| `fsfast/`    | 6.9 MB  | REMOVE                                                |
| `tktools/`   | 556 KB  | REMOVE                                                |
| `diffusion/` | 408 KB  | REMOVE                                                |

**`average/` conservative pruning -- remove ONLY standalone feature dirs:**

| Remove from average/             | Size    | Why safe                                              |
|----------------------------------|---------|-------------------------------------------------------|
| `mult-comp-cor/`                 | 1.3 GB  | Group-level multiple comparison (not individual)      |
| `samseg/`                        | 543 MB  | Standalone SAMSEG tool (pipeline doesn't call it)     |
| `SVIP_*.4dfp.*` (all)            | ~450 MB | Study-specific data (only in a comment in recon-all)  |
| `mideface-atlas/`               | 81 MB   | Face de-identification (not used)                     |
| `Yeo_Brainmap_MNI152/`          | 72 MB   | Resting-state parcellation reference (not used)       |
| `RLB700_atlas_as_orig.4dfp.*`   | ~65 MB  | Only in a comment in recon-all                        |
| `HippoSF/`                      | 20 MB   | Hippocampal subfields (separate standalone tool)      |
| `ThalamicNuclei/`               | 7.4 MB  | Thalamic nuclei (separate standalone tool)            |
| `Buckner_JNeurophysiol11_MNI152/`| 5.6 MB | Cerebellar atlas (not used)                           |
| `Yeo_JNeurophysiol11_MNI152/`   | 2.9 MB  | Functional parcellation (not used)                    |
| `Choi_JNeurophysiol12_MNI152/`  | 2.7 MB  | Functional parcellation (not used)                    |
| `BrainstemSS/`                   | 1.8 MB  | Brainstem substructures (separate standalone tool)    |
| **Total removed from average/**  | **~2.55 GB** |                                                  |

**KEEP in average/ (~1.45 GB):** all `.gca`, `.gcs`, `.tif`, `.4dfp` atlas files
(used by talairach_avi, recon-all, mris_register, mris_ca_label),
all `colortable_*.txt`, `mni305.*`, `mni152.*`, `surf/`, small metadata files.

**Lesson learned:** The original plan tried to prune `average/` to just 4 files.
This broke `recon-all -hyporelabel` which internally needs `RB_all_2020-01-02.gca`.
FS binaries can have default GCA paths compiled in. The revised approach only removes
clearly standalone feature directories, not individual atlas files.

**Implementation:**
```dockerfile
RUN curl -fsSL "..." -o /tmp/freesurfer.tar.gz && \
    tar --no-same-owner -xzf /tmp/freesurfer.tar.gz -C /usr/local && \
    rm -f /tmp/freesurfer.tar.gz && \
    # ---- prune FreeSurfer (15.3 GB -> ~3.6 GB) ----
    # Remove bundled Python (6.7 GB) -- all used FS commands are ELF binaries
    rm -rf "${FREESURFER_HOME}/python" && \
    # Remove ML models (1.9 GB) -- pipeline uses own fastsurfer_nn models
    rm -rf "${FREESURFER_HOME}/models" && \
    # Remove dirs not used by pipeline
    rm -rf "${FREESURFER_HOME}/subjects" \
           "${FREESURFER_HOME}/docs" \
           "${FREESURFER_HOME}/matlab" \
           "${FREESURFER_HOME}/trctrain" \
           "${FREESURFER_HOME}/fsfast" \
           "${FREESURFER_HOME}/tktools" \
           "${FREESURFER_HOME}/diffusion" && \
    # Prune average/ (4.0 GB -> ~1.45 GB) -- remove standalone feature dirs only
    rm -rf "${FREESURFER_HOME}/average/mult-comp-cor" \
           "${FREESURFER_HOME}/average/samseg" \
           "${FREESURFER_HOME}/average/mideface-atlas" \
           "${FREESURFER_HOME}/average/Yeo_Brainmap_MNI152" \
           "${FREESURFER_HOME}/average/Buckner_JNeurophysiol11_MNI152" \
           "${FREESURFER_HOME}/average/Yeo_JNeurophysiol11_MNI152" \
           "${FREESURFER_HOME}/average/Choi_JNeurophysiol12_MNI152" \
           "${FREESURFER_HOME}/average/HippoSF" \
           "${FREESURFER_HOME}/average/ThalamicNuclei" \
           "${FREESURFER_HOME}/average/BrainstemSS" && \
    # Remove study-specific 4dfp images not needed at runtime
    rm -f "${FREESURFER_HOME}"/average/SVIP_*.4dfp.* \
          "${FREESURFER_HOME}"/average/RLB700_atlas_as_orig.4dfp.*
```

**Risk:**
- `python/` removal: low -- verified all used FS commands are ELF binaries.
  `recon-all` is tcsh and doesn't import Python for the substeps we invoke.
- `models/` removal: low -- SynthSeg/SynthSR/easyreg models not called by pipeline.
- `average/` pruning: low -- only removing standalone feature directories
  (group stats, SAMSEG, defacing, hippocampal/thalamic/brainstem sub-segmentation,
  study-specific images). All `.gca`, `.gcs`, `.tif`, `.4dfp` atlas files kept.

**Also fix:** Change `-xzvf` to `-xzf` (drop verbose flag) to avoid storing
the massive filename list in the build log.

---

### Change 4: Clean Python venv in builder (~1-2 GB saved) -- LOW RISK

**Problem:** The venv is 6.63 GB which is large. Contains caches, test dirs, .pyc files.

**Fix:** Add cleanup step in the python-builder stage after `uv sync`:

**After the existing uv sync block (line 67), add:**
```dockerfile
RUN find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -type d -name "test" -exec rm -rf {} + 2>/dev/null; \
    find /opt/venv -name "*.pyc" -delete 2>/dev/null; \
    find /opt/venv -name "*.pyo" -delete 2>/dev/null; \
    true
```

**Risk:** Low. Removing __pycache__/.pyc just means they get regenerated on first import.
Removing test/ directories saves space; no production code imports from test dirs.

---

## Estimated savings summary

| Change                                         | Savings     | Risk   |
|------------------------------------------------|-------------|--------|
| 1. Fix chmod layer duplication                 | ~6.89 GB    | Low    |
| 2. Prune FSL data/src/doc/tcl/refdoc           | ~2.75 GB    | Low    |
| 3a. Remove FS python/                          | ~6.7 GB     | Low    |
| 3b. Remove FS models/                          | ~1.9 GB     | Low    |
| 3c. Remove FS subjects/docs/matlab/trctrain etc| ~0.5 GB     | Low    |
| 3d. Prune FS average/ (standalone features)    | ~2.55 GB    | Low    |
| 4. Clean Python venv                           | ~1-2 GB     | Low    |
| **Total**                                      | **~21-23 GB** |      |

**Projected final size: ~17-19 GB** (down from 40.2 GB, ~55% reduction)

---

## Rollback plan

If the slimmed image breaks:
1. Check which FS/FSL command failed and what file it tried to access.
2. The original Dockerfile is in git history -- revert specific changes.
3. Most likely failure point: a FreeSurfer command needing a file from
   `average/` or `python/`. Fix: add back the specific file/directory.

## Verification after build

```bash
# Quick smoke test -- verify all used commands exist and run
docker run --rm brainana:latest bash -c "
    flirt -version &&
    mcflirt -version 2>&1 | head -1 &&
    fslmaths --help 2>&1 | head -1 &&
    fslstats --help 2>&1 | head -1 &&
    fslroi 2>&1 | head -1 &&
    convert_xfm --help 2>&1 | head -1 &&
    mri_convert --version 2>&1 | head -1 &&
    mri_mask --help 2>&1 | head -1 &&
    mri_normalize --help 2>&1 | head -1 &&
    mris_anatomical_stats --help 2>&1 | head -1 &&
    mri_surf2volseg --help 2>&1 | head -1 &&
    mris_convert --help 2>&1 | head -1 &&
    3dTshift -help 2>&1 | head -1 &&
    3dDespike -help 2>&1 | head -1 &&
    3dresample -help 2>&1 | head -1 &&
    3dinfo -help 2>&1 | head -1 &&
    echo 'ALL COMMANDS OK'
"

# Verify average/ atlas files are intact
docker run --rm brainana:latest bash -c "
    ls /usr/local/freesurfer/average/RB_all_2020-01-02.gca &&
    ls /usr/local/freesurfer/average/lh.folding.atlas.acfb40.noaparc.i12.2016-08-02.tif &&
    ls /usr/local/freesurfer/average/lh.DKaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs &&
    ls /usr/local/freesurfer/average/talairach_mixed_with_skull.gca &&
    ls /usr/local/freesurfer/average/mni305.cor.mgz &&
    echo 'ATLAS FILES OK'
"

# Check final image size
docker images brainana:latest
```
