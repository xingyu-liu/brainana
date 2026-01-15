# Phase 3, Item 9: Simplify Registration Channel Joining

## Overview

This document describes the simplification of complex registration channel joining operations in `workflows/functional_workflow.nf` (lines 497-697). The goal was to break down nested combines/joins into smaller, well-named intermediate channels with clear comments, without changing the logic.

## Approach

Instead of creating helper functions (which can't call processes), we:
1. **Broke down complex operations** into 3-4 clear steps each
2. **Created well-named intermediate channels** that explain what each step does
3. **Added step-by-step comments** showing input/output channel structures
4. **Preserved all logic** - no functional changes

## Changes Made

### 1. Anatomical Registration Data Preparation (Lines 507-524)

**Before**: Single operation combining transform extraction and joining
**After**: Two clear steps with intermediate channel

```groovy
// Step 1: Extract forward transform
def anat_reg_transforms_forward = anat_reg_transforms
    .map { sub, ses, anat2template_xfm, inverse_transform ->
        [sub, ses, anat2template_xfm]
    }

// Step 2: Join transform with reference
def anat_reg_all_real = anat_reg_transforms_forward
    .join(anat_reg_reference, by: [0, 1])
    .map { sub, ses, anat2template_xfm, ref_from_anat_reg -> 
        [sub, ses, anat2template_xfm, ref_from_anat_reg]
    }
```

**Improvement**: Clear separation of transform extraction and joining steps

### 2. Session Mapping (Lines 526-551)

**Before**: Single operation with inline filtering
**After**: Three clear steps

```groovy
// Step 1: Extract session mapping
def func_ses_mapping_raw = func_compute_reg_output
    .map { sub, ses, run_id, registered_tmean, bids, anat_ses, is_cross_ses ->
        [sub, ses, anat_ses, is_cross_ses]
    }

// Step 2: Deduplicate
def func_ses_mapping = func_ses_mapping_raw
    .unique { sub, ses, anat_ses, is_cross_ses -> [sub, ses] }

// Step 3: Split into same-session and cross-session
def func_ses_same = func_ses_mapping
    .filter { sub, ses, anat_ses, is_cross_ses -> !is_cross_ses }
    .map { sub, ses, anat_ses, is_cross_ses -> [sub, ses] }

def func_ses_cross = func_ses_mapping
    .filter { sub, ses, anat_ses, is_cross_ses -> is_cross_ses }
    .map { sub, ses, anat_ses, is_cross_ses -> [sub, ses, anat_ses] }
```

**Improvement**: Each step has a clear purpose and intermediate channel name

### 3. Cross-Session Joining (Lines 562-567)

**Before**: Single operation with inline reordering
**After**: Three clear steps

```groovy
// Step 2a: Reorder for joining
def func_ses_cross_reordered = func_ses_cross
    .map { sub, ses_func, anat_ses -> [sub, anat_ses, ses_func] }

// Step 2b: Join with anatomical registration
def anat_reg_cross_ses_joined = func_ses_cross_reordered
    .join(anat_reg_all_real, by: [0, 1])

// Step 2c: Map back to functional session
def anat_reg_cross_ses = anat_reg_cross_ses_joined
    .map { sub, anat_ses, ses_func, xfm, ref -> [sub, ses_func, xfm, ref] }
```

**Improvement**: Each transformation step is clearly named and documented

### 4. Combining All Anatomical Registration Sources (Lines 580-604)

**Before**: Single complex operation with nested map/groupTuple operations
**After**: Four clear steps

```groovy
// Step 1: Mix all sources
def anat_reg_all_mixed = anat_reg_same_ses
    .mix(anat_reg_cross_ses)
    .mix(anat_reg_all_dummy)

// Step 2: Wrap pairs for groupTuple
def anat_reg_all_wrapped = anat_reg_all_mixed
    .map { sub, ses, xfm, ref ->
        [sub, ses, [xfm, ref]]
    }

// Step 3: Group by [sub, ses]
def anat_reg_all_grouped = anat_reg_all_wrapped
    .groupTuple(by: [0, 1])

// Step 4: Select best entry
def anat_reg_all = anat_reg_all_grouped
    .map { sub, ses, entries ->
        def selected = entries.find { xfm, ref ->
            !(xfm.toString().contains('.dummy') || ref.toString().contains('.dummy'))
        } ?: entries[0]
        [sub, ses] + selected
    }
    .map { sub, ses, xfm, ref ->
        [sub, ses, xfm, ref]
    }
```

**Improvement**: Each step of the complex operation is now clearly separated and named

### 5. Functional Registration Data Preparation (Lines 611-674)

**Before**: Nested combines/joins in single operations
**After**: Step-by-step progression with intermediate channels

**Session-Level Path**:
```groovy
// Step 1: Extract forward transform
def func_reg_transforms_forward = FUNC_COMPUTE_REGISTRATION.out.transforms
    .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
        [sub, ses, run_id, func2target_xfm]
    }

// Step 2: Combine functional registration outputs
def func_reg_with_transform = func_compute_reg_output
    .combine(func_reg_transforms_forward, by: [0, 1])

def func_reg_with_ref = func_reg_with_transform
    .combine(FUNC_COMPUTE_REGISTRATION.out.reference, by: [0, 1])
    .map { ... }

// Step 3: Combine with anatomical registration
def func_reg_with_anat = func_reg_with_ref
    .combine(anat_reg_all, by: [0, 1])
    .map { ... }

// Step 4: Join with BOLD data
func_apply_reg_with_bold = func_apply_conform_output
    .combine(func_reg_with_anat, by: [0, 1])
    .map { ... }
```

**Per-Run Path**: Similar step-by-step structure with `join()` instead of `combine()`

**Improvement**: Clear progression from one step to the next, easy to follow the data flow

### 6. APPLY CONFORM Section (Lines 441-485)

**Before**: Nested combines/joins in single operations
**After**: Step-by-step with intermediate channels

```groovy
if (func_coreg_runs_within_session && func_coreg_success) {
    // Step 1: Extract forward transform
    def func_conform_forward_xfm = func_compute_conform_transforms
        .map { sub, ses, run_id, func2target_xfm, inverse_transform ->
            [sub, ses, func2target_xfm]
        }
    
    // Step 2: Combine BOLD with conformed tmean
    def func_apply_with_conformed = func_apply_bold_input
        .combine(func_compute_conform_output, by: [0, 1])
    
    // Step 3: Combine with transform
    func_apply_conform_input = func_apply_with_conformed
        .combine(func_conform_forward_xfm, by: [0, 1])
        .map { ... }
} else {
    // Similar structure for per-run path
}
```

**Improvement**: Each combine/join operation is now a separate, clearly named step

## Benefits

1. **Easier to Understand**: Each step has a clear purpose and descriptive name
2. **Easier to Debug**: Can inspect intermediate channels to see data at each stage
3. **Easier to Modify**: Changes can be made to individual steps without affecting others
4. **Better Documentation**: Step-by-step comments explain the flow
5. **No Logic Changes**: All functionality preserved, just reorganized

## Channel Naming Convention

Intermediate channels follow a clear naming pattern:
- `*_raw` - Initial extraction before processing
- `*_forward` - Forward transform extraction
- `*_with_*` - Combined channels (e.g., `func_reg_with_ref`)
- `*_reordered` - Reordered for joining
- `*_joined` - Result of join operation
- `*_mixed` - Result of mix operation
- `*_wrapped` - Wrapped for groupTuple
- `*_grouped` - Result of groupTuple

## Testing

All changes preserve existing functionality:
- ✅ Same channel structures at each stage
- ✅ Same join/combine operations (just broken into steps)
- ✅ Same output channels
- ✅ No functional changes

## Files Modified

- `workflows/functional_workflow.nf` - Simplified registration channel joining section

## Next Steps (Item 8)

After completing item 9, item 8 (extract session-level vs per-run branching) can be tackled. The simplified channel operations from item 9 will make item 8 easier to implement.
