# Handling Additional Files in Unified Channel Structure

## Current Additional Files

### 1. Motion Parameters
- **Source**: FUNC_MOTION_CORRECTION
- **Output**: `FUNC_MOTION_CORRECTION.out.motion_params`
- **Structure**: `[sub, ses, task, run, motion_params_file]`
- **Usage**: QC only (line 897-902)

### 2. Brain Mask
- **Source**: FUNC_SKULLSTRIPPING
- **Output**: `FUNC_SKULLSTRIPPING.out.brain_mask`
- **Structure**: `[sub, ses, task, run, mask_file, bids_template]`
- **Usage**: QC only (line 932-941)

### 3. Brain (Skull-stripped tmean)
- **Source**: FUNC_SKULLSTRIPPING
- **Output**: `FUNC_SKULLSTRIPPING.out.brain`
- **Structure**: `[sub, ses, task, run, brain_file, bids_template]`
- **Usage**: **Currently replaces tmean in main flow** (line 730: `func_after_skull = func_skull_brain`)

### 4. Transforms (CONFORM)
- **Source**: FUNC_CONFORM
- **Output**: `FUNC_CONFORM.out.transforms`
- **Structure**: Transform files (`.mat` files)
- **Usage**: Not currently used downstream (stored for reference)

### 5. Transforms (REGISTRATION)
- **Source**: FUNC_REGISTRATION
- **Output**: `FUNC_REGISTRATION.out.transforms` (forward) + `FUNC_REGISTRATION.out.inverse_transforms` (inverse)
- **Structure**: `[sub, ses, task, run, transform_file]`
- **Usage**: **Critical for FUNC_APPLY_TRANSFORMS** (line 820-850)

### 6. Template Resampled
- **Source**: FUNC_CONFORM
- **Output**: `FUNC_CONFORM.out.template_resampled`
- **Structure**: `[sub, ses, task, run, template_file, bids_template]`
- **Usage**: QC only (line 920-927)

---

## Solution: Hybrid Approach

### Main Combined Channel (7 elements)
**Structure**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]`

- This is the **primary data flow**
- After SKULLSTRIPPING, `tmean_file` becomes `brain_file` (it's still the tmean, just skull-stripped)
- After REGISTRATION, `tmean_file` becomes `registered_tmean_file`

### Additional Files (Separate Channels)
**Keep as separate output channels** - they serve different purposes:

1. **QC-only files**: brain_mask, motion_params, template_resampled
   - Don't need to be in main flow
   - Used only for QC visualization
   - Keep as separate channels ✅

2. **Transform files**: CONFORM transforms, REGISTRATION transforms
   - Used downstream but not part of main data flow
   - Keep as separate channels ✅
   - Join with main channel when needed (e.g., for APPLY_TRANSFORMS)

3. **Brain from skullstripping**: 
   - **This is special** - it replaces tmean in the main flow
   - In unified structure: brain becomes the new `tmean_file` in combined channel
   - No separate channel needed for main flow ✅

---

## Updated Process Definitions

### FUNC_MOTION_CORRECTION
```groovy
output:
// Main combined channel
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-motion_bold.nii.gz"),      // BOLD
      path("*desc-motion_boldref.nii.gz"),   // tmean
      val(bids_naming_template), 
      emit: combined

// Additional files (separate channels)
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-confounds_timeseries.tsv"), 
      emit: motion_params  // For QC only

path "*.json", emit: metadata
```

### FUNC_DESPIKE
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file), 
      path(tmean_file), 
      val(bids_naming_template)
path config_file

output:
// Main combined channel
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-despike_bold.nii.gz"),      // Processed BOLD
      path("*desc-despike_boldref.nii.gz"),   // Processed tmean (or inherited)
      val(bids_naming_template), 
      emit: combined

path "*.json", emit: metadata
```

### FUNC_BIAS_CORRECTION
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),      // NEW: Accept BOLD (inherit)
      path(tmean_file),     // Process this
      val(bids_naming_template)
path config_file

output:
// Main combined channel
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),                          // Inherited from input (pass through)
      path("*desc-biascorrect_boldref.nii.gz"), // Processed tmean
      val(bids_naming_template), 
      emit: combined

path "*.json", emit: metadata
```

### FUNC_CONFORM
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(tmean_file), 
      path(bold_4d_file), 
      val(bids_naming_template), 
      path(anat_brain_file)
path config_file

output:
// Main combined channel
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-conform_bold.nii.gz"),      // Processed BOLD
      path("*desc-conform_boldref.nii.gz"),   // Processed tmean
      val(bids_naming_template), 
      emit: combined

// Additional files (separate channels)
path "*.mat", emit: transforms  // For reference/QC
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("template_resampled.nii.gz"), 
      val(bids_naming_template), 
      emit: template_resampled  // For QC only

path "*.json", emit: metadata
```

### FUNC_SKULLSTRIPPING
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),      // NEW: Accept BOLD (inherit)
      path(tmean_file),     // Process this → brain
      val(bids_naming_template)
path config_file

output:
// Main combined channel (brain replaces tmean)
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),                    // Inherited from input (pass through)
      path("*_boldref_brain.nii.gz"),     // Processed brain (replaces tmean)
      val(bids_naming_template), 
      emit: combined

// Additional files (separate channels)
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-brain_mask.nii.gz"), 
      val(bids_naming_template), 
      emit: brain_mask  // For QC only

path "*.json", emit: metadata
```

### FUNC_REGISTRATION
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),           // NEW: Accept BOLD (inherit)
      path(tmean_file),          // Process this → registered tmean
      val(bids_naming_template), 
      path(anat_registered), 
      path(anat_transforms), 
      val(anat_session_id), 
      val(is_fallback)
path config_file

output:
// Main combined channel
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),                    // Inherited from input (pass through)
      path("*space-*boldref.nii.gz"),     // Registered tmean
      val(bids_naming_template), 
      emit: combined

// Additional files (separate channels)
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*from-bold_to-*_mode-image_xfm.h5"), 
      emit: transforms  // For APPLY_TRANSFORMS

tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*from-*_to-bold_mode-image_xfm.h5"), 
      emit: inverse_transforms  // For inverse transforms if needed

path "*.json", emit: metadata
```

---

## Updated Channel Flow in main.nf

### After MOTION_CORRECTION
```groovy
func_after_motion = FUNC_MOTION_CORRECTION.out.combined
// Structure: [sub, ses, task, run, bold_file, tmean_file, bids_template]

func_motion_params = FUNC_MOTION_CORRECTION.out.motion_params
// Separate channel for QC
```

### After DESPIKE
```groovy
func_after_despike = FUNC_DESPIKE.out.combined
// Structure: [sub, ses, task, run, bold_file, tmean_file, bids_template]
```

### After BIAS_CORRECTION
```groovy
func_after_bias = FUNC_BIAS_CORRECTION.out.combined
// Structure: [sub, ses, task, run, bold_file, tmean_file, bids_template]
// Note: bold_file is inherited, tmean_file is processed
```

### After CONFORM
```groovy
func_after_conform = FUNC_CONFORM.out.combined
// Structure: [sub, ses, task, run, bold_file, tmean_file, bids_template]

func_conform_transforms = FUNC_CONFORM.out.transforms
// Separate channel (not used downstream currently, but available)
```

### After SKULLSTRIPPING
```groovy
func_after_skull = FUNC_SKULLSTRIPPING.out.combined
// Structure: [sub, ses, task, run, bold_file, brain_file, bids_template]
// Note: brain_file replaces tmean_file (it's the skull-stripped tmean)

func_skull_mask = FUNC_SKULLSTRIPPING.out.brain_mask
// Separate channel for QC: [sub, ses, task, run, mask_file, bids_template]
```

### After REGISTRATION
```groovy
func_after_reg = FUNC_REGISTRATION.out.combined
// Structure: [sub, ses, task, run, bold_file, registered_tmean_file, bids_template]
// Note: bold_file is inherited, registered_tmean_file is processed

func_reg_transforms = FUNC_REGISTRATION.out.transforms
// Separate channel for APPLY_TRANSFORMS: [sub, ses, task, run, transform_file]
```

### For APPLY_TRANSFORMS
```groovy
// Join main channel with transforms
def func_reg_with_transforms = func_after_reg
    .join(func_reg_transforms, by: [0, 1, 2, 3])
    .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, transform_file ->
        // Extract BOLD from combined channel for APPLY_TRANSFORMS
        // Use registered_tmean as reference
        [sub, ses, task, run, registered_tmean, transform_file, bids_template, bold_file]
    }

FUNC_APPLY_TRANSFORMS(func_reg_with_transforms, config_file)
```

---

## Key Points

### ✅ What Stays in Combined Channel
- **BOLD file**: Always present, inherited when not processed
- **tmean/brain/registered_tmean**: The "tmean" slot evolves:
  - After MOTION: tmean
  - After SKULLSTRIPPING: brain (skull-stripped tmean)
  - After REGISTRATION: registered_tmean
- **bids_template**: Always present

### ✅ What Stays as Separate Channels
- **QC files**: brain_mask, motion_params, template_resampled
  - Used only for visualization
  - Don't need to be in main flow
  
- **Transform files**: CONFORM transforms, REGISTRATION transforms
  - Used downstream but not part of main data flow
  - Join with main channel when needed

### ✅ Benefits
1. **Main flow is clean**: Always know what's in the combined channel
2. **Additional files are explicit**: Clear separation of concerns
3. **Easy to join**: When transforms are needed, join with main channel
4. **No data loss**: Everything is tracked, just organized better

---

## Example: APPLY_TRANSFORMS Input

**Current (complex)**:
```groovy
// func_after_reg: [sub, ses, task, run, tmean_reg, bids_template] (6 elements)
// func_reg_transforms: [sub, ses, task, run, transform] (5 elements)
// func_after_conform: [sub, ses, task, run, bold_4d, bids_template] (6 elements)
// Must join all three channels! ❌
```

**Proposed (simple)**:
```groovy
// func_after_reg: [sub, ses, task, run, bold_file, registered_tmean, bids_template] (7 elements)
// func_reg_transforms: [sub, ses, task, run, transform] (5 elements)
// Join by [0,1,2,3] and extract bold_file from combined channel ✅
def func_apply_input = func_after_reg
    .join(func_reg_transforms, by: [0, 1, 2, 3])
    .map { sub, ses, task, run, bold_file, registered_tmean, bids_template, transform_file ->
        // Extract what we need
        [sub, ses, task, run, registered_tmean, transform_file, bids_template, bold_file]
    }
```

---

## Summary

**Yes, the unified structure handles additional files perfectly!**

- **Main data flow**: Combined channel with BOLD + tmean/brain
- **Additional files**: Separate channels (transforms, masks, params)
- **When needed**: Join additional channels with main channel
- **Clean separation**: Main flow vs. QC vs. metadata

This approach gives us:
1. ✅ Consistent main channel structure
2. ✅ Clear separation of additional files
3. ✅ Easy joining when needed
4. ✅ No data loss or confusion

