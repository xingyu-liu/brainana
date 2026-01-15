# Channel Structure Reference Guide

This document provides a comprehensive reference for channel structures used throughout the Nextflow workflows. Understanding these structures is critical for modifying or extending the pipeline.

## Overview

Channels in Nextflow are used to pass data between processes. Each channel contains tuples with a specific structure. This document catalogs all channel structures at each stage of processing.

## Channel Structure Notation

Channels are documented using the format:
```groovy
// Channel structure: [element1, element2, element3, ...]
```

Where:
- `sub` = subject ID (string)
- `ses` = session ID (string or null)
- `run_id` or `run_identifier` = run identifier (string, may be empty for session-level)
- File paths are `path` types
- String values are `val` types

## Functional Workflow Channels

### Initial Channels

**Job Discovery Channel** (`func_jobs_ch`):
```groovy
// [sub, ses, run_identifier, file_obj, bids_naming_template]
```
- Created from JSON discovery file
- `run_identifier`: Extracted from BIDS filename (e.g., "task-rest_run-1")

### Processing Step Channels

**After Slice Timing/Reorient/Motion** (`func_after_motion`):
```groovy
// [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
```
- `bold_file`: 4D BOLD data
- `tmean_file`: Temporal mean (3D reference)

**After Despike** (`func_after_despike`):
```groovy
// [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
```
- Same structure as after motion correction

**After Coregistration** (`func_after_coreg`):
```groovy
// [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
```
- Coregistered within session if enabled
- Otherwise same as input

### Compute Phase Channels

#### Session-Level Compute Phase
**When**: `func_coreg_runs_within_session && func_coreg_success`

**Input** (`func_compute_input`):
```groovy
// [sub, ses, "", tmean, bids]  // run_id is empty for session-level
```

**After Bias Correction** (`func_after_bias`):
```groovy
// [sub, ses, "", bias_corrected_tmean, bids]
```

**After Conform** (`func_compute_conform_output`):
```groovy
// [sub, ses, "", conformed_tmean, bids]
```

**Conform Transforms** (`func_compute_conform_transforms`):
```groovy
// [sub, ses, "", forward_xfm, inverse_xfm]
```

**After Skull Stripping** (`func_compute_mask_output`):
```groovy
// [sub, ses, "", masked_tmean, bids, brain_mask]
```

**After Registration** (`func_compute_reg_output`):
```groovy
// [sub, ses, "", registered_tmean, bids, anat_ses, is_cross_ses]
```

#### Per-Run Compute Phase
**When**: Not using session-level coregistration

**Input** (`func_compute_input`):
```groovy
// [sub, ses, run_id, tmean, bids]
```

**After Bias Correction** (`func_after_bias`):
```groovy
// [sub, ses, run_id, bias_corrected_tmean, bids]
```

**After Conform** (`func_compute_conform_output`):
```groovy
// [sub, ses, run_id, conformed_tmean, bids]
```

**Conform Transforms** (`func_compute_conform_transforms`):
```groovy
// [sub, ses, run_id, forward_xfm, inverse_xfm]
```

**After Skull Stripping** (`func_compute_mask_output`):
```groovy
// [sub, ses, run_id, masked_tmean, bids, brain_mask]
```

**After Registration** (`func_compute_reg_output`):
```groovy
// [sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses]
```

### Apply Phase Channels

**Apply Conform Input** (`func_apply_conform_input`):
```groovy
// Session-level: [sub, ses, run_id, bold, func2target_xfm, conformed_tmean, bids]
// Per-run: [sub, ses, run_id, bold, func2target_xfm, conformed_tmean, bids]
```

**Apply Conform Output** (`func_apply_conform_output`):
```groovy
// [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
```

**Registration Application Input** (`func_apply_reg_with_bold`):
```groovy
// [sub, ses, run_id, conformed_bold, bids, func2target_xfm, ref_from_func_reg, anat2template_xfm, ref_from_anat_reg]
```

**Registration Application Output** (`func_apply_reg`):
```groovy
// [sub, ses, run_id, registered_bold, registered_boldref, bids]
```

### Anatomical Selection Channel

**Anatomical Selection** (`func_anat_selection`):
```groovy
// [sub, ses, run_id, anat_file, anat_ses, is_cross_ses]
```
- `anat_file`: Selected anatomical reference file
- `anat_ses`: Session ID of anatomical data (may differ from func session)
- `is_cross_ses`: Boolean indicating if cross-session match

### Registration Data Channels

**Anatomical Registration All** (`anat_reg_all`):
```groovy
// [sub, ses, anat2template_xfm, ref_from_anat_reg]
```
- Combined from same-session, cross-session, and dummy sources
- Real files preferred over dummy files

**Functional Registration with Reference** (`func_reg_with_ref`):
```groovy
// Session-level: [sub, ses, "", registered_tmean, func2target_xfm, ref_from_func_reg]
// Per-run: [sub, ses, run_id, registered_tmean, func2target_xfm, ref_from_func_reg, anat_ses, is_cross_ses]
```

## Anatomical Workflow Channels

### Initial Channels

**Job Discovery Channel** (`anat_jobs_ch`):
```groovy
// [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
```
- `file_objects`: List of file objects (may be single file)
- `needs_synth`: Boolean indicating if synthesis needed
- `suffix`: Modality suffix (e.g., "T1w", "T2w")
- `needs_t1w_reg`: Boolean for T2w files needing T1w registration

### Processing Step Channels

**After Synthesis** (`anat_synthesis_output`):
```groovy
// [sub, ses, anat_file, bids_naming_template]
```

**After Reorient** (`anat_after_reorient_normal`):
```groovy
// [sub, ses, anat_file, bids_template]
```

**After Conform** (`anat_after_conform`):
```groovy
// [sub, ses, anat_file, bids_template]
```

**Conform Transforms** (`anat_conform_transforms`):
```groovy
// [sub, ses, forward_xfm, inverse_xfm]
```

**Conform Reference** (`anat_conform_reference`):
```groovy
// [sub, ses, reference_file]
```

**After Bias Correction** (`anat_after_bias`):
```groovy
// [sub, ses, anat_file, bids_template]
```

**After Skull Stripping** (`anat_after_skull`):
```groovy
// [sub, ses, anat_file, bids_template]
```

**Skull Stripping Mask** (`anat_skull_mask`):
```groovy
// [sub, ses, brain_mask]
```

**Skull Stripping Segmentation** (`anat_skull_seg`):
```groovy
// [sub, ses, brain_segmentation]
```

**After Registration** (`anat_after_reg`):
```groovy
// [sub, ses, registered_file, bids_template]
```

**Registration Transforms** (`anat_reg_transforms`):
```groovy
// [sub, ses, forward_xfm, inverse_xfm]
```

**Registration Reference** (`anat_reg_reference`):
```groovy
// [sub, ses, reference_file]
```

## Channel Transformation Patterns

### Common Transformations

1. **Extract Single Element**:
   ```groovy
   .map { sub, ses, ... -> sub }  // Extract subject ID
   ```

2. **Add Element**:
   ```groovy
   .map { sub, ses, file -> [sub, ses, file, bids_template] }
   ```

3. **Remove Element**:
   ```groovy
   .map { sub, ses, run_id, file, bids -> [sub, ses, file, bids] }
   ```

4. **Reorder Elements**:
   ```groovy
   .map { sub, ses, a, b -> [sub, ses, b, a] }
   ```

### Joining Patterns

1. **Exact Match Join** (per-run):
   ```groovy
   channel1.join(channel2, by: [0, 1, 2])  // Match [sub, ses, run_id]
   ```

2. **Partial Match Combine** (session-level):
   ```groovy
   channel1.combine(channel2, by: [0, 1])  // Match [sub, ses] only
   ```

3. **MultiMap Split**:
   ```groovy
   channel.multiMap { sub, ses, file1, file2 ->
       combined: [sub, ses, file1]
       separate: file2
   }
   ```

## Important Notes

1. **Session-Level vs Per-Run**: The key difference is the `run_id` field:
   - Session-level: `run_id == ""` (empty string)
   - Per-run: `run_id` contains actual run identifier

2. **Channel Structure Consistency**: When modifying workflows, ensure:
   - Input channel structure matches process expectations
   - Output channel structure matches downstream process inputs
   - Tuple element positions remain consistent

3. **Join Keys**: The `by` parameter in `join()` and `combine()` refers to tuple element indices:
   - `by: [0, 1]` = match by first two elements (sub, ses)
   - `by: [0, 1, 2]` = match by first three elements (sub, ses, run_id)

4. **Dummy Files**: When steps are disabled, dummy files (`.dummy` extension) are used to maintain channel structure

## Debugging Channel Issues

When debugging channel problems:

1. **Check Structure**: Use `.view()` to inspect channel contents
2. **Verify Join Keys**: Ensure `by` parameter matches tuple structure
3. **Check for Empty Channels**: Empty channels can cause silent failures
4. **Validate Tuple Length**: Mismatched tuple lengths cause errors

## Examples

### Example 1: Session-Level Processing
```groovy
// Input: [sub, ses, "", tmean, bids]
def func_compute_input = func_tmean_averaged_ch
    .map { sub, ses, tmean, bids ->
        [sub, ses, "", tmean, bids]  // Empty run_id for session-level
    }

// Join with anatomical selection (matches by [sub, ses] only)
def func_with_anat = func_compute_input
    .combine(func_anat_selection, by: [0, 1])  // by: [0, 1] = [sub, ses]
```

### Example 2: Per-Run Processing
```groovy
// Input: [sub, ses, run_id, tmean, bids]
def func_compute_input = func_after_coreg
    .map { sub, ses, run_id, bold, tmean, bids ->
        [sub, ses, run_id, tmean, bids]
    }

// Join with anatomical selection (matches by [sub, ses, run_id])
def func_with_anat = func_compute_input
    .join(func_anat_selection, by: [0, 1, 2])  // by: [0, 1, 2] = [sub, ses, run_id]
```

### Example 3: Channel Splitting
```groovy
// Split channel for process that needs separate inputs
func_apply_reg_with_bold
    .multiMap { sub, ses, run_id, bold, bids, xfm, ref ->
        reg_params: [sub, ses, run_id, bids, xfm, ref]
        bold_file: bold
    }
    .set { split_channels }

PROCESS(split_channels.reg_params, split_channels.bold_file)
```

## References

- Nextflow Channel Documentation: https://www.nextflow.io/docs/latest/channel.html
- Workflow files: `workflows/functional_workflow.nf`, `workflows/anatomical_workflow.nf`
- Channel helpers: `workflows/channel_helpers.groovy`
- Functional channel operations: `workflows/functional_channels.groovy`
