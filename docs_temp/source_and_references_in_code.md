# Source and References in Code Comments

This document lists all parts of the brainana codebase where comments or docstrings mention **source**, **references**, or closely related concepts (e.g. citation, boilerplate, docs_temp, methods_reference). It is intended for documentation maintenance and ensuring references stay consistent.

---

## 1. Documentation / manuscript references (docs_temp, methods_reference, boilerplate)

### `src/nhp_mri_prep/quality_control/reports.py`
- **Line 72** (comment):  
  `# Full reference: docs_temp/paper/methods_reference.md and docs_temp/paper/boilerplate_methods.txt`
- **Line 81** (boilerplate text):  
  *"For a detailed reference of methods per step and full citations, see the pipeline documentation (methods_reference.md in the repository)."*
- **Line 84** (boilerplate text):  
  *"Pipeline source code and documentation are available at the project repository."*
- **Line 86** (boilerplate heading):  
  `References`
- **Line 774** (docstring):  
  `"""Create methods section with fMRIPrep-style boilerplate (methods and references), structured with headings and lists."""`
- **Lines 799, 808** (code): Section header `"References"` and block check `block.startswith("References")` for parsing the methods section.

### `nextflow.config`
- **Line 144** (comment):  
  `// See docs_temp/RESOURCE_CALIBRATION.md and docs/RESOURCE_USAGE_SUMMARY.md`

### `docs/outputs.rst`
- **Line 23**:  
  *"For design and architecture, see the repository (e.g. ``docs/paper/``)."*

### `docs/processing.rst`
- **Lines 12–14**:  
  *"derived from the internal paper materials in ``docs_temp/paper`` (including ``methods_reference.md`` and ``04-core-components-and-methods.md``)."*
- **Lines 418–419**:  
  *"For design and architecture details, see the repository docs under ``docs_temp/paper/`` (e.g. ``03-design-and-architecture.md``, ``04-core-components-and-methods.md``)."*

### `docs_temp/DOCUMENTATION_PLAN.md`
- Multiple references to `docs_temp/paper/`, `methods_reference.md`, boilerplate, and sync rules (e.g. lines 11, 13, 15, 25, 27, 28, 40, 82, 92, 97).

### `docs_temp/paper/methods_reference.md`
- **Line 3**:  
  *"This document provides a detailed reference of the methods and software used at each step..."*
- **Lines 43, 51, 58, 65, 72, 84, 95, 106, 142**:  
  **References:** (with RRIDs and citations).
- **Line 177**:  
  `## 6. References (for manuscript / boilerplate)`
- **Lines 190–195**:  
  **RRIDs** (ANTs, AFNI, FSL, FreeSurfer).
- **Lines 201–211**:  
  Describes QC report Methods section, boilerplate, and files `docs_temp/paper/boilerplate_methods.txt` and sync with `reports.py`.

---

## 2. “Single source of truth” / config source

### `src/nhp_mri_prep/utils/gpu_device.py`
- **Lines 4–5** (module docstring):  
  *"Single source of truth for device resolution. Respects CUDA_VISIBLE_DEVICES"*

### `src/nhp_mri_prep/config/config_io.py`
- **Line 116** (docstring of `get_default_config`):  
  *"\_version is set from the brainana package version (single source: pyproject.toml)."*
- **Line 169** (comment):  
  *"Ensure _version always reflects the running package (single source: pyproject.toml)"*

### `src/nhp_mri_prep/config/config.py`
- **Line 16** (docstring):  
  *"config_data: Configuration source (file path or dictionary)"*

### `src/nhp_skullstrip_nn/scripts/run_prediction.py`
- **Lines 104, 129, 132, 142, 159**:  
  Variable `config_source` and logging: config comes from `"checkpoint"`, `"file"`, or `None`; log message: *"Config: {config_source} (...)"*.

---

## 3. File/path “source” (symlink, copy, data location)

### `src/nhp_mri_prep/utils/nextflow.py`
- **Lines 17–61**:  
  `create_output_link(source_file, target_file)` — docstring and comments: *"Create symlink from source to target"*, *"Resolves source symlinks to the original non-symlink file"*, *"source_file: Path to source file"*, *"Resolve source to actual file"*, *"Create symlink pointing to the resolved source"*, *"resolve source before copying"*, *"Fallback to original source"*.

### `src/nhp_skullstrip_nn/config.py`
- **Line 165** (comment):  
  *"HDF5 directory is in TRAINING_DATA_DIR (same location as source data, like fastsurfer_nn)"*

### `src/nhp_mri_prep/operations/synthesis_multiple_anat.py`
- **Lines 54–55**:  
  Log: *"Source runs: ..."*, *"Reference image (run-...): ..."*
- **Lines 62–70, 76, 83–97, 102, 127, 131, 184–188**:  
  Use of first image as **reference**; *"reference_file"*, *"reference_path"*, *"reference_img"*, *"Coregister all other images to the reference"*, *"reference_run"*, *"reference_id"*, *"Create synthesized image using reference header"*.
- **Lines 207–215** (metadata):  
  Keys `"Sources"`, `"SourceRuns"`, `"ReferenceImage"`, `"ReferenceRun"`.

---

## 4. Image/registration “reference” (fixed image, reference space, reference volume)

### `src/nhp_mri_prep/utils/mri.py`
- **Lines 759–795**:  
  `crop_to_reference()` — docstring: *"Crop a padded NIfTI image back to match a reference image's grid"*, *"reference image's affine"*, *"ref_imagef: Original (unpadded) reference image"*, *"use the reference affine"*.

### `src/nhp_mri_prep/steps/anatomical.py`
- **368, 384, 442, 446, 463, 469, 477, 501, 507**:  
  Parameter `t1w_reference` and docstring *"T1w image defining output grid"*, *"Path to T1w reference"*; usage as `fixedf`/`reff` in registration.

### `src/nhp_mri_prep/steps/functional.py`
- **368, 376**:  
  Comments: *"Use the conformed tmean as reference for resampling"*, *"Use conformed tmean as reference"*.
- **569–601, 627–643, 655–657, 663, 672, 691, 694, 721, 732, 741, 761, 788**:  
  `reference_file`, `reference_tmean`, `reference_run`; docstrings *"Reference file for resampling"*, *"Coregister a functional run to a reference run"*, *"Path to reference tmean"*, *"Run identifier for reference"*; use as fixed/reference in registration.
- **829, 843, 870–874**:  
  `reference_img` for header/affine; *"Save first image for header/affine"*, *"Create averaged image using reference header"*.

### `src/nhp_mri_prep/steps/qc.py`
- **149**:  
  *"template_file: Template/reference image"*
- **520**:  
  *"tmean_run1: Tmean from first run (reference)"*

### `src/nhp_mri_prep/quality_control/mri_plotting.py`
- **851, 903**:  
  Docstrings: *"volume_img: Nibabel image object for transformation and shape reference"*, *"transformation reference"*.

### `src/nhp_mri_prep/operations/preprocessing.py`
- **349, 354, 357, 369**:  
  `source_for_padding`, use in padding.
- **484**:  
  *"Resample template to the same resolution as the input, serves as the reference"*
- **860–892**:  
  *"Generate reference volume"*, *"using reference timepoint"*, *"reference type - Tmean"*, *"using middle timepoint as reference"*, *"Reference volume generation failed"*.

### `src/nhp_mri_prep/operations/registration.py`
- **304**:  
  *"fixedf: Fixed (reference) image path"*
- **452–454, 609, 619, 655–657**:  
  *"movingf: Moving (source) image"*, *"reff: Reference image for output space"*, *"--reference-image"*.

### `src/nhp_mri_prep/config/defaults.yaml`
- **58–59**:  
  *"tzero: null  # ... reference time point"*, *"slice_time_ref: 0.5  # ... reference slice time"*
- **68**:  
  *"ref_vol: \"mid\"  # ... reference volume (...)"*

### `src/nhp_mri_prep/config/bids_adapter.py`
- **39**:  
  *"Calculate tzero based on slice timing reference"*

---

## 5. FireANTs / registration “source” (image dimension)

### `src/nhp_mri_prep/operations/fireants_registration.py`
- **Lines 64–65** (docstring):  
  *"FireANTs' ``downsample_fft`` assumes the target size is *smaller* than the source. When an image dimension ``d`` is small..."*

---

## 6. Resource (system/resources, not “source” in a ref sense)

### `src/nhp_skullstrip_nn/utils/threads.py`
- **4, 36, 57**:  
  *"resource cap issues"*, *"avoid resource cap issues"* (thread/resource usage).

### `src/nhp_mri_prep/utils/system.py`
- **73**:  
  *"Maximum allowed threads to prevent excessive resource usage"*

### `src/nhp_mri_prep/quality_control/snapshots.py`
- **628, 638, 645**:  
  *"Get path to Vol_Surface.scene resource file"*, *"resources/Vol_Surface.scene"*, *"quality_control/resources/Vol_Surface.scene"*.

### `src/nhp_mri_prep/environment.py`
- **8, 406–410, 581, 608–609, 625, 755–768**:  
  *"System resource assessment"*, `check_system_resources()`, *"system_resources"*, *"System Resources"* (memory, disk, CPU, GPU).

---

## 7. Config validation “source” (direction mapping)

### `src/nhp_mri_prep/config/config_validation.py`
- **589–604**:  
  Comments: *"Check for duplicate target directions (two sources mapping to same target)"*, *"for source, target in mappings"*, *"Each target direction should be mapped from exactly one source direction."*

---

## 8. FastSurfer / other “source” or “reference”

### `src/fastsurfer_surfrecon/wrappers/registration.py`
- **66**:  
  *"Source volume"* (parameter/docstring).

### `src/fastsurfer_surfrecon/stages/s14_parcellation.py`
- **154**:  
  *"Update smoothwm path reference for inflation step"*

### `src/fastsurfer_surfrecon/stages/s15_surface_placement.py`
- **92**:  
  *"white_surf=white  # Reference white surface"*

---

## 9. Template zoo / atlas references

### `template_zoo/atlas/retinotopy/atlas-retinotopy_info.md`
- **24**:  
  `## References`
- **26–27**:  
  Citation and AFNI NMT template links.

---

## Summary table

| Category                          | Files (main)                                                                 | Purpose |
|-----------------------------------|-------------------------------------------------------------------------------|---------|
| docs_temp / methods_reference     | reports.py, nextflow.config, outputs.rst, processing.rst, DOCUMENTATION_PLAN, methods_reference.md | Documentation and manuscript references |
| Single source of truth / config   | gpu_device.py, config_io.py, config.py, run_prediction.py                     | Version and config source |
| File/path source                  | nextflow.py, config.py (skullstrip), synthesis_multiple_anat.py               | Symlink/copy and data location |
| Image/registration reference      | mri.py, anatomical.py, functional.py, qc.py, mri_plotting.py, preprocessing.py, registration.py, defaults.yaml, bids_adapter.py | Reference image/volume/space |
| FireANTs source                   | fireants_registration.py                                                      | Target vs source size in FFT |
| System resource                   | threads.py, system.py, snapshots.py, environment.py                           | Resources (threads, memory, files) |
| Config validation source/target   | config_validation.py                                                          | Direction mapping |
| FastSurfer                        | registration.py, s14_parcellation.py, s15_surface_placement.py                | Source volume, path reference, reference surface |
| Atlas                              | atlas-retinotopy_info.md                                                      | References section and citations |

---

*Generated from a full codebase review. Update this file when adding or changing comments that refer to sources or references.*
