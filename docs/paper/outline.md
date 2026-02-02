# Paper Outline: Introducing banana (Macaque Neuroimaging Preprocessing)

## 1. Abstract

- One-paragraph summary: BIDS-based, Nextflow-orchestrated preprocessing pipeline for macaque MRI (anatomical + functional).
- Key points: anatomical synthesis for multi-run data, UNet skull stripping, bias correction, ANTs registration, optional FastSurfer-style segmentation and surface reconstruction, NMT2Sym template support, integrated QC.

---

## 2. Introduction / Background

- **Motivation**: Need for reproducible, standardized preprocessing of non-human primate (NHP) MRI; limitations of human-focused tools (e.g. fMRIPrep) for macaque data.
- **BIDS and NHP**: BIDS extension for NHP; role of BIDS in discovery and derivatives.
- **Scope**: banana as a dedicated macaque preprocessing pipeline (anatomical → functional, with optional surface analysis).

---

## 3. Design and Architecture

- **High-level design**: Nextflow as orchestrator; per-step parallelization; resumability and resource control.
- **Data flow**: BIDS input → discovery → anatomical branch (with synthesis when needed) → functional branch → derivatives + QC.
- **Modularity**: Separation of pipeline (Nextflow), step logic (Python), and low-level operations (calls to AFNI, ANTs, FSL, PyTorch).

*→ Expanded in [03-design-and-architecture.md](03-design-and-architecture.md).*

---

## 4. Core Components (and Methods)

- **4.1** BIDS discovery and job creation  
- **4.2** Anatomical processing (synthesis, reorient, conform, bias correction, skull stripping, registration)  
- **4.3** Functional processing (slice timing, motion correction, despiking, bias correction, skull stripping, registration)  
- **4.4** Skull stripping and segmentation (UNet, FastSurfer-style; algorithms)  
- **4.5** Surface reconstruction (optional)  
- **4.6** Quality control  
- **Methods**: Anatomical synthesis algorithm; skull stripping (UNet); registration (ANTs); bias correction.

*→ Expanded (with methods incorporated) in [04-core-components-and-methods.md](04-core-components-and-methods.md).*

---

## 6. Implementation

- **Stack**: Python 3.11+, Nextflow; AFNI, ANTs, FSL; PyTorch (UNet, FastSurfer-style); nibabel, pybids, etc.
- **Configuration**: YAML config, defaults, path/template validation; Nextflow parameters and config profiles.
- **Execution**: Nextflow workflow (main.nf, modules for anatomical, functional, QC); Docker support for reproducibility.
- **Resource usage**: Approximate CPU/GPU/memory for heavy steps (anatomical synthesis, skull stripping, surface reconstruction).

---

## 7. Usage and Workflow

- **Input**: BIDS dataset (anatomical and/or functional).
- **Output**: BIDS derivatives (preprocessed images, masks, transforms, segmentations/surfaces if enabled); QC reports.
- **Example**: Single command or minimal config (e.g. `run_nextflow.sh`); optional parameters (templates, surface/segmentation on/off).
- **Reproducibility**: Docker image, lock file (uv.lock), config defaults.

---

## 8. Validation and Quality Control

- Types of QC (motion, skull stripping, registration, bias).
- How reports are generated and where they appear in the derivatives.
- Any validation of pipeline outputs (e.g. against manual masks or other software) if available.

---

## 9. Availability and Reproducibility

- **Software**: GitHub URL, license (MIT), Python package (install from repo).
- **Containers**: Docker image and how to run it.
- **Documentation**: README, Nextflow docs, Docker docs; reference to `docs/` (e.g. ANAT_SYNTHESIS_FLOW, PROJECT_STRUCTURE, CORE_COMPONENTS).
- **Templates**: NMT2Sym template zoo (included or documented download).

---

## 10. Discussion

- **Strengths**: BIDS-native, NHP-focused, modular, optional surface/segmentation, QC integration.
- **Limitations**: Macaque-focused; dependency on external tools and GPU for some steps; computational cost of surface reconstruction.
- **Future work**: Additional templates, more NHP species, validation studies, integration with other NHP BIDS tools.

---

## 11. Conclusion

- Short recap: banana as a dedicated, BIDS-based, Nextflow-driven pipeline for macaque MRI preprocessing (and optional segmentation/surface reconstruction), with QC and reproducibility in mind.
- Intended users (NHP imaging labs, method developers) and invitation to use/contribute.

---

## Suggested Figures/Tables

- **Figure 1**: High-level pipeline flowchart (anatomical + functional + QC), e.g. from ANAT_SYNTHESIS_FLOW and main.nf.
- **Figure 2**: Component diagram (e.g. from macacaMRIprep_component_diagram.puml), simplified for the paper.
- **Figure 3**: Example QC outputs (motion, skull stripping, registration).
- **Table 1**: Pipeline steps (anatomical vs functional) with main tool per step.
- **Table 2**: Software/dependency versions and execution environment (optional).
