# Refactoring Plan Analysis: Unified BOLD + tmean Channel Structure

## Current State Problems

### Issue 1: Inconsistent Output Structures
- **MOTION_CORRECTION**: Outputs BOLD + tmean (separate channels) ✅
- **DESPIKE**: Outputs BOLD + tmean (separate channels) ✅
- **BIAS_CORRECTION**: Outputs **tmean only** ❌ (loses BOLD!)
- **CONFORM**: Takes both as input, outputs both (separate channels) ✅
- **SKULLSTRIPPING**: Outputs brain + mask (no BOLD) ❌

### Issue 2: Complex Rejoining Logic
Currently at line 692-698, we have to **rejoin** BOLD and tmean:
```groovy
// func_after_bias: [sub, ses, task, run, tmean_file, bids_template] (6 elements)
// func_after_despike: [sub, ses, task, run, bold_4d_file, bids_template] (6 elements)
def func_tmean_and_bold = func_after_bias
    .join(func_after_despike, by: [0, 1, 2, 3])  // Rejoining what was split!
```

This is error-prone and creates the exact bug we just fixed.

### Issue 3: Lost Track of BOLD
After BIAS_CORRECTION, the BOLD channel is lost and must be retrieved from `func_after_despike`, creating dependency on previous steps.

---

## Proposed Solution: Unified Channel Structure

### New Channel Structure (Starting from MOTION_CORRECTION)
**Standard format**: `[sub, ses, task, run, bold_file, tmean_file, bids_naming_template]` (7 elements)

### Benefits
1. ✅ **Consistent structure** - Every step after motion correction has the same format
2. ✅ **No rejoining needed** - BOLD and tmean stay together
3. ✅ **Easier to track** - Always know what each channel contains
4. ✅ **Simpler joins** - No need to track separate channels
5. ✅ **Less error-prone** - Fewer opportunities for mismatched channels

### Implementation Strategy

#### Step 1: MOTION_CORRECTION (Starting Point)
**Current**: Two separate outputs
- `FUNC_MOTION_CORRECTION.out.output`: BOLD
- `FUNC_MOTION_CORRECTION.out.tmean`: tmean

**New**: Single combined output
- `FUNC_MOTION_CORRECTION.out.combined`: `[sub, ses, task, run, bold_file, tmean_file, bids_template]`

**Implementation**: 
- Process already generates both, just need to combine them in the output channel
- If step disabled, create combined channel from input: `[sub, ses, task, run, input_file, input_file, bids_template]` (use same file for both)

#### Step 2: DESPIKE
**Current**: Two separate outputs, takes only BOLD as input

**New**: 
- **Input**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- **Output**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- Process BOLD, inherit tmean from input (or process both if needed)

**Implementation**:
- If step processes BOLD only: output processed BOLD + input tmean
- If step processes both: output both processed
- If step disabled: pass through unchanged

#### Step 3: BIAS_CORRECTION
**Current**: Takes only tmean, outputs only tmean (loses BOLD!)

**New**:
- **Input**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- **Output**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- Process tmean, **inherit BOLD from input**

**Implementation**:
- Process tmean for bias correction
- Pass through BOLD unchanged
- Output: `[sub, ses, task, run, input_bold_file, processed_tmean_file, bids_template]`

#### Step 4: CONFORM
**Current**: Takes both as separate inputs (8 elements), outputs both separately

**New**:
- **Input**: `[sub, ses, task, run, bold_file, tmean_file, bids_template, anat_file]` (8 elements)
- **Output**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- Process both BOLD and tmean, output both

**Implementation**:
- Already processes both, just need to combine outputs into single channel

#### Step 5: SKULLSTRIPPING
**Current**: Takes only tmean, outputs brain + mask (no BOLD)

**New**:
- **Input**: `[sub, ses, task, run, bold_file, tmean_file, bids_template]` (7 elements)
- **Output**: `[sub, ses, task, run, bold_file, tmean_brain_file, bids_template]` (7 elements) + mask channel
- Process tmean → brain, **inherit BOLD from input**

**Implementation**:
- Process tmean to create brain
- Pass through BOLD unchanged
- Output: `[sub, ses, task, run, input_bold_file, processed_brain_file, bids_template]`
- Also output mask separately for QC: `[sub, ses, task, run, mask_file, bids_template]`

#### Step 6: REGISTRATION
**Current**: Takes only tmean/brain, outputs registered tmean

**New**:
- **Input**: `[sub, ses, task, run, bold_file, tmean_file, bids_template, anat_reg, anat_trans, anat_ses, is_fallback]` (11 elements)
- **Output**: `[sub, ses, task, run, bold_file, tmean_registered_file, bids_template]` (7 elements)
- Process tmean for registration, **inherit BOLD from input**

**Implementation**:
- Register tmean to template/anatomical
- Pass through BOLD unchanged (will be transformed later in APPLY_TRANSFORMS)
- Output: `[sub, ses, task, run, input_bold_file, registered_tmean_file, bids_template]`

---

## Comparison: Current vs Proposed

### Current Flow (Problematic)
```
MOTION: [BOLD] + [tmean] (separate)
  ↓
DESPIKE: [BOLD] + [tmean] (separate)
  ↓
BIAS: [tmean] only ❌ (BOLD lost!)
  ↓
CONFORM: Must rejoin BOLD + tmean ❌ (complex join)
  ↓
SKULL: [brain] only ❌ (BOLD lost!)
  ↓
REG: [registered_tmean] only ❌ (BOLD lost!)
```

### Proposed Flow (Clean)
```
MOTION: [BOLD, tmean] (combined)
  ↓
DESPIKE: [BOLD, tmean] (combined, inherit tmean if not processed)
  ↓
BIAS: [BOLD, tmean] (combined, inherit BOLD)
  ↓
CONFORM: [BOLD, tmean] (combined, process both)
  ↓
SKULL: [BOLD, brain] (combined, inherit BOLD)
  ↓
REG: [BOLD, registered_tmean] (combined, inherit BOLD)
```

---

## Implementation Details

### Helper Function for Inheritance
```groovy
// Helper to create combined channel when step is disabled
def createCombinedChannel = { sub, ses, task, run, file, bids_template ->
    [sub, ses, task, run, file, file, bids_template]  // Use same file for both
}

// Helper to inherit one component
def inheritBOLD = { sub, ses, task, run, bold_file, tmean_file, bids_template ->
    [sub, ses, task, run, bold_file, tmean_file, bids_template]  // Pass through
}

def inheritTmean = { sub, ses, task, run, bold_file, tmean_file, bids_template ->
    [sub, ses, task, run, bold_file, tmean_file, bids_template]  // Pass through
}
```

### Process Output Changes

#### FUNC_MOTION_CORRECTION
```groovy
output:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-motion_bold.nii.gz"), 
      path("*desc-motion_boldref.nii.gz"), 
      val(bids_naming_template), 
      emit: combined
// Keep separate outputs for backward compatibility if needed
```

#### FUNC_BIAS_CORRECTION
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),  // NEW: accept BOLD even though we don't process it
      path(tmean_file), 
      val(bids_naming_template)
path config_file

output:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),  // Pass through unchanged
      path("*desc-biascorrect_boldref.nii.gz"),  // Processed tmean
      val(bids_naming_template), 
      emit: combined
```

#### FUNC_SKULLSTRIPPING
```groovy
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),  // NEW: accept BOLD
      path(tmean_file), 
      val(bids_naming_template)
path config_file

output:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file),  // Pass through unchanged
      path("*_boldref_brain.nii.gz"),  // Processed brain
      val(bids_naming_template), 
      emit: combined
// Keep mask separate for QC
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("*desc-brain_mask.nii.gz"), 
      val(bids_naming_template), 
      emit: brain_mask
```

---

## Migration Strategy

### Phase 1: Update Process Definitions
1. Update FUNC_MOTION_CORRECTION to output combined channel
2. Update FUNC_DESPIKE to accept and output combined channel
3. Update FUNC_BIAS_CORRECTION to accept BOLD (inherit) and output combined
4. Update FUNC_CONFORM to accept and output combined channel
5. Update FUNC_SKULLSTRIPPING to accept BOLD (inherit) and output combined
6. Update FUNC_REGISTRATION to accept BOLD (inherit) and output combined

### Phase 2: Update main.nf Channel Flow
1. Change `func_after_motion` to use combined channel
2. Remove separate `func_motion_tmean` channel
3. Update DESPIKE to use combined channel
4. Remove separate `func_despike_tmean` channel
5. Update BIAS_CORRECTION to use combined channel
6. Remove complex join logic at CONFORM (lines 692-698)
7. Update SKULLSTRIPPING to use combined channel
8. Update REGISTRATION to use combined channel

### Phase 3: Update Downstream Steps
1. Update FUNC_APPLY_TRANSFORMS to extract BOLD from combined channel
2. Update QC processes if needed
3. Test all conditional paths (enabled/disabled combinations)

---

## Potential Concerns & Solutions

### Concern 1: Some steps don't need both files
**Solution**: They inherit the one they don't process. This is explicit and clear.

### Concern 2: Memory/disk usage
**Solution**: Nextflow handles file staging efficiently. We're not duplicating data, just keeping references together.

### Concern 3: Backward compatibility
**Solution**: Keep separate output channels for now (emit both `combined` and individual), deprecate later.

### Concern 4: Steps that genuinely need separate processing
**Solution**: They can still process separately internally, just combine at output.

---

## Recommendation

**✅ This plan is EXCELLENT and should be implemented.**

### Why?
1. **Eliminates the root cause** of the current bugs (lost BOLD, complex rejoins)
2. **Simplifies the codebase** significantly
3. **Makes the pipeline more maintainable**
4. **Reduces cognitive load** - always know what's in each channel
5. **Prevents future bugs** - can't lose track of BOLD anymore

### Suggested Refinements
1. **Start from MOTION_CORRECTION** as proposed ✅
2. **Use consistent naming**: `combined` output channel name
3. **Add validation**: Assert that combined channels always have 7 elements
4. **Document inheritance pattern**: Clearly mark which steps inherit vs process

### Alternative Consideration
Could start even earlier (from REORIENT), but MOTION_CORRECTION is a good starting point since that's when tmean is first created.

---

## Next Steps

1. Review this analysis
2. Decide on exact channel structure (7 elements vs 8 with additional metadata)
3. Create implementation plan with specific file changes
4. Implement incrementally (one step at a time)
5. Test each step thoroughly before moving to next

