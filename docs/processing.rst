Processing pipeline details
===========================

brainana adapts its pipeline depending on what data and metadata are
available and on the configuration you provide. For example,
anatomical synthesis runs only when multiple T1w/T2w runs or sessions
are present and synthesis is enabled; slice timing correction runs
only when slice timing information is available in the BIDS metadata.

This page describes the methods used at each stage of the pipeline.


Pipeline overview
-----------------

Results included in analyses processed with brainana come from
preprocessing performed using **brainana**, a BIDS-based,
Nextflow-orchestrated pipeline for macaque (and other NHP)
anatomical and functional MRI. The pipeline adapts to available
data and configuration:

- Anatomical synthesis runs only when multiple T1w/T2w runs or sessions
  are present and synthesis is enabled.
- Slice timing correction runs only when slice timing metadata are
  available in BIDS.
- Surface reconstruction is optional and requires a valid FreeSurfer
  license.


Main software stack
~~~~~~~~~~~~~~~~~~~

- Python 3.11+, Nextflow
- AFNI, ANTs, FSL, FreeSurfer (for optional surface reconstruction)
- PyTorch (UNet skull stripping and FastSurfer-style segmentation)
- nibabel for NIfTI I/O, pybids for BIDS layout/metadata
- Internal models and tools:

  - ``nhp_skullstrip_nn`` (UNet skull stripping model, derived from
    DeepBet/NHP-BrainExtraction)
  - ``fastsurfer_nn`` (FastSurfer-style CNN segmentation, fine-tuned
    for macaque)
  - ``fastsurfer_surfrecon`` (modified FastSurfer recon_surf for
    surface reconstruction)


1. BIDS discovery and job creation
----------------------------------

Before the Nextflow workflow runs, a Python discovery step scans the
BIDS (and NHP-BIDS) dataset and produces structured job descriptors.

- **Purpose:** Determine what data are available and which processing
  branches should run (e.g. whether anatomical synthesis is needed,
  whether functional runs have slice timing metadata).
- **Methods:** Deterministic layout/metadata scan using BIDS entities
  and configuration. Discovery evaluates whether anatomical synthesis
  is needed (``needs_synth``) and decides synthesis type/level
  (session vs. subject) from config. There are **no imaging
  algorithms** at this stage.


2. Anatomical processing
------------------------

The anatomical branch turns raw (or synthesized) T1w/T2w images into
bias-corrected, skull-stripped, and template-registered images, and
optionally segmentations and cortical surfaces. These outputs provide
the anatomical reference for T2w and functional workflows.


2.1 Anatomical synthesis (multiple T1w/T2w)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When multiple T1w or T2w images exist per session or per subject,
brainana can synthesize a single anatomical reference.

- **When:** Multiple T1w or T2w per session or subject (configurable
  synthesis level).
- **Method:** The first image (by lexicographic order) is used as the
  fixed reference. Each other image is rigidly coregistered to the
  reference using ANTs (``antsRegistration`` with a rigid transform).
  All coregistered images, including the reference, are averaged in
  the reference space.
- **Output:** One synthesized NIfTI per (subject, session) or per
  subject, with BIDS naming that drops ``run`` (and for subject-level
  synthesis, ``ses``). The result is the single anatomical input to
  the rest of the anatomical pipeline.


2.2 Reorient
~~~~~~~~~~~~

- **Purpose:** Standardize image orientation (e.g. RAS or template
  orientation) before conform and registration.
- **Method:** AFNI ``3dresample -orient`` is used to reorient each
  image to a target orientation, or to match the orientation of a
  target file when one is provided. This step is configurable and
  can be disabled in the pipeline configuration.


2.3 Conform to template
~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Align the brain to template space (orientation and
  grid) so that subsequent registrations and resamplings are
  well-defined.
- **Method (summary):**

  1. Skull-strip the input with ``nhp_skullstrip_nn`` (UNet) or use
     an existing brain mask when skull stripping is disabled.
  2. Resample the template to match the input resolution if needed.
  3. Run FSL FLIRT (rigid, 6 DOF) from the brain-extracted input to
     the template.
  4. Use AFNI ``3dresample`` to ensure template and input share a
     consistent grid.
  5. Apply the FLIRT transform back to the full-head anatomical with
     ``flirt -applyxfm``.

- **Outputs:** Conformed anatomical image(s) and transforms relating
  scanner space to template space.


2.4 Skull stripping and segmentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Provide brain mask and atlas/tissue segmentation for
  masking, bias correction, registration, and optional surface
  reconstruction.
- **Method:** ``fastsurfer_nn`` (FastSurfer-style CNN segmentation)
  is fine-tuned on macaque anatomical MRI with CHARM and SARM level 2
  atlases (ARM2 parcellation). The network produces an atlas-labelled
  segmentation, from which a brain mask and optional hemisphere masks
  are derived. FSL ``fslmaths -mul`` applies the mask to the
  anatomical to obtain a skull-stripped image.
- **Outputs:** Segmentation volume, brain mask, skull-stripped image,
  and optional hemisphere mask and LUT. These feed T1w+T2w combined
  processing (when enabled) and surface reconstruction.


2.5 Bias field correction (anatomical)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Correct intensity non-uniformity (INU) in anatomical
  images.
- **Method:** N4 bias field correction (ANTs
  ``N4BiasFieldCorrection``) is run on the anatomical image, with the
  brain mask from segmentation optionally provided as ``-x`` to
  restrict correction to brain tissue.
- **Outputs:** Bias-corrected full-head anatomical and
  bias-corrected brain images (e.g.
  ``desc-biascorrect_T1w.nii.gz``,
  ``desc-biascorrect_T1w_brain.nii.gz``). The bias-corrected brain is
  used for registration.


2.6 Registration to template (anatomical)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Map anatomical data to a standard template space (for
  example, NMT2Sym).
- **Method:** Multi-stage ANTs registration in
  ``src/nhp_mri_prep/operations/registration.py``:

  - Translation → rigid → affine → optional SyN.
  - Metrics (e.g. mutual information, cross-correlation, Mattes),
    gradient steps, shrink factors, convergence criteria, and
    smoothing schedules are configurable.
  - When GPU resources and FireANTs are available, the SyN stage can
    be run with FireANTs; otherwise CPU ``antsRegistration`` is used.

- **Outputs:** Template-space anatomical image(s) and composite
  forward and inverse transforms. Downstream T2w and functional
  workflows reuse these transforms to move data between native
  anatomical and template spaces.


2.7 T2w to T1w coregistration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When T2w data are present, brainana can coregister T2w to the
preprocessed T1w:

- **Method:** ANTs rigid registration from T2w to preprocessed T1w,
  followed by ``antsApplyTransforms`` to resample T2w into T1w space
  with a configurable interpolation (e.g. BSpline).
- **Usage:** T2w in T1w space can be used for combined T1w+T2w
  processing and surface reconstruction.


2.8 Surface reconstruction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Surface reconstruction is an optional and resource-intensive step.

- **Purpose:** Build cortical surfaces and derived measures (e.g.
  thickness, area, curvature) from the anatomical segmentation.
- **Inputs:** Preprocessed anatomical, segmentation (from
  ``fastsurfer_nn``), and optionally a combined T1w+T2w image.
- **Method:** ``fastsurfer_surfrecon`` is a modified version of
  FastSurfer's ``recon_surf`` pipeline. It orchestrates FreeSurfer
  volume stages (bias correction, Talairach transform, normalization,
  WM segmentation) and surface stages (tessellation, smoothing,
  inflation, topology fixing, atlas parcellation, morphometry). The
  pipeline calls FreeSurfer tools such as ``mri_convert``,
  ``mri_mask``, ``mri_pretess``, ``mri_fill``, ``mris_smooth``,
  ``mris_inflate``, ``mris_fix_topology``, ``mris_place_surface``,
  ``mris_register``, ``mris_ca_label``, and
  ``mris_anatomical_stats``.
- **Requirements:** A valid FreeSurfer license is required when this
  step is enabled.
- **Outputs:** Cortical surface meshes and derived measures written
  in BIDS derivatives layout where applicable.


3. Functional processing
------------------------

The functional branch preprocesses BOLD data and produces
motion-corrected, optionally slice-time-corrected, despiked,
bias-corrected, and skull-stripped BOLD in native or template space,
with associated transforms and QC outputs.

The workflow is conceptually split into:

- **Time-series steps:** Slice timing (if available) → reorient →
  motion correction and temporal mean → despiking → optional
  within-session coregistration and session-averaged temporal mean.
- **Compute on temporal mean:** Bias correction → conform → brain mask
  (UNet) → registration to anatomical or template.
- **Apply to 4D:** Apply conform and registration transforms to the
  4D BOLD and brain mask.


3.1 Slice timing correction
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When slice timing information is available in BIDS metadata, brainana
applies slice timing correction.

- **Purpose:** Align voxel time series in time according to the slice
  acquisition order.
- **Method:** AFNI ``3dTshift`` is used to shift slices in time to a
  reference (typically the middle of the TR). Slice timing pattern
  (e.g. ``alt+z``, ``seq+z``) is derived from the BIDS
  ``SliceTiming`` and ``SliceEncodingDirection`` fields. If slice
  encoding is not along the z axis, data are swapped to z for
  ``3dTshift`` and swapped back afterwards.
- **Control:** This step can be disabled in configuration or skipped
  when slice timing metadata are missing.


3.2 Reorient
~~~~~~~~~~~~~~~~~~~~~~~~~

- **Method:** Same approach as anatomical reorient, using AFNI
  ``3dresample -orient`` to match a desired orientation or target
  image before motion correction and subsequent steps.


3.3 Motion correction
~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Realign BOLD volumes to correct for subject motion.
- **Method:** FSL ``mcflirt`` performs volume realignment with 6 DOF.
  The reference volume is either a user-specified timepoint, the
  middle volume, or a temporal mean (via ``fslmaths -Tmean`` or
  ``fslroi``). Outputs include motion-corrected 4D BOLD, motion
  matrices, and motion parameters (TSV).
- **Short runs:** For very short runs (e.g. fewer than 15 volumes),
  motion correction can be skipped, and pass-through outputs
  (including a temporal mean and zero-filled motion parameters) are
  generated.


3.4 Despiking
~~~~~~~~~~~~~

- **Purpose:** Reduce the impact of extreme timepoints ("spikes") in
  the BOLD signal.
- **Method:** AFNI ``3dDespike`` is applied to the motion-corrected
  BOLD time series with configurable parameters (e.g. ``-cut`` and
  optional ``-localedit``). The step is skipped for runs of 15 or
  fewer volumes.


3.5 Within-session coregistration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When multiple BOLD runs exist per session, an optional within-session
coregistration step can align runs to a common reference and produce
a session-averaged temporal mean.

- **Purpose:** Improve stability of the temporal mean used for
  bias correction, conform, and registration.
- **Method:** Rigid registration from each run's temporal mean to a
  reference run's temporal mean, using ANTs or FSL FLIRT as
  configured, followed by applying the transform to the 4D BOLD and
  mask.


3.6 Bias correction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Method:** N4 bias field correction (ANTs
  ``N4BiasFieldCorrection``) is applied to the temporal mean of the
  motion-corrected/despiked BOLD. An optional mask can be used, and
  intensities may be rescaled (e.g. to mean 100) depending on config.
- **Usage:** The estimated bias field can be applied to the full 4D
  BOLD in a separate step.


3.7 Conform and skull stripping
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Conform:** The functional temporal mean is conformed to the
  chosen template using the same strategy as anatomical conform:
  ``nhp_skullstrip_nn`` on the mean, FSL FLIRT rigid registration to
  the template, resampling with AFNI ``3dresample``, and application
  of the transform (optionally composed with anatomical transforms).
- **Skull stripping:** A UNet-based functional skull-stripping model
  (``nhp_skullstrip_nn`` EPI model, derived from
  NHP-BrainExtraction/DeepBet) is run on the temporal mean to obtain
  a brain mask, which is then applied to the 4D BOLD with
  ``fslmaths -mas``.


3.8 Registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Method:** ANTs registration (rigid, affine, or SyN as configured)
  from the mean functional image to the preprocessed anatomical or
  directly to the template. Composite transforms are applied to the
  4D BOLD and brain mask with ``antsApplyTransforms`` (e.g. BSpline
  interpolation for BOLD).
- **Outputs:** Preprocessed BOLD and mask in anatomical or template
  space, plus motion and other confounds for downstream analysis.


4. Summary table
----------------

.. list-table::
   :header-rows: 1

   * - Domain
     - Step
     - Main tool / method
   * - Anatomical
     - Synthesis
     - ANTs rigid + average
   * - Anatomical
     - Reorient
     - AFNI 3dresample
   * - Anatomical
     - Conform
     - FLIRT + ``nhp_skullstrip_nn`` + 3dresample
   * - Anatomical
     - Skull strip & segment
     - ``fastsurfer_nn`` (FastSurferCNN fine-tuned)
   * - Anatomical
     - Bias correction
     - ANTs N4BiasFieldCorrection
   * - Anatomical
     - Registration
     - ANTs (optional FireANTs for SyN)
   * - Anatomical
     - Surface recon
     - ``fastsurfer_surfrecon`` + FreeSurfer
   * - Functional
     - Slice timing
     - AFNI 3dTshift
   * - Functional
     - Reorient
     - AFNI 3dresample
   * - Functional
     - Motion correction
     - FSL mcflirt
   * - Functional
     - Despiking
     - AFNI 3dDespike
   * - Functional
     - Within-session coreg
     - ANTs or FLIRT
   * - Functional
     - Bias correction
     - ANTs N4BiasFieldCorrection
   * - Functional
     - Conform / skull strip
     - FLIRT + ``nhp_skullstrip_nn`` + 3dresample
   * - Functional
     - Registration
     - ANTs (optional FireANTs for SyN)

For outputs and directory layout, see :doc:`outputs`.

