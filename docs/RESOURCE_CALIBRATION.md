# brainana Resource Calibration

Resource requirements calibrated from actual Nextflow trace data from two datasets, plus comparison with fMRIPrep and DeepPrep. Used to set `nextflow.config` process resources and Docker documentation.

---

## 1. Reference Benchmarks

### fMRIPrep
- **Minimal**: 16 GB RAM, 4+ CPUs
- **Recommended**: 32 GB+ for recon-all

### DeepPrep
- **RAM + Swap**: ≥ 12 GB
- **Disk**: ≥ 20 GB
- **CPUs**: ≥ 4 logical cores
- **GPU (optional)**: ≥ 10 GB VRAM, NVIDIA driver ≥ 520.61.05, CUDA ≥ 11.8

### brainana (calibrated)
- **Minimal** (anat-only, single subject, no surface): 12 GB RAM, 4 CPUs
- **Recommended** (full anat+func, multiple subjects): 20 GB RAM, 8 CPUs
- **Surface reconstruction**: +2–8 GB per subject (ANAT_SURFACE_RECONSTRUCTION)
- **Heavy functional** (FUNC_APPLY_TRANSFORMS): up to 15 GB peak per task

---

## 2. Trace Data Summary

### Dataset 1: PRIME-DE site-newcastle
- **Type**: Full anat+func, 10 subjects, multiple sessions, resting fMRI
- **Pipeline**: Anatomical + functional + QC + surface reconstruction

### Dataset 2: ElectrodeLocalization bids_preproc
- **Type**: Anatomical only, 9 subjects, single session
- **Pipeline**: Anatomical + surface reconstruction, no functional

### Peak memory (peak_rss) by process

| Process | Dataset 1 peak_rss | Dataset 2 peak_rss | Notes |
|---------|--------------------|--------------------|-------|
| ANAT_CONFORM | 2.1 GB | 2.1–6.7 GB | Large for big volumes (e.g. red: 6.7 GB) |
| ANAT_SKULLSTRIPPING | 1.9–2 GB | 2–2.2 GB | GPU process, ~15–20 min/subject |
| ANAT_SURFACE_RECONSTRUCTION | 1.9–2 GB | 2.1–2.3 GB | 13–23 min/subject |
| ANAT_REGISTRATION | 2.5–2.6 GB | 2.6 GB | 1–1.5 h/subject |
| ANAT_BIAS_CORRECTION | 1.2–1.5 GB | 1.3–1.8 GB | |
| FUNC_APPLY_TRANSFORMS | 6.9 GB | N/A | Highest func process |
| FUNC_COMPUTE_CONFORM | 2 GB | N/A | peak_vmem 16.7 GB |
| FUNC_APPLY_CONFORM | 3.2 GB | N/A | |
| FUNC_COMPUTE_BRAIN_MASK | 1.9–2 GB | N/A | peak_vmem 12.6 GB |
| FUNC_COMPUTE_REGISTRATION | 1.3–1.4 GB | N/A | |
| QC_SURF_RECON_TISSUE_SEG | 2 GB | 1.9–2 GB | peak_vmem 10–11.5 GB |
| QC_CORTICAL_SURF_AND_MEASURES | 1.3 GB | 1.4–1.5 GB | peak_vmem up to 60 GB (wb_command) |

### Peak virtual memory (peak_vmem)

Several processes have much higher peak_vmem than peak_rss due to mapped libraries and FSL/FreeSurfer patterns:

- ANAT_CONFORM: up to 20 GB vmem
- FUNC_COMPUTE_CONFORM: 16.7 GB vmem
- FUNC_COMPUTE_BRAIN_MASK: 12.6 GB vmem
- QC_SURF_RECON_TISSUE_SEG: 11.5 GB vmem
- QC_CORTICAL_SURF_AND_MEASURES: up to 60 GB vmem (Connectome Workbench)

Physical RAM is better reflected by peak_rss; vmem is mainly for reference.

---

## 3. Recommended Resource Allocation

### Per-process (nextflow.config)

| Process | cpus | memory | maxForks | Rationale |
|---------|------|--------|----------|-----------|
| ANAT_SURFACE_RECONSTRUCTION | 1 | 8 GB (×attempt^1.5) | 1 | Peak ~7 GB, add headroom |
| FUNC_APPLY_TRANSFORMS | 2 | 12 GB (×attempt^1.5) | 1 | Peak ~7 GB, scales with vol size |
| ANAT_SKULLSTRIPPING | 2 | 6 GB (×attempt^1.5) | 2 | Peak ~2.2 GB |
| ANAT_REGISTRATION | 2 | 5 GB (×attempt^1.5) | 2 | Peak ~2.6 GB |
| FUNC_COMPUTE_REGISTRATION | 3 | 8 GB (×attempt^1.5) | 2 | Peak ~1.4 GB, CPU-heavy |
| ANAT_CONFORM | 1 | 8 GB | - | Peak 6.7 GB in ElectrodeLocalization |
| ANAT_BIAS_CORRECTION | 1 | 8 GB | - | Peak ~1.8 GB |
| ANAT_SYNTHESIS | 1 | 6 GB | - | GPU process |
| FUNC_COMPUTE_CONFORM | 1 | 6 GB | - | peak_vmem 16.7 GB |
| FUNC_APPLY_CONFORM | 1 | 8 GB | - | Peak 3.2 GB |
| FUNC_COMPUTE_BRAIN_MASK | 1 | 4 GB | - | GPU process |
| FUNC_BIAS_CORRECTION | 1 | 2 GB | - | |
| ANAT_T2W_TO_T1W_REGISTRATION | 1 | 6 GB | - | |
| Default (light/QC) | 1 | 2 GB | - | |

### Global executor (scheduling pool)

| Profile | cpus | memory | Use case |
|---------|------|--------|----------|
| **minimal** | 4 | 16 GB | Anat-only, 1–2 subjects |
| **default** | 8 | 20 GB | Typical local/Docker runs |
| **recommended** | 8 | 32 GB | Full pipeline, multiple subjects |
| **high** | 16 | 64 GB | Large batches, HPC |

---

## 4. brainana System Requirements

| Tier | RAM | CPUs | Disk | GPU |
|------|-----|------|------|-----|
| **Minimal** | 12 GB | 4 | 20 GB | Optional (skullstrip slower on CPU) |
| **Recommended** | 20 GB | 8 | 50 GB | 1× with ≥6 GB VRAM |
| **Production** | 32 GB | 8+ | 100 GB+ | 1× with ≥10 GB VRAM |

---

## 5. Implementation Plan

### 5.1 nextflow.config

1. **Params for executor pool**
   - Add `--max_cpus` and `--max_memory` (or use env vars)
   - Default: 8 CPUs, 20 GB

2. **Profiles**
   - `minimal`: executor 4 cpus, 16 GB
   - `default`: executor 8 cpus, 20 GB
   - `recommended`: executor 8 cpus, 32 GB

3. **Process updates**
   - ANAT_CONFORM: 6 GB → 8 GB (ElectrodeLocalization outlier)
   - FUNC_APPLY_TRANSFORMS: keep 12 GB (observed 6.9 GB)
   - QC_CORTICAL_SURF_AND_MEASURES: 2 GB → 4 GB (wb_command spikes)
   - Others: keep current or adjust from table above

### 5.2 Docker

1. **Document resource flags**
   ```bash
   # Minimal
   docker run --memory 16g --cpus 4 ...

   # Recommended
   docker run --memory 20g --cpus 8 --gpus all ...
   ```

2. **README_Docker.md**
   - Add a "System requirements" section
   - Add examples with `--memory` and `--cpus`

3. **Executor alignment**
   - If user passes `--memory 20g`, Nextflow should see executor.memory ≤ 20 GB
   - Option: read from env (e.g. `NXF_MAX_MEMORY`, `NXF_MAX_CPUS`)

### 5.3 Env-driven executor (optional)

```groovy
def maxCpus = System.getenv('NXF_MAX_CPUS') ?: '8'
def maxMemory = System.getenv('NXF_MAX_MEMORY') ?: '20 GB'

executor {
    cpus = maxCpus as int
    memory = maxMemory
}
```

Allows Docker to set `-e NXF_MAX_MEMORY=20g -e NXF_MAX_CPUS=8` so Nextflow matches container limits.

---

## 7. Implementation Checklist

- [x] nextflow.config: Add NXF_MAX_CPUS / NXF_MAX_MEMORY support
- [x] nextflow.config: Add profiles (minimal, recommended)
- [x] nextflow.config: Bump ANAT_CONFORM to 8 GB
- [x] nextflow.config: Add QC_SURF_RECON_TISSUE_SEG and QC_CORTICAL_SURF_AND_MEASURES (4 GB)
- [x] README_Docker.md: Add System Requirements section
- [x] README_Docker.md: Add --memory / --cpus examples
- [x] Update RESOURCE_USAGE_SUMMARY.md to reference this doc

---

## 8. Data Sources

| Dataset | Path | Type |
|---------|------|------|
| PRIME-DE site-newcastle | `/mnt/DataDrive2/macaque/data_preproc/macaque_mri/PRIME-DE_brainana/site-newcastle/nextflow_reports` | Full anat+func |
| ElectrodeLocalization | `/mnt/DataDrive2/macaque/data_raw/macaque_mri/ElectrodeLocalization/bids_preproc/nextflow_reports` | Anat-only |

Trace columns used: `peak_rss` (actual RAM), `peak_vmem` (virtual), `%cpu`, `realtime` (duration).
