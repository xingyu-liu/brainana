# Anatomical Synthesis Flowchart

## Overview

Anatomical synthesis combines multiple anatomical runs (T1w or T2w) into a single image through coregistration and averaging. This document describes all possible cases and how the synthesized output is used by T2w and functional workflows.

## Synthesis Decision Tree

```
┌─────────────────────────────────────────────────────────────────┐
│                    INPUT: Anatomical Files                       │
│              (from BIDS discovery: anat_jobs.json)               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  Check:         │
                    │  needs_synth?   │
                    └────────┬───────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
        ┌───────────────┐        ┌───────────────┐
        │  YES          │        │  NO            │
        │  (needs_synth │        │  (Single file) │
        │   = true)     │        │                │
        └───────┬───────┘        └───────┬───────┘
                │                         │
                ▼                         │
        ┌────────────────┐                │
        │  Check:        │                │
        │  synthesis_type│                │
        └────────┬───────┘                │
                 │                        │
        ┌────────┴────────┐              │
        │                  │              │
        ▼                  ▼              │
┌──────────────┐  ┌──────────────┐      │
│ "t1w"        │  │ "t2w"        │      │
│ (T1w synth)  │  │ (T2w synth)  │      │
└──────┬───────┘  └──────┬───────┘      │
       │                 │               │
       │                 │               │
       └────────┬────────┘               │
                │                        │
                ▼                        ▼
        ┌──────────────────────────────────────┐
        │     ANAT_SYNTHESIS Process           │
        │                                      │
        │  Input: [sub, ses, file_objects]     │
        │  - file_objects: List of files      │
        │    (multiple runs or sessions)       │
        └──────────────┬───────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │  Check: len(anat_files) <= 1?        │
        └──────────────┬───────────────────────┘
                       │
            ┌───────────┴───────────┐
            │                       │
            ▼                       ▼
    ┌──────────────┐      ┌──────────────────┐
    │  YES         │      │  NO               │
    │  (Single     │      │  (Multiple files) │
    │   file)      │      │                   │
    └──────┬───────┘      └──────────┬────────┘
           │                         │
           │                         ▼
           │              ┌──────────────────────┐
           │              │  SYNTHESIS PROCESS   │
           │              │                      │
           │              │  1. Select first     │
           │              │     file as reference│
           │              │                      │
           │              │  2. For each other   │
           │              │     file:            │
           │              │     - Coregister to  │
           │              │       reference      │
           │              │       (ANTs rigid)   │
           │              │     - Store result    │
           │              │                      │
           │              │  3. Average all      │
           │              │     coregistered     │
           │              │     images          │
           │              │                      │
           │              │  4. Generate output: │
           │              │     - Remove 'run'   │
           │              │       entity         │
           │              │     - Remove 'ses'    │
           │              │       if subject-    │
           │              │       level          │
           │              └──────────┬───────────┘
           │                         │
           └─────────────┬───────────┘
                         │
                         ▼
        ┌──────────────────────────────────────┐
        │  Output: [sub, ses, anat_file,       │
        │           bids_name.txt]            │
        │                                      │
        │  - anat_file: Synthesized or single │
        │  - bids_name.txt: BIDS naming       │
        │    template (without 'run',          │
        │    without 'ses' if subject-level)   │
        └──────────────┬───────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │  Continue to Normal Anatomical       │
        │  Processing Pipeline:                │
        │  - Reorient                          │
        │  - Conform                           │
        │  - Bias Correction                   │
        │  - Skull Stripping                   │
        │  - Registration                      │
        └──────────────────────────────────────┘
```

## Synthesis Levels

### Case 1: Session-Level Synthesis
**Configuration**: `anat.synthesis_level = "session"` (default: "subject")

**Input**: Multiple runs within the same session
- Example: `sub-001_ses-001_run-01_T1w.nii.gz`, `sub-001_ses-001_run-02_T1w.nii.gz`

**Process**:
1. Coregister all runs to first run (reference)
2. Average coregistered images
3. Output filename: `sub-001_ses-001_T1w.nii.gz` (run entity removed, ses kept)

**Output Structure**: `[sub, ses, anat_file, bids_name]`
- `ses`: Session ID (e.g., "001")
- `bids_name`: `sub-001/ses-001/anat/sub-001_ses-001_T1w.nii.gz`

### Case 2: Subject-Level Synthesis
**Configuration**: `anat.synthesis_level = "subject"`

**Input**: Multiple sessions (or runs across sessions) for the same subject
- Example: `sub-001_ses-001_T1w.nii.gz`, `sub-001_ses-002_T1w.nii.gz`

**Process**:
1. Collect all anatomical files across all sessions
2. Coregister all to first file (reference)
3. Average coregistered images
4. Output filename: `sub-001_T1w.nii.gz` (both run and ses entities removed)

**Output Structure**: `[sub, "", anat_file, bids_name]`
- `ses`: Empty string `""` (or `null`)
- `bids_name`: `sub-001/anat/sub-001_T1w.nii.gz` (no ses directory)

### Case 3: Single File (No Synthesis)
**Input**: Single anatomical file (one run, one session)

**Process**:
1. Skip synthesis (passthrough)
2. Output: Original file (unchanged)

**Output Structure**: `[sub, ses, anat_file, bids_name]`
- `bids_name`: Original file path (includes run if present)

## Usage by T2w Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  T2w Processing Flow                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  T2w Synthesis │
                    │  (if needed)   │
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  T2w Reorient  │
                    └────────┬───────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  Anatomical Selection for T2w        │
        │  (performT2wAnatomicalSelection)     │
        │                                      │
        │  Priority:                            │
        │  1. Subject-level T1w (ses="")       │
        │     - HIGHEST PRIORITY               │
        │     - Cross-session synthesized      │
        │  2. Same-session T1w                  │
        │  3. Cross-session T1w                 │
        │  4. No T1w (stop processing)         │
        └──────────────┬───────────────────────┘
                       │
            ┌───────────┴───────────┐
            │                       │
            ▼                       ▼
    ┌──────────────┐      ┌──────────────┐
    │  T1w Found   │      │  No T1w      │
    │  (with_t1w)  │      │  (without_   │
    │              │      │   t1w)       │
    └──────┬───────┘      └──────┬───────┘
           │                     │
           ▼                     │
    ┌──────────────┐             │
    │  T2w→T1w     │             │
    │  Registration│             │
    │  (uses T1w   │             │
    │   from       │             │
    │   reorient   │             │
    │   stage)     │             │
    └──────┬───────┘             │
           │                     │
           ▼                     │
    ┌──────────────────────┐     │
    │  Apply T1w's         │     │
    │  Conform Transform   │     │
    │  (ANAT_APPLY_CONFORM)│     │
    └──────┬───────────────┘     │
           │                     │
           ▼                     │
    ┌──────────────────────┐     │
    │  Apply T1w's         │     │
    │  Registration        │     │
    │  Transform           │     │
    │  (ANAT_APPLY_        │     │
    │   TRANSFORMATION)    │     │
    └──────┬───────────────┘     │
           │                     │
           └──────────┬──────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Final T2w Output│
            │  (in template    │
            │   space)         │
            └──────────────────┘
```

**Key Points**:
- T2w uses T1w from **reorient stage** (before conform) for T2w→T1w registration
- T2w then applies T1w's conform and registration transforms sequentially
- T1w can be session-level or subject-level synthesized
- Subject-level T1w (ses="") is available to all T2w sessions

## Usage by Functional Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  Functional Processing Flow                                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  Func Pipeline │
                    │  (slice timing, │
                    │   reorient,     │
                    │   motion, etc.) │
                    └────────┬───────┘
                             │
                             ▼
        ┌──────────────────────────────────────┐
        │  Anatomical Selection for Func        │
        │  (performFuncAnatomicalSelection)     │
        │                                      │
        │  Priority:                            │
        │  1. Subject-level T1w (ses="")       │
        │     - HIGHEST PRIORITY               │
        │     - Cross-session synthesized      │
        │  2. Same-session T1w                  │
        │  3. Cross-session T1w                 │
        │  4. Dummy (no anatomical)            │
        └──────────────┬───────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │  Compute Phase (on tmean)            │
        │  - Conform to anatomical             │
        │  - Compute brain mask                │
        │  - Register to anatomical            │
        └──────────────┬───────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │  Apply Phase (to full BOLD 4D)        │
        │  - Apply conform transform           │
        │  - Apply registration transforms     │
        │    (func→anat + anat→template)       │
        └──────────────┬───────────────────────┘
                       │
                       ▼
            ┌──────────────────┐
            │  Final Func Output│
            │  (in template    │
            │   space)         │
            └──────────────────┘
```

**Key Points**:
- Functional uses T1w from **bias correction stage** (Phase 1 final output - brain version)
- Subject-level T1w (ses="") has **HIGHEST PRIORITY** for functional registration
- All runs in the same functional session use the same anatomical reference
- Functional registration uses two-step transform:
  1. func→anat (computed on tmean)
  2. anat→template (from anatomical workflow)

## Synthesis Metadata

The synthesis process generates metadata indicating:
- `synthesized`: Boolean (true if synthesis occurred, false if passthrough)
- `num_runs`: Number of input files
- BIDS filename: Modified to remove `run` entity (and `ses` for subject-level)

## Channel Structures

### After Synthesis
```groovy
// [sub, ses, anat_file, bids_name]
// ses: "" for subject-level, session ID for session-level
// bids_name: BIDS naming template (without run, without ses if subject-level)
```

### Used by T2w
```groovy
// T2w anatomical selection output:
// [sub, ses, t2w_file, t2w_bids_name, t1w_file, anat_ses]
// anat_ses: Session ID of T1w reference ("" for subject-level)
```

### Used by Functional
```groovy
// Functional anatomical selection output:
// [sub, ses, anat_file, anat_ses]
// anat_ses: Session ID of T1w reference ("" for subject-level, highest priority)
```

## Summary of All Cases

| Case | Input | Synthesis Level | Output ses | Output filename | Used By |
|------|-------|----------------|------------|-----------------|---------|
| 1 | Multiple runs, same session | Session | Session ID | `sub-XXX_ses-XXX_T1w.nii.gz` | T2w, Func |
| 2 | Multiple sessions | Subject | `""` | `sub-XXX_T1w.nii.gz` | T2w, Func (priority) |
| 3 | Single file | None | Session ID | Original (with run) | T2w, Func |

**Note**: Subject-level synthesis (Case 2) is preferred by functional workflow because it provides a single, high-quality anatomical reference across all sessions.
