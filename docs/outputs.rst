Outputs
=======

Brainana writes all results under the **output directory** you specify (e.g. ``/output`` when using Docker). Outputs follow a BIDS derivatives layout.

Directory layout
----------------

.. code-block:: text

   output_dir/
   ├── sub-<id>/
   │   ├── [ses-<id>/]
   │   │   ├── anat/        # anatomical derivatives
   │   │   └── func/        # functional derivatives
   │   └── figures/         # QC figures (per subject)
   ├── fastsurfer/          # surface reconstruction outputs (when enabled)
   ├── nextflow_reports/    # Nextflow execution logs and trace
   └── sub-<id>_report.html # browsable QC report (per subject)

Anatomical outputs (``anat/``)
------------------------------

Files are named using BIDS derivative conventions. ``<prefix>`` includes subject, session, and run entities
(e.g. ``sub-001_ses-01_run-1``).

For files using the ``space-<space>`` entity (for example, ``space-scanner`` or
``space-NMT2Sym``), refer to :doc:`spaces_and_transforms` for space definitions
and transform direction conventions.

*Preprocessed images — T1w space*

- ``<prefix>_desc-preproc_T1w.nii.gz`` — Preprocessed T1w in T1w space.
- ``<prefix>_desc-preproc_T1w_brain.nii.gz`` — Preprocessed T1w, skullstripped.
- ``<prefix>_desc-brain_mask.nii.gz`` — Binary brain mask.
- ``<prefix>_desc-brain_hemimask.nii.gz`` — Hemisphere mask.
- ``<prefix>_desc-brain_atlasARM2.nii.gz`` — ARM2 atlas segmentation.
- ``<prefix>_desc-brain_atlasARM2.tsv`` — Color LUT for the atlas segmentation.

*Atlas backprojection*

When registration is enabled, atlas volumes are backprojected from template space to two spaces:

- T1w space (``atlas_space-T1w/``)
- Scanner space (``atlas_space-scanner/``)

*T2w outputs (when T2w data are present)*

- ``<prefix>_desc-preproc_T2w.nii.gz`` — Preprocessed T2w.
- ``<prefix>_space-T1w_desc-preproc_T2w.nii.gz`` — T2w co-registered to T1w space.
- ``<prefix>_desc-preproc_T1wT2wCombined.nii.gz`` — T1w/T2w combined image (T2w-enhanced contrast, T1w space).

*Template-space images*

- ``<prefix>_space-<template>_desc-preproc_T1w.nii.gz`` — T1w registered to template space.
- ``<prefix>_space-<template>_desc-preproc_T2w.nii.gz`` — T2w registered to template space.
- ``<prefix>_space-<template>_desc-brain_mask.nii.gz`` — Brain mask in template space.

*Transform files*

- ``<prefix>_from-scanner_to-T1w_mode-image_xfm.mat`` — Scanner-to-T1w conformation transform (FSL ``.mat``).
- ``<prefix>_from-T1w_to-scanner_mode-image_xfm.mat`` — Inverse conformation transform.
- ``<prefix>_from-T1w_to-<template>_mode-image_xfm.<ext>`` — T1w-to-template registration (ANTs ``.h5`` or fireANTS ``.nii.gz``).
- ``<prefix>_from-<template>_to-T1w_mode-image_xfm.<ext>`` — Template-to-T1w inverse registration.
- ``<prefix>_from-T2w_to-T1wScanner_mode-image_xfm.<ext>`` — T2w-to-T1wScanner registration transform.
- ``<prefix>_from-T1wScanner_to-T2w_mode-image_xfm.<ext>`` — T1wScanner-to-T2w registration transform.

Functional outputs (``func/``)
-------------------------------

Session-level files (no task/run entity) are shared across all runs in the session; per-run files include
task and run entities (e.g. ``sub-001_ses-01_task-resting_run-1``).
**Session-level files are produced only when within-session coregistration is enabled** (``func.coreg_runs_within_session``).
When it is disabled, the brain mask, BOLD reference, and transform files below are produced **per-run** (same names but with ``<run_prefix>``).

*Session-level files* (when coreg enabled)

- ``<ses_prefix>_desc-brain_mask.nii.gz`` — Brain mask for functional data (BOLD space).
- ``<ses_prefix>_desc-coreg_boldref.nii.gz`` — BOLD reference image used for func-to-anat coregistration.

*Transform files* (session-level when coreg enabled; per-run when coreg disabled)

- ``<prefix>_from-bold_to-T1w_mode-image_xfm.<ext>`` — BOLD-to-T1w coregistration transform (ANTs ``.h5`` or fireANTS ``.nii.gz``).
- ``<prefix>_from-T1w_to-bold_mode-image_xfm.<ext>`` — T1w-to-BOLD transform.
- ``<prefix>_from-scanner_to-bold_mode-image_xfm.mat`` — Scanner-to-BOLD conformation transform.
- ``<prefix>_from-bold_to-scanner_mode-image_xfm.mat`` — Inverse conformation transform.

*Per-run files — BOLD space*

- ``<run_prefix>_desc-preproc_bold.nii.gz`` — Preprocessed BOLD in BOLD space.
- ``<run_prefix>_desc-preproc_boldref.nii.gz`` — BOLD reference in BOLD space.

*Per-run files — T1w space*

- ``<run_prefix>_space-T1w_desc-preproc_bold.nii.gz`` — Preprocessed BOLD registered to T1w space.
- ``<run_prefix>_space-T1w_desc-preproc_boldref.nii.gz`` — BOLD reference in T1w space.
- ``<run_prefix>_space-T1w_desc-brain_mask.nii.gz`` — Brain mask in T1w space.

*Per-run files — template space*

- ``<run_prefix>_space-<template>_desc-preproc_bold.nii.gz`` — Preprocessed BOLD registered to template space.
- ``<run_prefix>_space-<template>_desc-preproc_boldref.nii.gz`` — BOLD reference in template space.
- ``<run_prefix>_space-<template>_desc-brain_mask.nii.gz`` — Brain mask in template space.

*Per-run files — Confounds*

- ``<run_prefix>_desc-confounds_timeseries.tsv`` — Motion/confound table with columns:
  ``rot_x``, ``rot_y``, ``rot_z`` (radians), ``trans_x``, ``trans_y``, ``trans_z`` (mm), and ``enorm``.
  ``enorm`` is the L2 norm of backward frame-to-frame differences.

Surface reconstruction outputs (``fastsurfer/``)
-------------------------------------------------

When surface reconstruction is enabled, FreeSurfer-compatible outputs are written under ``fastsurfer/<subject_id>/``. 
This includes cortical surface meshes, parcellations, and morphometric files (thickness, area, curvature).

Quality control reports
------------------------

- ``sub-<id>_report.html`` — Brainana outputs a browsable HTML report with summaries, all QC snapshots, and methods. View a `sample report for sub-example <_static/QCreport_example/sub-example.html>`_.
