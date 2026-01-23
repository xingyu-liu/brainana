# Anatomical Synthesis Code Review & Improvement Plan

## Summary

After reviewing the anatomical synthesis code and its usage in T2w and functional workflows, I've identified several areas for potential improvement. This document outlines the findings and proposed changes.

## Current Architecture Strengths

1. **Clear separation of concerns**: Synthesis logic is well-isolated in `synthesis_multiple_anat.py`
2. **Flexible synthesis levels**: Supports both session-level and subject-level synthesis
3. **Proper BIDS compliance**: Correctly handles entity removal (run, ses) for synthesized outputs
4. **Robust error handling**: Good validation and fallback mechanisms

## Areas for Improvement

### 1. Session ID Handling (High Priority)

**Issue**: Repetitive code for handling session_id normalization across multiple files.

**Current Pattern** (repeated in multiple places):
```python
# Handle empty string, None, whitespace-only, and the string "null"
if session_id_raw and session_id_raw.strip() and session_id_raw.strip().lower() != 'null':
    session_id_py = session_id_raw.strip()
else:
    session_id_py = None
```

**Location**: 
- `modules/anatomical.nf` (lines 40-46, 92-100, 126-127)
- `workflows/channel_helpers.groovy` (lines 302-305, 311-314, 320-323)
- `workflows/anatomical_workflow.nf` (lines 860-862, 896-898)

**Proposed Solution**:
1. Create a utility function in `macacaMRIprep/utils/nextflow.py`:
   ```python
   def normalize_session_id(session_id_raw: str) -> Optional[str]:
       """Normalize session ID from Nextflow (handles None, empty, 'null' string)."""
       if not session_id_raw:
           return None
       session_id = session_id_raw.strip()
       if not session_id or session_id.lower() == 'null':
           return None
       return session_id
   ```

2. Create a Groovy helper function in `channel_helpers.groovy`:
   ```groovy
   def normalizeSessionId = { ses ->
       if (ses == null || ses == "" || (ses instanceof String && ses.toLowerCase() == 'null')) {
           return null
       }
       return ses
   }
   ```

**Impact**: Reduces code duplication, improves maintainability, ensures consistent behavior.

---

### 2. Debug Print Statements (Medium Priority)

**Issue**: Excessive debug print statements in production code.

**Location**: `modules/anatomical.nf` (lines 86-144)

**Current Code**:
```python
print(f"DEBUG: session_id_raw from Nextflow: {repr(session_id_raw)}", file=sys.stderr)
print(f"DEBUG: session_id_py (reused): {repr(session_id_py)}", file=sys.stderr)
# ... 11 more debug prints
```

**Proposed Solution**:
1. Replace debug prints with proper logging:
   ```python
   from macacaMRIprep.utils.logging import get_logger
   logger = get_logger(__name__)
   
   logger.debug(f"session_id_raw from Nextflow: {repr(session_id_raw)}")
   logger.debug(f"session_id_py (reused): {repr(session_id_py)}")
   ```

2. Or remove entirely if not needed for production.

**Impact**: Cleaner code, better control over log levels, easier debugging when needed.

---

### 3. BIDS Filename Generation Logic (Medium Priority)

**Issue**: Complex logic for determining output filename based on synthesis level.

**Location**: `modules/anatomical.nf` (lines 77-148)

**Current Flow**:
1. Parse entities from first file
2. Remove 'run' entity
3. Check if subject-level, remove 'ses' entity
4. Generate filename
5. Determine path for downstream (subject-level vs session-level)

**Proposed Solution**:
Extract to a dedicated function in `macacaMRIprep/utils/bids.py`:
```python
def create_synthesized_bids_filename(
    original_file: Path,
    modality: str,
    is_subject_level: bool,
    synthesized: bool
) -> Tuple[str, str]:
    """
    Create BIDS filename and path for synthesized anatomical output.
    
    Returns:
        (bids_filename, bids_path_for_downstream)
    """
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

**Impact**: Cleaner module code, reusable logic, easier testing.

---

### 4. Workflow Branching Logic (Low Priority)

**Issue**: Complex branching in `anatomical_workflow.nf` for T1w vs T2w synthesis.

**Location**: `workflows/anatomical_workflow.nf` (lines 186-256)

**Current Pattern**:
```groovy
anat_jobs_ch.branch {
    t1w_synthesis: it[3] == true && it[6] == "t1w"
    t2w_synthesis: it[3] == true && it[6] == "t2w"
    t1w_single: it[3] == false && it[4] == "T1w"
    t2w_single: it[3] == false && it[4] == "T2w"
}
```

**Proposed Solution**:
Extract to a helper function for clarity:
```groovy
def categorizeAnatomicalJobs = { anat_jobs_ch ->
    anat_jobs_ch.branch {
        t1w_synthesis: it[3] == true && it[6] == "t1w"
        t2w_synthesis: it[3] == true && it[6] == "t2w"
        t1w_single: it[3] == false && it[4] == "T1w"
        t2w_single: it[3] == false && it[4] == "T2w"
    }
}
```

**Impact**: Slight improvement in readability, but current code is acceptable.

---

### 5. Channel Operations for T2w Apply Phase (Medium Priority)

**Issue**: Complex `combine() + filter()` pattern for matching T2w with T1w transforms.

**Location**: `workflows/anatomical_workflow.nf` (lines 842-911)

**Current Pattern**:
```groovy
def t2w_for_apply_conform = t2w_after_reg_to_t1w
    .map { ... }
    .combine(anat_conform_data, by: 0)  // Combine by subject only
    .filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
        // Handle subject-level case
        def is_subject_level_anat = (anat_ses == "" || anat_ses == null || ...)
        def is_subject_level_conform = (conform_ses == "" || conform_ses == null || ...)
        (anat_ses == conform_ses) || (is_subject_level_anat && is_subject_level_conform)
    }
```

**Proposed Solution**:
Create a helper function for session matching:
```groovy
def matchSessions = { ses1, ses2 ->
    def normalize = { ses ->
        if (ses == null || ses == "" || (ses instanceof String && ses.toLowerCase() == 'null')) {
            return null
        }
        return ses
    }
    def ses1_norm = normalize(ses1)
    def ses2_norm = normalize(ses2)
    return ses1_norm == ses2_norm
}

// Then use:
.filter { sub, ses, t2w_file, t2w_bids_name, anat_ses, conform_ses, forward_xfm, reference ->
    matchSessions(anat_ses, conform_ses)
}
```

**Impact**: Reduces code duplication, improves readability.

---

### 6. Metadata Handling (Low Priority)

**Issue**: Metadata is saved in multiple places with similar structure.

**Location**: Multiple processes in `modules/anatomical.nf`

**Proposed Solution**:
Standardize metadata structure and create helper functions:
```python
def create_synthesis_metadata(
    synthesized: bool,
    num_runs: int,
    modality: str,
    session_level: str  # "subject" or "session"
) -> Dict[str, Any]:
    """Create standardized synthesis metadata."""
    return {
        "step": "anat_synthesis",
        "synthesized": synthesized,
        "num_runs": num_runs,
        "modality": modality,
        "synthesis_level": session_level
    }
```

**Impact**: Consistent metadata structure, easier parsing downstream.

---

## Implementation Priority

1. **High Priority** (Do First):
   - Session ID normalization utility functions
   - Remove/replace debug print statements

2. **Medium Priority** (Do Next):
   - BIDS filename generation refactoring
   - Channel operation helpers for session matching

3. **Low Priority** (Nice to Have):
   - Workflow branching helpers
   - Metadata standardization

## Testing Considerations

For each improvement:
1. **Session ID normalization**: Test with None, "", "null", "  null  ", valid session IDs
2. **BIDS filename generation**: Test subject-level, session-level, single file cases
3. **Channel operations**: Test with multiple T2w sessions referencing same T1w session
4. **Metadata**: Verify downstream processes can still parse metadata correctly

## Backward Compatibility

All proposed changes maintain backward compatibility:
- No changes to channel structures
- No changes to file naming conventions
- No changes to workflow logic (only refactoring)

## Estimated Effort

- High priority items: 2-3 hours
- Medium priority items: 3-4 hours
- Low priority items: 1-2 hours
- Testing: 2-3 hours

**Total**: ~8-12 hours

## Questions for Discussion

1. Should debug prints be removed entirely or converted to proper logging?
2. Are there any performance concerns with the current `combine() + filter()` patterns?
3. Should we create a shared utility module for Nextflow/Groovy helpers?
4. Are there any edge cases in session matching that need special handling?
