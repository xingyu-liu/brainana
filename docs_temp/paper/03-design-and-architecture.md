# 3. Design and Architecture (Expanded)

This section describes the high-level design of brainana: how the pipeline is orchestrated, how data flows from BIDS input to derivatives, and how modularity is achieved across the Nextflow workflow, Python step logic, and low-level operations.

---

## 3.1 High-Level Design

brainana is built around **Nextflow** as the central orchestrator. The pipeline is designed for:

- **Per-step parallelization**: Each processing step (reorient, bias correction, skull stripping, registration, etc.) is a separate Nextflow process. Subjects, sessions, and runs can be processed in parallel where dependencies allow.
- **Resumability**: Nextflow tracks process outputs and can resume from the last successful step after a failure, avoiding full re-runs.
- **Resource control**: CPU, GPU, and memory can be specified per process (e.g. GPU for skull stripping and segmentation, CPU for registration and preprocessing).

The workflow is **two-phase**: 

- anatomical processing runs first 
- functional (and T2w) processing depends on anatomical outputs (e.g. synthesized or single-run T1w, masks, transforms). This ordering is enforced by Nextflow channel dependencies and by the BIDS discovery step, which produces job descriptors that encode these dependencies.

---

## 3.2 Data Flow

End-to-end data flow can be summarized as follows:

1. **BIDS input**: A BIDS-formatted dataset (or NHP-BIDS extension) containing anatomical and/or functional MRI data.
2. **Discovery**: A Python discovery script (`discover_bids_for_nextflow.py`) runs *before* Nextflow. It scans the dataset and produces **job JSON files** that describe what to process (e.g. subject/session/run, file paths, whether anatomical synthesis is needed). Discovery uses BIDS metadata and config (e.g. `synthesis_type`, `synthesis_level`) to decide synthesis per anatomical job.
3. **Anatomical branch**:  
   - If **anatomical synthesis** is needed (multiple T1w or T2w runs/sessions), the synthesis process runs first: one file is chosen as reference, others are coregistered to it (ANTs rigid), then all coregistered images are averaged. The result is a single anatomical image per (sub, ses) or per subject, with BIDS naming that drops `run` (and optionally `ses` for subject-level synthesis).  
   - The resulting (or single) anatomical file then enters the normal anatomical pipeline: reorient → conform → bias correction → skull stripping (UNet) → registration to template (ANTs). Optional steps include FastSurfer-style segmentation and surface reconstruction.
4. **Functional branch**: Functional jobs are created from discovery. Each job gets the appropriate anatomical reference (synthesized or single-run T1w, depending on session/subject and config). Functional steps run in order: reorient and temporal mean → slice timing correction → motion correction → despiking → bias correction (on mean) → conform → skull stripping on mean → registration of mean to target → apply transforms to full 4D BOLD.
5. **Quality control**: QC processes consume outputs from preprocessing and registration (e.g. motion params, brain masks, aligned images) and generate snapshots and reports (e.g. motion, skull stripping, registration, bias correction).
6. **Output**: All outputs are written in **BIDS derivatives** layout (e.g. preprocessed images, masks, transforms, segmentations, QC reports), preserving BIDS entity structure where applicable.

This flow is documented in the repository in `docs/ANAT_SYNTHESIS_FLOW.md` (synthesis decision tree and usage by T2w/functional) and in `docs/CORE_COMPONENTS.md` (data flow architecture).

---

## 3.3 Modularity: Pipeline, Steps, and Operations

Modularity is achieved by separating three layers:

### 3.3.1 Nextflow pipeline layer

- **Location**: `main.nf`, `modules/anatomical.nf`, `modules/functional.nf`, `modules/qc.nf`, and supporting workflow files under `workflows/`.
- **Role**: Define processes, channels, and dependencies. Each process typically invokes a Python step script with a well-defined set of inputs (paths, config). The pipeline does not implement algorithms; it orchestrates when and where each step runs and how outputs are passed to the next steps.
- **Responsibilities**: Parallel execution, resumption, resource allocation (e.g. `cpus`, `memory`, `gpu`), and grouping of inputs (e.g. by subject/session) for anatomical vs functional workflows.

### 3.3.2 Step functions (Python)

- **Location**: `src/nhp_mri_prep/steps/` (e.g. `bids_discovery.py`, `anatomical.py`, `functional.py`, `qc.py`, `types.py`).
- **Role**: Implement the *logic* of each processing step: what to run, in what order, and what to validate. Step functions call into operations and utilities; they do not call external tools directly (that is done in the operations layer).
- **Responsibilities**: Input/output validation, sequencing of operations within a step (e.g. “bias correct then skull strip”), handling of optional behaviors (e.g. two-pass refinement in skull stripping), and producing outputs that conform to BIDS derivatives naming and layout.

### 3.3.3 Processing operations (Python)

- **Location**: `src/nhp_mri_prep/operations/` (e.g. `preprocessing.py`, `registration.py`, `synthesis_multiple_anat.py`, `validation.py`) and `src/nhp_mri_prep/operations/skullstripping/`.
- **Role**: Provide the actual implementation of algorithms and tool calls. They interface with **external tools** (AFNI, ANTs, FSL) and with **internal models** (e.g. UNet skull stripping, FastSurfer-style segmentation in `fastsurfer_nn`).
- **Responsibilities**: Building and running command lines (e.g. ANTs, AFNI), reading/writing neuroimaging files (via nibabel etc.), running PyTorch models, and performing low-level validation (e.g. file existence, working directory).

This three-layer split keeps the pipeline readable and testable: workflow structure lives in Nextflow; step logic and BIDS handling in Python steps; and algorithm/tool details in operations. The same operations can be reused across steps (e.g. registration used in both anatomical and functional pipelines) and tested independently.

---

## 3.4 Discovery and Job Creation

Discovery runs **before** the Nextflow pipeline. It:

- Scans the BIDS dataset and respects BIDS (and NHP-BIDS) layout and metadata.
- Determines which anatomical jobs need synthesis (`needs_synth`) and which synthesis type/level (T1w vs T2w, session vs subject) from configuration.
- Produces structured job descriptors (e.g. JSON) that Nextflow reads to create channels. Thus, Nextflow does not re-scan the file system for BIDS layout; it consumes a precomputed job list.

This design keeps BIDS logic in one place (Python + BIDS libraries) and lets Nextflow focus on scheduling and execution. Cross-session and cross-run dependencies (e.g. “this functional run uses that synthesized T1w”) are encoded in the job descriptors so that the pipeline can order and group processes correctly.

---

## 3.5 Key Design Principles

- **Modularity**: Each component has a single, well-defined responsibility (orchestration vs step logic vs algorithm/tool execution).
- **Dependency safety**: Two-phase processing (anatomical then functional) and synthesis rules ensure that functional and T2w workflows always see the correct anatomical reference.
- **BIDS compliance**: Inputs and outputs follow BIDS (and derivatives) structure; discovery and step outputs use BIDS entity naming (e.g. dropping `run`/`ses` when appropriate).
- **Error handling and recovery**: Validation at step and operation level; Nextflow resumption to avoid re-running successful steps.
- **Quality control**: QC is integrated as first-class processes that consume pipeline outputs and produce standardized reports.
- **Configuration**: A single configuration system (YAML defaults, Nextflow params, environment) drives discovery, synthesis level, template choice, and step options, so that runs are reproducible and comparable.

Together, this design supports reproducible, BIDS-native preprocessing of macaque MRI with maximum parallelization and clear separation between workflow structure, step logic, and low-level methods—the details of which are described in the next section (Core Components and Methods).
