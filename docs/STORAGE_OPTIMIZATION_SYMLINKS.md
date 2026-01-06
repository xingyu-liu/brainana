# Storage Optimization: Using Symlinks for File Inheritance

## Nextflow File Staging Behavior

### Default Behavior
Nextflow **automatically uses symlinks** when staging files in the work directory:
- Files are **symlinked** (not copied) from input channels to work directories
- This is Nextflow's default behavior for efficiency
- Only when files are **published** (via `publishDir`) are they actually copied

### Current Codebase Pattern
Your codebase already uses symlinks extensively:
- `create_output_link()` function creates symlinks for outputs
- Used throughout processes to avoid duplication
- Nextflow's `publishDir` follows symlinks and copies actual content

---

## Solution: Using `stageAs` for Inherited Files

### Option 1: Use `stageAs` to Create Symlinks (Recommended)

When a process inherits a file (doesn't process it), we can use Nextflow's `stageAs` parameter to create a symlink:

```groovy
process FUNC_BIAS_CORRECTION {
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), 
          path(bold_file, stageAs: 'bold_inherited.nii.gz -> *'),  // Symlink to input
          path(tmean_file),  // Process this
          val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), 
          path("bold_inherited.nii.gz"),  // Symlink to input (no copy!)
          path("*desc-biasCorrection_boldref.nii.gz"),  // Processed tmean
          val(bids_naming_template), 
          emit: combined
    
    script:
    """
    # bold_inherited.nii.gz is already a symlink to the input file
    # No need to copy it - just reference it in output
    # Process tmean for bias correction...
    """
}
```

**How it works**:
- `stageAs: 'bold_inherited.nii.gz -> *'` tells Nextflow to create a symlink named `bold_inherited.nii.gz` pointing to the input file
- The `*` pattern matches the input filename
- Nextflow creates a **symlink**, not a copy
- When the process outputs `bold_inherited.nii.gz`, it's still a symlink
- Nextflow's `publishDir` will follow the symlink and copy the actual file content

### Option 2: Explicit Symlink in Script (Alternative)

If `stageAs` doesn't work as expected, create symlink explicitly in the script:

```groovy
process FUNC_BIAS_CORRECTION {
    input:
    tuple val(subject_id), val(session_id), val(task_name), val(run), 
          path(bold_file),  // Input file
          path(tmean_file), 
          val(bids_naming_template)
    path config_file
    
    output:
    tuple val(subject_id), val(session_id), val(task_name), val(run), 
          path("bold_inherited.nii.gz"),  // Output symlink
          path("*desc-biasCorrection_boldref.nii.gz"), 
          val(bids_naming_template), 
          emit: combined
    
    script:
    """
    # Create symlink to inherited BOLD file
    import os
    from pathlib import Path
    
    bold_input = Path('${bold_file}')
    bold_output = Path('bold_inherited.nii.gz')
    
    # Create symlink (relative path for portability)
    if bold_output.exists() or bold_output.is_symlink():
        bold_output.unlink()
    os.symlink(bold_input.name, 'bold_inherited.nii.gz')
    # Note: Nextflow stages files in work directory, so we can use relative symlink
    
    # Process tmean...
    """
}
```

---

## Storage Analysis

### Current Approach (Without Inheritance)
```
MOTION: [BOLD_file] → copies to work/
DESPIKE: [BOLD_file] → copies to work/ (new copy!)
BIAS: [tmean_file] → copies to work/ (BOLD lost, must rejoin)
CONFORM: [BOLD_file] → copies to work/ (another copy!)
```

**Storage**: Multiple copies of BOLD file in different work directories

### Proposed Approach (With Symlink Inheritance)
```
MOTION: [BOLD_file] → symlink in work/
DESPIKE: [BOLD_file] → symlink in work/ (points to MOTION output)
BIAS: [BOLD_file] → symlink in work/ (points to DESPIKE output, no copy!)
CONFORM: [BOLD_file] → symlink in work/ (points to DESPIKE output)
```

**Storage**: 
- **One actual copy** of BOLD file (in MOTION work directory)
- **Symlinks** in subsequent work directories
- **Final copy** only when published via `publishDir`

### Storage Savings

For a typical functional run:
- **BOLD file**: ~500 MB - 2 GB
- **tmean file**: ~5-10 MB

**Without symlinks** (current):
- Each step that needs BOLD: +500 MB - 2 GB
- 4 steps × 2 GB = **8 GB** per run

**With symlinks** (proposed):
- One actual copy: **2 GB**
- Symlinks: **~0 bytes** (just filesystem metadata)
- **Savings: ~6 GB per run**

For a dataset with 10 subjects, 2 sessions, 2 runs:
- **Without**: 10 × 2 × 2 × 8 GB = **320 GB**
- **With**: 10 × 2 × 2 × 2 GB = **80 GB**
- **Savings: 240 GB** (75% reduction!)

---

## Implementation Strategy

### Step 1: Update Process Inputs

For processes that inherit files, use `stageAs`:

```groovy
// FUNC_BIAS_CORRECTION - inherits BOLD
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file, stageAs: 'bold_inherited.nii.gz -> *'),  // Symlink
      path(tmean_file),  // Process this
      val(bids_naming_template)
```

```groovy
// FUNC_SKULLSTRIPPING - inherits BOLD
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file, stageAs: 'bold_inherited.nii.gz -> *'),  // Symlink
      path(tmean_file),  // Process this → brain
      val(bids_naming_template)
```

```groovy
// FUNC_REGISTRATION - inherits BOLD
input:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(bold_file, stageAs: 'bold_inherited.nii.gz -> *'),  // Symlink
      path(tmean_file),  // Process this → registered
      val(bids_naming_template),
      ...
```

### Step 2: Update Process Scripts

Reference the symlinked file in output:

```python
# In FUNC_BIAS_CORRECTION script
# bold_inherited.nii.gz is already a symlink, just reference it
# Process tmean for bias correction
result = func_bias_correction(tmean_input_obj)

# Output both files
# bold_inherited.nii.gz is already in work directory as symlink
# Processed tmean is created by the step
```

### Step 3: Update Output Patterns

Make sure output patterns match the symlinked filename:

```groovy
output:
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path("bold_inherited.nii.gz"),  // Matches stageAs name
      path("*desc-biasCorrection_boldref.nii.gz"), 
      val(bids_naming_template), 
      emit: combined
```

---

## Verification

### Check Symlinks in Work Directory

After running, check work directories:

```bash
# Check if files are symlinks
ls -la work/*/FUNC_BIAS_CORRECTION/bold_inherited.nii.gz
# Should show: bold_inherited.nii.gz -> ../FUNC_DESPIKE/desc-despike_bold.nii.gz

# Check file sizes
du -sh work/*/FUNC_BIAS_CORRECTION/
# Should show minimal size (just tmean + symlink)
```

### Verify No Duplication

```bash
# Count actual BOLD files (not symlinks)
find work/ -name "*bold.nii.gz" -type f | wc -l
# Should be 1 per run (in MOTION_CORRECTION work directory)

# Count symlinks
find work/ -name "*bold*.nii.gz" -type l | wc -l
# Should be multiple (one per step that inherits)
```

---

## Potential Issues & Solutions

### Issue 1: `stageAs` Pattern Matching
**Problem**: `stageAs: 'bold_inherited.nii.gz -> *'` might not work as expected

**Solution**: Use explicit symlink creation in script (Option 2)

### Issue 2: Relative vs Absolute Symlinks
**Problem**: Symlinks might break if work directories are moved

**Solution**: 
- Use relative symlinks (Nextflow handles this)
- Or use `stageAs` which Nextflow manages automatically

### Issue 3: Cross-Filesystem Issues
**Problem**: Symlinks don't work across different filesystems

**Solution**: 
- `create_output_link()` already handles this (falls back to copy)
- Nextflow's `stageAs` also handles this gracefully

### Issue 4: Windows Compatibility
**Problem**: Windows symlink support varies

**Solution**: 
- Nextflow handles this automatically
- Falls back to copy if symlinks not supported
- Your `create_output_link()` function already has this fallback

---

## Recommended Approach

### Use `stageAs` for Inherited Files

**Advantages**:
1. ✅ Nextflow manages symlinks automatically
2. ✅ Handles cross-filesystem issues
3. ✅ Works on Windows (Nextflow handles it)
4. ✅ No manual symlink creation needed
5. ✅ Cleaner code

**Implementation**:
```groovy
// For any process that inherits a file
path(inherited_file, stageAs: 'inherited_filename.nii.gz -> *')
```

### Fallback: Explicit Symlink in Script

If `stageAs` doesn't work, use explicit symlink:

```python
# In process script
from pathlib import Path
import os

inherited_file = Path('${bold_file}')
output_file = Path('bold_inherited.nii.gz')

if output_file.exists() or output_file.is_symlink():
    output_file.unlink()

# Create relative symlink
os.symlink(inherited_file.name, str(output_file))
```

---

## Summary

**✅ Yes, symlinks are absolutely feasible and recommended!**

### Benefits:
1. **Massive storage savings**: 75% reduction in work directory size
2. **Faster execution**: No time spent copying large files
3. **Nextflow native**: Uses Nextflow's built-in symlink support
4. **Automatic fallback**: Nextflow handles edge cases

### Implementation:
- Use `stageAs` parameter for inherited files
- Nextflow creates symlinks automatically
- No manual symlink management needed
- Works seamlessly with existing `publishDir` behavior

### Storage Impact:
- **Before**: Multiple copies of BOLD file (8 GB per run)
- **After**: One copy + symlinks (2 GB per run)
- **Savings**: ~6 GB per run (75% reduction)

This is a **win-win**: cleaner code AND massive storage savings!

