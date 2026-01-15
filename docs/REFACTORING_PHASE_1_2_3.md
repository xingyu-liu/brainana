# Refactoring Phases 1, 2, and 3 - Code Improvements

This document describes the refactoring work done to improve code simplicity, efficiency, clarity, and maintainability while preserving all functionality.

## Overview

The refactoring was done in three phases:
- **Phase 1**: Low-risk cleanup (duplicate removal, redundant code elimination)
- **Phase 2**: Extract common patterns (helper functions, centralized config handling)
- **Phase 3**: Simplify complex channel operations (documentation, channel structure clarity)

## Phase 1: Low-Risk Cleanup

### Changes Made

1. **Removed Duplicate Print Statements**
   - **File**: `workflows/anatomical_workflow.nf`
   - **Issue**: Duplicate header print block (lines 126-136)
   - **Fix**: Removed the duplicate block, keeping only the first one with the effective config path

2. **Consolidated Effective Config Path**
   - **File**: `main.nf`
   - **Issue**: Hardcoded config path string repeated in multiple places
   - **Fix**: Defined as constant `EFFECTIVE_CONFIG_PATH` (though later changed to helper function approach)

3. **Removed Redundant Config Loading**
   - **Files**: `modules/functional.nf`, `modules/anatomical.nf`
   - **Issue**: Multiple processes loaded config file twice (e.g., FUNC_REORIENT, FUNC_COMPUTE_CONFORM, ANAT_REORIENT, ANAT_REGISTRATION)
   - **Fix**: Removed duplicate `load_config()` calls, using the already-loaded config variable

### Impact
- Reduced code duplication
- Eliminated unnecessary file I/O operations
- No functional changes

## Phase 2: Extract Common Patterns

### Changes Made

1. **Created Config Helpers Module**
   - **New File**: `workflows/config_helpers.groovy`
   - **Purpose**: Centralized configuration file handling
   - **Functions**:
     - `ensureParamResolverInitialized()`: Safe initialization of parameter resolver
     - `getEffectiveConfigPath()`: Validates and returns config file path as string

2. **Updated Workflows to Use Helpers**
   - **Files**: `workflows/anatomical_workflow.nf`, `workflows/functional_workflow.nf`
   - **Change**: Replaced duplicate try-catch blocks and config loading logic with helper function calls
   - **Benefit**: Single source of truth for config handling, easier to maintain

3. **Fixed File Path Resolution Issue**
   - **Issue**: Nextflow was trying to resolve `file()` paths at definition time, before config file was generated
   - **Solution**: Pass string paths directly to processes instead of using `file()` in workflow blocks
   - **Rationale**: Nextflow automatically converts string paths to file objects when processes execute

### Impact
- Reduced code duplication across workflows
- Centralized error handling
- Fixed early file validation issues
- Improved maintainability

## Phase 3: Simplify Complex Channel Operations

### Changes Made

1. **Added Comprehensive Channel Structure Documentation**
   - **Files**: `workflows/functional_workflow.nf`, `workflows/anatomical_workflow.nf`
   - **Purpose**: Document channel tuple structures at key transformation points
   - **Format**: Detailed comments showing:
     - Input channel structure: `[sub, ses, run_id, ...]`
     - Output channel structure: `[sub, ses, run_id, ...]`
     - Transformation description
   - **Locations**:
     - **Functional Workflow**:
       - Job parsing and initial channel creation
       - Slice timing, reorient, motion correction steps
       - Within-session coregistration
       - Anatomical selection
       - Compute phase (session-level vs per-run)
       - Apply phase (conform, registration)
       - Registration channel joining (complex section)
     - **Anatomical Workflow**:
       - Job parsing
       - Reorient, conform, bias correction, skull stripping
       - Registration outputs

2. **Improved Channel Operation Clarity**
   - Added section headers with `============================================` separators
   - Documented complex channel joining operations with:
     - Input channel structures
     - Output channel structures
     - Purpose of each transformation
   - Documented session-level vs per-run processing differences
   - Clarified channel structure evolution through the pipeline
   - Added comments explaining why certain operations use `join()` vs `combine()`

3. **Simplified Registration Channel Joining (Item 9)**
   - **Location**: `workflows/functional_workflow.nf` lines 497-697
   - **Improvements**:
     - **Broke down complex nested operations** into smaller, well-named intermediate channels:
       - `anat_reg_transforms_forward` - Extracted forward transform
       - `anat_reg_all_real` - Combined transform and reference
       - `func_ses_mapping_raw` → `func_ses_mapping` - Session mapping extraction
       - `func_ses_same` / `func_ses_cross` - Split by session type
       - `func_ses_cross_reordered` → `anat_reg_cross_ses_joined` → `anat_reg_cross_ses` - Cross-session joining steps
       - `func_subjects_sessions` - Unique subject-session pairs
       - `anat_reg_all_mixed` → `anat_reg_all_wrapped` → `anat_reg_all_grouped` → `anat_reg_all` - Combining all sources
       - `func_reg_transforms_forward` - Functional transform extraction
       - `func_reg_with_transform` → `func_reg_with_ref` → `func_reg_with_anat` - Progressive combination
     - **Simplified APPLY CONFORM section**:
       - Extracted `func_conform_forward_xfm` as intermediate channel
       - Split nested combines into clear step-by-step operations
       - Added intermediate channels: `func_apply_with_conformed`
     - **Improved session-level vs per-run paths**:
       - Both paths now use same intermediate channel names where applicable
       - Clear step-by-step progression documented
     - **Result**: Complex operations are now broken into 3-4 clear steps each, making the flow much easier to follow

### Channel Structure Reference

#### Functional Workflow Channels

**Initial Job Channel**:
```groovy
// [sub, ses, run_identifier, file_obj, bids_naming_template]
def func_jobs_ch
```

**After Slice Timing/Reorient/Motion**:
```groovy
// [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
def func_after_motion
```

**After Coregistration**:
```groovy
// [sub, ses, run_identifier, bold_file, tmean_file, bids_template]
def func_after_coreg
```

**Compute Phase (Session-level)**:
```groovy
// Input: [sub, ses, "", tmean, bids]  (run_id is empty for session-level)
// After bias: [sub, ses, "", bias_corrected_tmean, bids]
// After conform: [sub, ses, "", conformed_tmean, bids]
// After mask: [sub, ses, "", masked_tmean, bids, brain_mask]
```

**Compute Phase (Per-run)**:
```groovy
// Input: [sub, ses, run_id, tmean, bids]
// After bias: [sub, ses, run_id, bias_corrected_tmean, bids]
// After conform: [sub, ses, run_id, conformed_tmean, bids]
// After mask: [sub, ses, run_id, masked_tmean, bids, brain_mask]
```

**Apply Phase**:
```groovy
// Input: [sub, ses, run_id, bold_file, tmean_file, bids_template]
// After conform: [sub, ses, run_id, conformed_bold, conformed_tmean_ref, bids]
// After registration: [sub, ses, run_id, registered_bold, registered_boldref, bids]
```

#### Anatomical Workflow Channels

**Initial Job Channel**:
```groovy
// [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg]
def anat_jobs_ch
```

**After Processing Steps**:
```groovy
// [sub, ses, anat_file, bids_template]
def anat_after_reorient
def anat_after_conform
def anat_after_bias
def anat_after_skull
```

**Registration Outputs**:
```groovy
// Transforms: [sub, ses, forward_transform, inverse_transform]
def anat_reg_transforms

// Reference: [sub, ses, reference_file]
def anat_reg_reference
```

### Key Patterns Identified

1. **Session-Level vs Per-Run Processing**
   - **Condition**: When `func_coreg_runs_within_session && func_coreg_success`
   - **Session-Level Path**:
     - Compute phase operates on session-level averaged tmean (run_id == "")
     - Channel structure: `[sub, ses, "", ...]` (empty run_id)
     - Uses `combine()` for joining (matches by `[sub, ses]` only)
   - **Per-Run Path**:
     - Both compute and apply phases operate per-run
     - Channel structure: `[sub, ses, run_id, ...]`
     - Uses `join()` for joining (matches by `[sub, ses, run_id]`)
   - **Documentation**: Both paths are clearly marked with section headers

2. **Channel Joining Patterns**
   - **`join()`**: Used when matching by exact keys
     - Example: `join(..., by: [0, 1, 2])` matches `[sub, ses, run_id]`
     - Used in per-run processing paths
   - **`combine()`**: Used when matching by subset of keys
     - Example: `combine(..., by: [0, 1])` matches `[sub, ses]` only
     - Used in session-level processing paths
   - **`multiMap()`**: Used to split channels for processes that need separate inputs
     - Example: Split BOLD file from registration parameters

3. **Dummy File Pattern**
   - Used when steps are disabled or data is missing
   - Dummy files created with `.dummy` extension
   - Processes check for dummy files to determine if step was skipped
   - Example: `dummy_anat.dummy` when no anatomical data available

4. **Registration Channel Joining Pattern**
   - **Complexity**: Lines 458-695 in functional_workflow.nf
   - **Steps**:
     1. Prepare anatomical registration data (combine transforms + reference)
     2. Map functional to anatomical sessions (same-session vs cross-session)
     3. Join anatomical registration by session type
     4. Create dummy registration for missing data
     5. Mix all channels and select real over dummy
     6. Combine with functional registration outputs
     7. Join with BOLD data for application
   - **Documentation**: Each step now has clear comments explaining purpose and channel structures

## Files Modified

### New Files
- `workflows/config_helpers.groovy` - Configuration helper functions

### Modified Files
- `main.nf` - Added config file verification
- `workflows/anatomical_workflow.nf` - Removed duplicates, added helpers, added channel docs
- `workflows/functional_workflow.nf` - Removed duplicates, added helpers, added channel docs
- `modules/functional.nf` - Removed redundant config loads
- `modules/anatomical.nf` - Removed redundant config loads

## Testing Recommendations

After these refactorings, verify:
1. ✅ Same outputs generated (file names, structure)
2. ✅ Same behavior with different configs
3. ✅ No new errors introduced
4. ✅ Config file handling works correctly
5. ✅ Channel structures match documented formats

## Phase 3 Item 9: Simplify Registration Channel Joining (Completed ✅)

### Changes Made

1. **Broke Down Complex Nested Operations**
   - Anatomical registration preparation: 2 steps (extract → join)
   - Session mapping: 3 steps (extract → deduplicate → split)
   - Cross-session joining: 3 steps (reorder → join → map back)
   - Combining all sources: 4 steps (mix → wrap → group → select)
   - Functional registration preparation: 4 steps per path
   - APPLY CONFORM: 3 steps per path

2. **Created Well-Named Intermediate Channels**
   - `anat_reg_transforms_forward` - Forward transform extraction
   - `func_ses_mapping_raw` → `func_ses_mapping` - Session mapping progression
   - `func_ses_cross_reordered` → `anat_reg_cross_ses_joined` → `anat_reg_cross_ses` - Cross-session steps
   - `func_subjects_sessions` - Unique subject-session pairs
   - `anat_reg_all_mixed` → `anat_reg_all_wrapped` → `anat_reg_all_grouped` → `anat_reg_all` - Combining steps
   - `func_reg_transforms_forward` - Functional transform extraction
   - `func_reg_with_transform` → `func_reg_with_ref` → `func_reg_with_anat` - Progressive combination
   - `func_conform_forward_xfm` - Conform transform extraction
   - `func_apply_with_conformed` - Intermediate combination step

3. **Added Step-by-Step Documentation**
   - Each step has clear comments showing:
     - Input channel structure
     - Output channel structure
     - Purpose of the transformation
   - Section headers separate major operations

### Impact

- **Clarity**: Complex operations are now broken into 3-4 clear steps each
- **Maintainability**: Easy to modify individual steps
- **Debugging**: Can inspect intermediate channels at each stage
- **No Logic Changes**: All functionality preserved

See `PHASE_3_ITEM_9_SIMPLIFICATION.md` for detailed breakdown.

## Future Improvements (Not Yet Implemented)

### Phase 3 Item 8: Extract Session-Level vs Per-Run Branching

1. **Extract Session-Level vs Per-Run Logic**
   - The compute phase (lines 230-431) has significant duplication
   - Both paths follow same pattern: bias → conform → mask → registration
   - Could extract common pattern while keeping process calls in workflow
   - Approach: Create helper functions for channel transformations, but keep process calls in workflow

2. **Standardize Process Script Patterns**
   - Many processes have similar patterns for:
     - Config loading
     - BIDS filename generation
     - Metadata saving
     - Command log initialization
   - Could create standard template/helper functions

3. **Add Channel Validation**
   - Helper functions to validate channel structures
   - Early error detection for channel mismatches

## Notes for Other Agents

### Working with Channel Structures

When modifying workflows:
1. **Check channel structure comments** - They document what each channel contains
2. **Maintain tuple order** - Channel operations depend on tuple element positions
3. **Update comments** - If you change channel structure, update the documentation comments
4. **Test joins carefully** - Channel joins are sensitive to tuple structure and key positions

### Working with Config Helpers

- Use `configHelpers.getEffectiveConfigPath()` to get config file path
- Pass string paths directly to processes (Nextflow handles conversion)
- Don't use `file()` in workflow blocks - it causes early validation issues

### Common Pitfalls

1. **Early file validation**: Don't use `file()` in workflow definition blocks
2. **Channel structure mismatches**: Always check tuple structure before joining channels
3. **Session-level vs per-run**: Be aware of which mode the pipeline is in
4. **Dummy files**: Check for `.dummy` extension when determining if step was skipped

## References

- Channel helpers: `workflows/channel_helpers.groovy`
- Functional channel operations: `workflows/functional_channels.groovy`
- Config helpers: `workflows/config_helpers.groovy`
- Parameter resolver: `workflows/param_resolver.groovy`
