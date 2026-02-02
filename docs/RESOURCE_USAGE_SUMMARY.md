# Resource Usage Summary by Process Type

This document summarizes the actual resource usage observed from Nextflow trace files, providing guidance for parallelism tuning and resource allocation.

## Data Source

Resource measurements collected from test dataset run (`dataset_multiple_v5`) with 4 subjects including infant data. Values represent observed ranges across subjects with varying data complexity.

---

## Anatomical Workflow (ANAT_WF)

### Heavy Processes (Recommend Limited Parallelism)

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **ANAT_SKULLSTRIPPING** | 15m - 1h33m | 121-250% | 2.0-6.1 GB | 18.8-28.4 GB | Multi-threaded, memory intensive |
| **ANAT_SURFACE_RECONSTRUCTION** | 1h33m - 3h52m | 14-26% | 2.1-10 GB | 7.5-15.2 GB | Long-running, high memory for infants |
| **ANAT_REGISTRATION** | 1h44m - 2h17m | 101-110% | 2.6-4.6 GB | 8.3-10.3 GB | ANTs registration, CPU intensive |

### Medium Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **ANAT_SYNTHESIS** | 4m - 32m | 91-158% | 1.7-5.2 GB | 7.5-11.4 GB | GPU process (fastsurfer_nn) |
| **ANAT_BIAS_CORRECTION** | 1m - 13m | 83-110% | 1.8-7.3 GB | 7.5-13.1 GB | N4 bias field correction |
| **ANAT_CONFORM** | 4m - 11m | 15-57% | 2.1-5.5 GB | 18.4-21.8 GB | FLIRT registration, low CPU |

### Light Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **ANAT_REORIENT** | 11s - 1m | 23-106% | 1.0-1.5 GB | 6.1-6.6 GB | Quick reorientation |
| **ANAT_APPLY_CONFORM** | 27s | 22% | 1.1 GB | 7.1 GB | Apply transform |
| **ANAT_APPLY_TRANSFORMATION** | 40s | 31% | 1.2 GB | 7.0 GB | Apply ANTs transform |
| **ANAT_APPLY_TRANSFORM_MASK** | 15-32s | 16-33% | 0.9-1.4 GB | 6.0-6.5 GB | Mask transformation |
| **ANAT_PUBLISH_PHASE1** | 23-40s | 12-20% | 0.9-1.0 GB | 6.0 GB | File publishing |

### QC Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM |
|---------|----------|-------|----------|-----------|
| **QC_CONFORM** | 7-27s | 19-94% | 1.1-1.9 GB | 6.1-7.0 GB |
| **QC_SKULLSTRIPPING** | 20-26s | 26-27% | 1.1-1.9 GB | 6.1-7.0 GB |
| **QC_ATLAS_SEGMENTATION** | 22-29s | 26-28% | 1.2-2.4 GB | 6.4-7.5 GB |
| **QC_BIAS_CORRECTION** | 27-56s | 12-20% | 1.0-1.6 GB | 6.1-6.7 GB |
| **QC_SURF_RECON_TISSUE_SEG** | 36s - 1m14s | 15-39% | 2.0-2.6 GB | 12.3-12.9 GB |
| **QC_CORTICAL_SURF_AND_MEASURES** | 18-46s | 13-32% | 1.3 GB | 6.4-6.5 GB |
| **QC_REGISTRATION** | 17-36s | 16-32% | 1.0 GB | 6.1 GB |
| **QC_T2W_TO_T1W_REGISTRATION** | 12s | 45% | 1.1 GB | 6.1 GB |
| **QC_T2W_TEMPLATE_SPACE** | 27s | 20% | 1.0 GB | 6.1 GB |

---

## Functional Workflow (FUNC_WF)

### Heavy Processes (Recommend Limited Parallelism)

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **FUNC_COMPUTE_REGISTRATION** | 4m - 3h53m | 61-300% | 1.0-9.6 GB | 6.7-15.4 GB | ANTs registration, highly variable |
| **FUNC_APPLY_TRANSFORMS** | 44s - 6m12s | 27-245% | 1.1-15.2 GB | 6.8-21 GB | Memory scales with volume size |
| **FUNC_COMPUTE_CONFORM** | 5m - 1h51m | 13-18% | 1.8-4.4 GB | 17.2-20.6 GB | FLIRT-based conforming |

### Medium Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **FUNC_APPLY_CONFORM** | 39s - 9m15s | 12-16% | 1.0-7.1 GB | 7.0-13.2 GB | Apply conform transform |
| **FUNC_COMPUTE_BRAIN_MASK** | 46s - 1m4s | 13-23% | 1.8-3.4 GB | 17.2-19.7 GB | Brain extraction |
| **FUNC_BIAS_CORRECTION** | 57s - 3m13s | 23-80% | 0.9-1.1 GB | 6.7-6.8 GB | N4 correction |

### Light Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM | Notes |
|---------|----------|-------|----------|-----------|-------|
| **FUNC_SLICE_TIMING** | 21-22s | 21-22% | 940-955 MB | 6.0 GB | Quick preprocessing |
| **FUNC_REORIENT** | 35s - 1m41s | 14-16% | 940 MB - 1.4 GB | 6.0-7.4 GB | Reorientation |
| **FUNC_MOTION_CORRECTION** | 45s - 2m | 13-15% | 950 MB - 1.5 GB | 6.0-7.6 GB | FSL mcflirt |
| **FUNC_WITHIN_SES_COREG** | 45s - 1m18s | 18-20% | 0.9-1.1 GB | 7.0-7.1 GB | Within-session coregistration |
| **FUNC_AVERAGE_TMEAN** | 30-33s | 15-16% | 937-965 MB | 6.0 GB | Temporal mean |
| **FUNC_APPLY_TRANSFORMS_MASK** | 32-50s | 15-19% | 0.9-1.6 GB | 6.0-7.2 GB | Mask application |

### QC Processes

| Process | Duration | CPU % | Peak RAM | Peak VMEM |
|---------|----------|-------|----------|-----------|
| **QC_MOTION_CORRECTION** | 33-43s | 12-15% | 968-990 MB | 6.1 GB |
| **QC_WITHIN_SES_COREG** | 44-46s | 12% | 979-982 MB | 6.1 GB |
| **QC_CONFORM_FUNC** | 35s - 1m12s | 10-14% | 959 MB - 1.6 GB | 6.1-6.7 GB |
| **QC_SKULLSTRIPPING_FUNC** | 38s - 1m13s | 10-14% | 979 MB - 1.6 GB | 6.1-6.7 GB |
| **QC_REGISTRATION_FUNC_INTERMEDIATE** | 6-21s | 24-99% | 0.9-1.2 GB | 6.1-6.3 GB |
| **QC_REGISTRATION_FUNC** | 8-21s | 24-100% | 0.9-2.3 GB | 6.1-7.4 GB |

---

## Report Generation

| Process | Duration | CPU % | Peak RAM | Peak VMEM |
|---------|----------|-------|----------|-----------|
| **QC_GENERATE_REPORT** | 6-7s | 67% | 953-966 MB | 6.0 GB |

---

## Implemented Resource Configuration

Resource allocation is centralized in `nextflow.config` using `withName:` selectors. This follows the DeepPrep pattern of declaring resources per process with a global resource cap.

### Global Resource Cap (Local Executor)

```groovy
profiles {
    local {
        executor.cpus = 8         // Total CPUs available for scheduling
        executor.memory = '16 GB' // Total memory available for scheduling
    }
}
```

Nextflow schedules tasks based on declared `cpus`/`memory` and only starts new tasks when there's room within these limits.

### Process Resource Declarations

```groovy
process {
    // Default for light processes
    cpus = 1
    memory = '2 GB'
    
    // HEAVY PROCESSES - Strict limits with retry strategy
    withName: 'ANAT_SURFACE_RECONSTRUCTION' {
        cpus = 1
        memory = { 10.GB * (task.attempt ** 1.5) }
        errorStrategy = { task.exitStatus in 137..140 ? 'retry' : 'terminate' }
        maxRetries = 2
        maxForks = 1  // Peak 10 GB - only 1 at a time on 16 GB system
    }
    
    withName: 'FUNC_APPLY_TRANSFORMS' {
        cpus = 2
        memory = { 16.GB * (task.attempt ** 1.5) }
        errorStrategy = { task.exitStatus in 137..140 ? 'retry' : 'terminate' }
        maxRetries = 2
        maxForks = 1  // Peak 15.2 GB - must run alone
    }
    
    withName: 'ANAT_SKULLSTRIPPING' {
        cpus = 2
        memory = { 7.GB * (task.attempt ** 1.5) }
        maxForks = 2
    }
    
    withName: 'ANAT_REGISTRATION' {
        cpus = 2
        memory = { 5.GB * (task.attempt ** 1.5) }
        maxForks = 2
    }
    
    withName: 'FUNC_COMPUTE_REGISTRATION' {
        cpus = 3
        memory = { 10.GB * (task.attempt ** 1.5) }
        maxForks = 2
    }
    
    // MEDIUM PROCESSES
    withName: 'ANAT_CONFORM' { cpus = 1; memory = '6 GB' }
    withName: 'ANAT_BIAS_CORRECTION' { cpus = 1; memory = '8 GB' }
    withName: 'ANAT_SYNTHESIS' { cpus = 1; memory = '6 GB' }
    withName: 'FUNC_COMPUTE_CONFORM' { cpus = 1; memory = '5 GB' }
    withName: 'FUNC_APPLY_CONFORM' { cpus = 1; memory = '8 GB' }
    withName: 'FUNC_COMPUTE_BRAIN_MASK' { cpus = 1; memory = '4 GB' }
    withName: 'FUNC_BIAS_CORRECTION' { cpus = 1; memory = '2 GB' }
    
    // GPU processes - limited by VRAM
    withLabel: 'gpu' {
        maxForks = gpuCount > 0 ? gpuCount * maxJobsPerGpu : 1
    }
    
    // LIGHT PROCESSES - use defaults (1 CPU, 2 GB)
}
```

### Scheduling Example (8 CPU / 16 GB System)

```
Scenario: ANAT_SURFACE_RECONSTRUCTION running
  Running: 1 CPU, 10 GB → Remaining: 7 CPUs, 6 GB
  ANAT_CONFORM (1 CPU, 6 GB) → Fits! Starts
  ANAT_SKULLSTRIPPING (2 CPU, 7 GB) → Memory insufficient, queued

Scenario: Multiple light processes
  8x QC processes (1 CPU, 2 GB each) → Only 8 fit by memory (16 GB used)
  9th process waits
```

### Retry Strategy

Heavy processes use dynamic memory scaling on retry:
- Exit codes 137-140 indicate OOM kill
- Memory increases by 1.5x per retry: 10 GB → 15 GB → 22.5 GB
- Max 2 retries before terminating

---

## Notes

1. **Infant data** (e.g., `baby31`) consistently shows higher resource usage due to larger volume sizes and more complex processing.

2. **Virtual memory (VMEM)** values are much higher than peak RSS due to memory mapping; actual physical memory usage is reflected in `peak_rss`.

3. **CPU percentages over 100%** indicate multi-threaded execution (e.g., 250% = using ~2.5 cores on average).

4. **Duration variability** is primarily due to:
   - Subject data quality and size
   - Age-related complexity (infants vs adults)
   - Whether results are cached

5. **FLIRT-based processes** (`ANAT_CONFORM`, `FUNC_COMPUTE_CONFORM`) use ~70 MB per FLIRT instance but high virtual memory due to FSL memory mapping patterns.
