Processing pipeline details
===========================

brainana adapts its pipeline depending on what data and metadata are available and on the configuration you provide. For example, anatomical synthesis runs only when multiple T1w or T2w runs/sessions are present and synthesis is enabled; slice timing correction runs only when slice timing information is available in the BIDS metadata.

A high-level view of the pipeline is: **BIDS input** → **discovery** (job creation) → **anatomical branch** (synthesis when needed, then reorient, conform, skull stripping & segmentation, bias correction, registration; optionally surface reconstruction) → **functional branch** (slice timing, motion correction, despiking, optional within-session coregistration, bias correction, conform, skull stripping, registration) → **derivatives and QC**.

The design and methods are described in detail in the repository under ``docs/paper/`` (e.g. `03-design-and-architecture.md`, `04-core-components-and-methods.md`).


sMRI preprocessing
------------------

The anatomical preprocessing workflow turns raw (or synthesized) T1w/T2w into bias-corrected, skull-stripped, and template-registered images. It optionally produces segmentations and cortical surfaces. Anatomical outputs feed the T2w and functional workflows as a single reference per subject/session.

**Order of steps (T1w):** Raw or synthesized T1w → Reorient (optional) → Conform → Skull stripping & segmentation → Bias correction → Registration to template → (optional) Surface reconstruction.

**T2w branch:** Synthesized or single T2w is reoriented, registered to the preprocessed T1w, conformed using the T1w conform, bias-corrected, and optionally combined with T1w for joint processing. T2w can be used in surface reconstruction when configured.


Anatomical synthesis (multiple runs/sessions)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When multiple T1w or T2w images exist per session or per subject, brainana can synthesize a single anatomical reference.

- **Reference:** The first file (by lexicographic order) is used as the fixed reference.
- **Coregistration:** Each other image is rigidly coregistered to the reference using **ANTs**.
- **Averaging:** All coregistered images (including the reference) are averaged in the reference space.
- **Output:** One synthesized NIfTI per (subject, session) or per subject, with BIDS naming that drops ``run`` (and optionally ``ses`` for subject-level synthesis).

Synthesis is controlled by configuration (e.g. ``anat.synthesis_level``, ``anat.synthesis_type``). The result is the single anatomical input to the rest of the anatomical pipeline.


Reorient and conform
~~~~~~~~~~~~~~~~~~~~

- **Reorient:** Images are reoriented to a target orientation (e.g. RAS or template orientation) to standardize orientation before conform and registration. This step can be enabled or disabled in config.
- **Conform:** The image is conformed so the brain is upright and aligned to the template space. Conform uses **FLIRT** (FSL) for rigid registration to the template and may use the **UNet** skull-stripping model to support alignment. Outputs include conformed image and transforms (scanner ↔ template).


Skull stripping and segmentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Produce a brain mask and tissue/parcellation segmentation for masking and downstream surface reconstruction.
- **Method:** A **FastSurfer-style** segmentation (in ``fastsurfer_nn``) is used, with models retrained for macaque MRI (e.g. CHARM/SARM level 2 atlas). The brain mask is derived from the segmentation.
- **Outputs:** Brain mask, brain-only image, optional hemisphere mask and atlas-labelled segmentation (and LUT). These feed bias correction, T1w+T2w combined processing when enabled, and surface reconstruction.


Bias field correction
~~~~~~~~~~~~~~~~~~~~~

- **Method:** **N4-style** bias field correction. The brain mask from skull stripping restricts the correction to the brain.
- **Output:** Bias-corrected full-head and bias-corrected brain images (e.g. ``desc-biascorrect_T1w.nii.gz``, ``desc-biascorrect_T1w_brain.nii.gz``). The bias-corrected brain is used for registration to template.


Registration to template
~~~~~~~~~~~~~~~~~~~~~~~~

- **Method:** **ANTs** registration (in ``src/nhp_mri_prep/operations/registration.py``). A multi-stage approach is used: translation → rigid → affine → (optional) SyN. Parameters (gradient step, metric, shrink factors, convergence, smoothing) are configurable.
- **Template:** By default the **NMT2Sym** macaque template is used (e.g. ``NMT2Sym:res-05``). The output space can be set via ``template.output_space`` in the config.
- **Output:** Template-space anatomical, forward and inverse transforms. Functional and T2w workflows use these transforms to map data into template or preprocessed anatomical space.


Surface reconstruction (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Purpose:** Build cortical surfaces from the brain segmentation.
- **Input:** Preprocessed anatomical and segmentation (from FastSurfer-style step). Optionally uses a T1w+T2w combined image when configured.
- **Method:** A FastSurfer-like surface pipeline: mesh extraction, inflation, and registration to an atlas (atlas and config under ``fastsurfer_surfrecon/``).
- **Output:** Surface meshes and derived measures in BIDS derivatives layout. This step is optional and resource-intensive; a FreeSurfer license may be required when using FreeSurfer-based components.


fMRI preprocessing
------------------

The functional workflow preprocesses BOLD data and produces motion-corrected, optionally slice-time-corrected, despiked, bias-corrected, and skull-stripped BOLD in native or template space, with confounds and QC.

**Time-series steps:** BOLD → Slice timing correction (if metadata available) → Reorient (optional) → Motion correction (and temporal mean) → Despiking → Optional within-session coregistration and session-averaged temporal mean.

**Compute on temporal mean:** Bias correction → Conform → Brain mask (UNet on mean) → Registration (mean BOLD to anatomical/template).

**Apply to 4D:** The conform and registration transforms are applied to the full 4D BOLD and to the brain mask to produce the final preprocessed BOLD and mask.


Slice timing correction
~~~~~~~~~~~~~~~~~~~~~~~

When **SliceTiming** (or equivalent) is available in the BIDS metadata for the BOLD series, slice timing correction is applied.

- **Method:** Typically **AFNI** ``3dTshift`` or **FSL**-based correction; slices are realigned in time to a reference (e.g. middle of the TR).
- This step can be disabled via configuration or if slice timing information is missing.


Motion correction
~~~~~~~~~~~~~~~~~

- **Method:** **AFNI** or **FSL** (e.g. MCFLIRT) for volume realignment. A reference volume (e.g. middle frame or temporal mean) is used.
- **Output:** Realigned 4D BOLD, motion parameters (confounds), and a temporal mean image used for subsequent bias correction, conform, skull stripping, and registration.


Despiking
~~~~~~~~~

- **Method:** **AFNI**-style despiking to reduce the impact of extreme timepoints.
- Applied after motion correction in the time series.


Within-session coregistration (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When multiple BOLD runs exist per session, an optional within-session coregistration step can align runs to a common reference and produce a session-averaged temporal mean. This improves stability of the mean used for bias correction, conform, and registration.


Bias correction, conform, and skull stripping (functional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Bias correction:** **N4-style** bias field correction applied on the (session-averaged or run) temporal mean; the derived field can be applied to the 4D BOLD.
- **Conform:** The mean functional is conformed to template space using **FLIRT** and the same approach as anatomical conform.
- **Skull stripping:** A **UNet** functional skull-stripping model is run on the temporal mean to produce a brain mask. The same mask is used for the full 4D BOLD.


Registration (functional)
~~~~~~~~~~~~~~~~~~~~~~~~~

- **Method:** **ANTs** registers the mean BOLD to the preprocessed anatomical (or template). The resulting transform is applied to the full 4D BOLD and brain mask via ``antsApplyTransforms`` (or equivalent).
- **Output:** Preprocessed BOLD and mask in anatomical or template space, plus motion and other confounds for downstream analysis.


Summary table
------------

| Domain     | Step                    | Main tool / method              |
|-----------|-------------------------|----------------------------------|
| Anatomical| Synthesis               | ANTs rigid + average             |
| Anatomical| Reorient                | AFNI (optional)                   |
| Anatomical| Conform                 | FLIRT + UNet skullstrip          |
| Anatomical| Skull strip & segment   | FastSurfer-style (fastsurfer_nn) |
| Anatomical| Bias correction         | N4 (mask-restricted)             |
| Anatomical| Registration            | ANTs                             |
| Anatomical| Surface recon           | fastsurfer_surfrecon (optional)   |
| Functional| Slice timing            | AFNI / FSL                       |
| Functional| Reorient                | AFNI (optional)                   |
| Functional| Motion correction       | AFNI / FSL                       |
| Functional| Despiking               | AFNI                             |
| Functional| Within-session coreg    | ANTs (optional)                  |
| Functional| Bias correction         | N4                               |
| Functional| Conform                 | FLIRT + UNet skullstrip          |
| Functional| Skull strip (brain mask)| UNet                             |
| Functional| Registration            | ANTs                             |

For outputs and directory layout, see :doc:`outputs`. For design and methods details, see the repository docs under ``docs/paper/``.

