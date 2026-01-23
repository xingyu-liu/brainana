# Detailed Implementation Plan: Anatomical Synthesis Improvements

## Overview

This document provides a step-by-step implementation plan for improving the anatomical synthesis code. The improvements are organized by priority and include detailed steps, test cases, and validation criteria.

## Issue Found: Inconsistent Documentation

**Discovery**: The flowchart incorrectly showed T2w anatomical selection priority. The actual implementation (`performT2wAnatomicalSelection`) has the same priority as functional:
1. Subject-level T1w (HIGHEST PRIORITY)
2. Same-session T1w
3. Cross-session T1w
4. No T1w

**Action**: Flowchart has been corrected. Also need to fix misleading comment in `anatomical_workflow.nf` line 765.

---

## Phase 1: High Priority Improvements

### 1.1 Session ID Normalization Utilities

**Goal**: Eliminate code duplication for session ID handling across Python and Groovy code.

#### Step 1.1.1: Create Python Utility Function

**File**: `macacaMRIprep/utils/nextflow.py`

**Action**:
```python
def normalize_session_id(session_id_raw: Optional[str]) -> Optional[str]:
    """
    Normalize session ID from Nextflow.
    
    Handles various representations of empty/null session IDs:
    - None
    - Empty string ""
    - Whitespace-only strings
    - String "null" (Nextflow may pass "null" as a string)
    
    Args:
        session_id_raw: Raw session ID from Nextflow
        
    Returns:
        Normalized session ID string, or None if empty/null
    """
    if not session_id_raw:
        return None
    
    session_id = session_id_raw.strip()
    if not session_id or session_id.lower() == 'null':
        return None
    
    return session_id
```

**Test Cases**:
- `None` → `None`
- `""` → `None`
- `"  "` → `None`
- `"null"` → `None`
- `"NULL"` → `None`
- `"  null  "` → `None`
- `"001"` → `"001"`
- `"  ses-001  "` → `"ses-001"`

**Validation**: Add unit tests in `tests/utils/test_nextflow.py`

---

#### Step 1.1.2: Create Groovy Helper Function

**File**: `workflows/channel_helpers.groovy`

**Action**: Add at the top of the file (after imports/initial setup):
```groovy
/**
 * Normalize session ID from Nextflow.
 * Handles None, empty string, whitespace, and string "null".
 * 
 * @param ses Session ID to normalize
 * @return Normalized session ID string, or null if empty/null
 */
def normalizeSessionId = { ses ->
    if (ses == null || ses == "") {
        return null
    }
    if (ses instanceof String) {
        def trimmed = ses.trim()
        if (trimmed == "" || trimmed.toLowerCase() == 'null') {
            return null
        }
        return trimmed
    }
    return ses
}
```

**Test Cases** (manual testing in Nextflow):
- `null` → `null`
- `""` → `null`
- `"  "` → `null`
- `"null"` → `null`
- `"NULL"` → `null`
- `"  null  "` → `null`
- `"001"` → `"001"`
- `"  ses-001  "` → `"ses-001"`

**Validation**: Test in Nextflow REPL or add to test workflow

---

#### Step 1.1.3: Replace Python Code in ANAT_SYNTHESIS

**File**: `modules/anatomical.nf`

**Lines to Replace**: 40-46, 92-100, 126-127

**Before**:
```python
session_id_raw = '${session_id}'
import sys
# Handle empty string, None, whitespace-only, and the string "null"
if session_id_raw and session_id_raw.strip() and session_id_raw.strip().lower() != 'null':
    session_id_py = session_id_raw.strip()
else:
    session_id_py = None
```

**After**:
```python
from macacaMRIprep.utils.nextflow import normalize_session_id

session_id_raw = '${session_id}'
session_id_py = normalize_session_id(session_id_raw)
```

**Validation**: 
- Run synthesis with subject-level data (ses="")
- Run synthesis with session-level data (ses="001")
- Verify output filenames are correct

---

#### Step 1.1.4: Replace Groovy Code in channel_helpers.groovy

**File**: `workflows/channel_helpers.groovy`

**Locations**: 
- `performT2wAnatomicalSelection` (lines 178-179, 187-188, 196-197)
- `performFuncAnatomicalSelection` (lines 302-304, 311-313, 320-322)

**Before**:
```groovy
.filter { sub, ses, brain_file, bids_name -> 
    ses == "" || ses == null || (ses instanceof String && ses.toLowerCase() == 'null')
}
```

**After**:
```groovy
.filter { sub, ses, brain_file, bids_name -> 
    normalizeSessionId(ses) == null
}
```

**Validation**:
- Test T2w anatomical selection with subject-level T1w
- Test functional anatomical selection with subject-level T1w
- Verify correct priority matching

---

#### Step 1.1.5: Replace Groovy Code in anatomical_workflow.nf

**File**: `workflows/anatomical_workflow.nf`

**Locations**: Lines 860-862, 896-898

**Before**:
```groovy
def is_subject_level_anat = (anat_ses == "" || anat_ses == null || (anat_ses instanceof String && anat_ses.toLowerCase() == 'null'))
def is_subject_level_conform = (conform_ses == "" || conform_ses == null || (conform_ses instanceof String && conform_ses.toLowerCase() == 'null'))
```

**After**:
```groovy
def is_subject_level_anat = (normalizeSessionId(anat_ses) == null)
def is_subject_level_conform = (normalizeSessionId(conform_ses) == null)
```

**Note**: Need to import `normalizeSessionId` from channel_helpers:
```groovy
def normalizeSessionId = channelHelpers.normalizeSessionId
```

**Validation**:
- Test T2w apply conform with subject-level T1w
- Test T2w apply registration with subject-level T1w
- Verify transforms are applied correctly

---

### 1.2 Remove/Replace Debug Print Statements

**Goal**: Clean up production code by removing debug prints or converting to proper logging.

#### Step 1.2.1: Audit Debug Statements

**File**: `modules/anatomical.nf`

**Lines**: 86-144 (13 debug print statements)

**Action**: Review each debug statement:
- **Keep as logging**: Statements that provide useful diagnostic information
- **Remove**: Statements that are purely for development debugging

**Decision Matrix**:
| Line | Statement | Action | Reason |
|------|-----------|--------|--------|
| 86 | `session_id_raw from Nextflow` | Remove | Development only |
| 87 | `session_id_py (reused)` | Remove | Development only |
| 91 | `Before ses removal check` | Remove | Development only |
| 96 | `Removed 'ses' entity` | Keep as logging | Useful diagnostic |
| 98 | `'ses' not in entities` | Remove | Development only |
| 100 | `keeping 'ses' entity` | Remove | Development only |
| 103 | `Creating filename with entities` | Keep as logging | Useful diagnostic |
| 109 | `Created bids_output_filename` | Keep as logging | Useful diagnostic |
| 121 | `synthesized flag` | Remove | Development only |
| 133 | `Subject-level synthesis path` | Keep as logging | Useful diagnostic |
| 137 | `Session-level synthesis path` | Keep as logging | Useful diagnostic |
| 142 | `No synthesis, using original path` | Remove | Development only |
| 144 | `Final bids_name_for_downstream` | Remove | Development only |

---

#### Step 1.2.2: Replace with Logging

**File**: `modules/anatomical.nf`

**Action**: Replace selected debug prints with proper logging:

```python
from macacaMRIprep.utils.logging import get_logger

logger = get_logger(__name__)

# Replace debug prints with:
if 'ses' in entities:
    ses_value = entities['ses']
    del entities['ses']
    logger.debug(f"Removed 'ses' entity (value was '{ses_value}') for subject-level synthesis")

logger.debug(f"Creating BIDS filename with entities: {entities}")
logger.debug(f"Created BIDS output filename: {bids_output_filename}")

if is_subject_level:
    logger.debug(f"Subject-level synthesis path: {synthesized_path}")
else:
    logger.debug(f"Session-level synthesis path: {synthesized_path}")
```

**Validation**:
- Verify logs appear in command log files
- Verify log level can be controlled via config
- Test with different log levels

---

#### Step 1.2.3: Remove Unnecessary Debug Statements

**File**: `modules/anatomical.nf`

**Action**: Simply delete lines 86-87, 91, 98, 100, 121, 142, 144

**Validation**:
- Run synthesis workflow
- Verify no errors
- Verify output is correct

---

## Phase 2: Medium Priority Improvements

### 2.1 BIDS Filename Generation Refactoring

**Goal**: Extract complex BIDS filename generation logic to a reusable utility function.

#### Step 2.1.1: Create Utility Function

**File**: `macacaMRIprep/utils/bids.py`

**Action**: Add new function:

```python
def create_synthesized_bids_filename(
    original_file: Path,
    modality: str,
    is_subject_level: bool,
    synthesized: bool
) -> Tuple[str, str]:
    """
    Create BIDS filename and path for synthesized anatomical output.
    
    Args:
        original_file: Original anatomical file (for parsing entities)
        modality: Modality suffix (e.g., "T1w", "T2w")
        is_subject_level: True if subject-level synthesis, False if session-level
        synthesized: True if synthesis occurred, False if passthrough
        
    Returns:
        Tuple of (bids_filename, bids_path_for_downstream)
        - bids_filename: Just the filename (e.g., "sub-001_T1w.nii.gz")
        - bids_path_for_downstream: Full path for downstream steps
          (e.g., "sub-001/anat/sub-001_T1w.nii.gz" for subject-level)
    """
    from .bids import parse_bids_entities, create_bids_filename
    
    # Parse entities from original file
    entities = parse_bids_entities(original_file.name)
    
    # Remove 'run' entity for synthesized files
    if synthesized and 'run' in entities:
        del entities['run']
    
    # Remove 'ses' entity for subject-level synthesis
    if is_subject_level and 'ses' in entities:
        del entities['ses']
    
    # Generate filename
    bids_filename = create_bids_filename(
        entities=entities,
        suffix=modality,
        extension='.nii.gz'
    )
    
    # Generate path for downstream
    if synthesized and is_subject_level:
        subject_id = entities.get('sub', 'unknown')
        bids_path = f"sub-{subject_id}/anat/{bids_filename}"
    elif synthesized:
        bids_path = str(original_file.parent / bids_filename)
    else:
        bids_path = str(original_file)
    
    return bids_filename, bids_path
```

**Test Cases**:
1. Subject-level synthesis: `sub-001_ses-001_run-01_T1w.nii.gz` → `sub-001_T1w.nii.gz`, `sub-001/anat/sub-001_T1w.nii.gz`
2. Session-level synthesis: `sub-001_ses-001_run-01_T1w.nii.gz` → `sub-001_ses-001_T1w.nii.gz`, `sub-001/ses-001/anat/sub-001_ses-001_T1w.nii.gz`
3. Single file (no synthesis): `sub-001_ses-001_run-01_T1w.nii.gz` → original path unchanged

**Validation**: Add unit tests in `tests/utils/test_bids.py`

---

#### Step 2.1.2: Refactor ANAT_SYNTHESIS Process

**File**: `modules/anatomical.nf`

**Lines to Replace**: 77-148

**Before**: Complex inline logic (70+ lines)

**After**:
```python
from macacaMRIprep.utils.bids import create_synthesized_bids_filename
from macacaMRIprep.utils.nextflow import normalize_session_id

# ... existing code ...

# Check if synthesis occurred
synthesized = result.metadata.get("synthesized", False)

# Normalize session ID
session_id_py = normalize_session_id('${session_id}')
is_subject_level = (session_id_py is None)

# Generate BIDS filename and path
bids_output_filename, bids_name_for_downstream = create_synthesized_bids_filename(
    original_file=bids_name,
    modality=modality,
    is_subject_level=is_subject_level,
    synthesized=synthesized
)

# Use symlinks to avoid duplication
create_output_link(result.output_file, bids_output_filename)

# Write bids_name for downstream
with open('bids_name.txt', 'w') as f:
    f.write(bids_name_for_downstream)
```

**Validation**:
- Test subject-level synthesis
- Test session-level synthesis
- Test single file (no synthesis)
- Verify output filenames are correct
- Verify downstream steps receive correct paths

---

### 2.2 Channel Operations Helpers

**Goal**: Simplify complex `combine() + filter()` patterns for session matching.

#### Step 2.2.1: Create Session Matching Helper

**File**: `workflows/channel_helpers.groovy`

**Action**: Add helper function:

```groovy
/**
 * Match two session IDs, handling subject-level case (null/empty/"null").
 * 
 * @param ses1 First session ID
 * @param ses2 Second session ID
 * @return true if sessions match (including both being subject-level)
 */
def matchSessions = { ses1, ses2 ->
    def ses1_norm = normalizeSessionId(ses1)
    def ses2_norm = normalizeSessionId(ses2)
    return ses1_norm == ses2_norm
}
```

**Validation**: Test with various session ID combinations

---

#### Step 2.2.2: Refactor T2w Apply Conform

**File**: `workflows/anatomical_workflow.nf`

**Lines**: 856-863

**Before**:
```groovy
.filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
    def is_subject_level_anat = (anat_ses == "" || anat_ses == null || (anat_ses instanceof String && anat_ses.toLowerCase() == 'null'))
    def is_subject_level_conform = (conform_ses == "" || conform_ses == null || (conform_ses instanceof String && conform_ses.toLowerCase() == 'null'))
    (anat_ses == conform_ses) || (is_subject_level_anat && is_subject_level_conform)
}
```

**After**:
```groovy
.filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
    matchSessions(anat_ses, conform_ses)
}
```

**Validation**:
- Test T2w apply conform with subject-level T1w
- Test T2w apply conform with session-level T1w
- Verify transforms are applied correctly

---

#### Step 2.2.3: Refactor T2w Apply Registration

**File**: `workflows/anatomical_workflow.nf`

**Lines**: 892-899

**Before**: Similar complex filter logic

**After**: Use `matchSessions` helper

**Validation**: Same as Step 2.2.2

---

## Phase 3: Low Priority Improvements

### 3.1 Workflow Branching Helpers

**Goal**: Improve readability of workflow branching logic.

#### Step 3.1.1: Extract Branching Function

**File**: `workflows/channel_helpers.groovy`

**Action**: Add helper:

```groovy
/**
 * Categorize anatomical jobs by type.
 * 
 * @param anat_jobs_ch Channel with structure: [sub, ses, file_objects, needs_synth, suffix, needs_t1w_reg, synthesis_type]
 * @return Branch result with: t1w_synthesis, t2w_synthesis, t1w_single, t2w_single
 */
def categorizeAnatomicalJobs = { anat_jobs_ch ->
    anat_jobs_ch.branch {
        t1w_synthesis: it[3] == true && it[6] == "t1w"
        t2w_synthesis: it[3] == true && it[6] == "t2w"
        t1w_single: it[3] == false && it[4] == "T1w"
        t2w_single: it[3] == false && it[4] == "T2w"
    }
}
```

**Validation**: Test with various job types

---

### 3.2 Metadata Standardization

**Goal**: Standardize metadata structure across processes.

#### Step 3.2.1: Create Metadata Helper

**File**: `macacaMRIprep/utils/nextflow.py`

**Action**: Add function:

```python
def create_synthesis_metadata(
    synthesized: bool,
    num_runs: int,
    modality: str,
    synthesis_level: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create standardized synthesis metadata.
    
    Args:
        synthesized: Whether synthesis occurred
        num_runs: Number of input files
        modality: Modality (e.g., "T1w", "T2w")
        synthesis_level: "subject" or "session" (None if not synthesized)
        
    Returns:
        Standardized metadata dictionary
    """
    metadata = {
        "step": "anat_synthesis",
        "synthesized": synthesized,
        "num_runs": num_runs,
        "modality": modality
    }
    
    if synthesized and synthesis_level:
        metadata["synthesis_level"] = synthesis_level
    
    return metadata
```

**Validation**: Test metadata structure matches expectations

---

## Phase 4: Documentation Fixes

### 4.1 Fix Misleading Comment in Workflow

**File**: `workflows/anatomical_workflow.nf`

**Line**: 765

**Before**:
```groovy
// Priority: 1) Same session T1w, 2) Cross-session T1w, 3) No T1w (stop processing)
```

**After**:
```groovy
// Priority: 1) Subject-level T1w (ses="", HIGHEST PRIORITY), 2) Same session T1w, 3) Cross-session T1w, 4) No T1w (stop processing)
```

**Validation**: Comment matches actual implementation

---

## Testing Strategy

### Unit Tests

1. **Session ID Normalization**:
   - Test all edge cases (None, "", "null", whitespace)
   - Test valid session IDs
   - Test both Python and Groovy implementations

2. **BIDS Filename Generation**:
   - Test subject-level synthesis
   - Test session-level synthesis
   - Test single file (no synthesis)
   - Test with various entity combinations

3. **Session Matching**:
   - Test subject-level matching (both null)
   - Test same session matching
   - Test cross-session matching
   - Test mismatched sessions

### Integration Tests

1. **End-to-End Synthesis**:
   - Subject-level T1w synthesis
   - Session-level T1w synthesis
   - T2w synthesis
   - Single file passthrough

2. **T2w Workflow**:
   - T2w with subject-level T1w
   - T2w with same-session T1w
   - T2w with cross-session T1w
   - T2w without T1w

3. **Functional Workflow**:
   - Func with subject-level T1w (priority test)
   - Func with same-session T1w
   - Func with cross-session T1w
   - Func without T1w (dummy)

### Regression Tests

- Verify all existing tests still pass
- Test with real BIDS datasets
- Test with various synthesis configurations

---

## Implementation Timeline

### Week 1: High Priority
- Day 1-2: Session ID normalization utilities
- Day 3: Replace Python code
- Day 4: Replace Groovy code
- Day 5: Testing and validation

### Week 2: Medium Priority
- Day 1-2: BIDS filename generation refactoring
- Day 3: Channel operations helpers
- Day 4-5: Testing and validation

### Week 3: Low Priority & Documentation
- Day 1: Workflow branching helpers
- Day 2: Metadata standardization
- Day 3: Documentation fixes
- Day 4-5: Final testing and cleanup

---

## Risk Assessment

### Low Risk
- Session ID normalization (isolated utility functions)
- Debug print removal (no functional changes)
- Documentation fixes

### Medium Risk
- BIDS filename generation (affects output naming)
- Channel operations (affects workflow logic)

### Mitigation
- Comprehensive unit tests
- Integration tests with real data
- Incremental implementation with validation at each step
- Keep old code commented until validation complete

---

## Success Criteria

1. ✅ All code duplication eliminated
2. ✅ All debug statements removed or converted to logging
3. ✅ BIDS filename generation logic extracted and tested
4. ✅ Channel operations simplified and tested
5. ✅ All existing tests pass
6. ✅ Documentation is accurate and consistent
7. ✅ No functional changes (backward compatible)

---

## Rollback Plan

If issues arise:
1. Revert changes in reverse order (low → high priority)
2. Keep old code commented for quick rollback
3. Test each phase independently before moving to next
4. Maintain git branches for each phase

---

## Questions for Discussion

1. Should we create a shared utility module for Nextflow/Groovy helpers?
2. Are there performance concerns with the current `combine() + filter()` patterns?
3. Should debug prints be completely removed or kept as debug-level logging?
4. Do we need additional test datasets for validation?
