# FUNC_REGISTRATION Input Source Analysis

## Summary

This document traces the complete data flow leading to `FUNC_REGISTRATION` process input, identifying all transformation points and potential issues.

---

## FUNC_REGISTRATION Process Input Structure

**Process Definition** (line 717-728 in `modules/functional.nf`):
```groovy
input:
// Combined channel: [sub, ses, task, run, func_file, bids_naming_template, anat_reg, anat_trans, anat_ses, is_fallback]
tuple val(subject_id), val(session_id), val(task_name), val(run), 
      path(input_file), 
      val(bids_naming_template), 
      path(anat_registered), 
      path(anat_transforms), 
      val(anat_session_id), 
      val(is_fallback)
path config_file
```

**Expected Input**: 10-element tuple + config_file
- Elements: `[sub, ses, task, run, func_file, bids_naming_template, anat_reg, anat_trans, anat_ses, is_fallback]`

---

## Data Flow Trace

### 1. Initial Channel: `func_jobs_ch`
**Structure**: `[sub, ses, task, run, file, bids_naming_template]` (6 elements)
- Source: BIDS discovery output
- Passed through: `passThroughFunc` helper when steps are disabled

### 2. Pre-Processing Steps (Lines 622-676)
All steps maintain 6-element structure: `[sub, ses, task, run, file, bids_naming_template]`

- **SLICE_TIMING** → `func_after_slice`
- **REORIENT** → `func_after_reorient`  
- **MOTION_CORRECTION** → `func_after_motion` (also outputs `func_motion_tmean`)
- **DESPIKE** → `func_after_despike` (also outputs `func_despike_tmean`)
- **BIAS_CORRECTION** → `func_after_bias` (operates on tmean, not 4D BOLD)

**Key Point**: `func_after_bias` contains **tmean** files, not 4D BOLD.

### 3. CONFORM Step (Lines 678-717)

**Input to FUNC_CONFORM** (line 704-709):
```groovy
// func_tmean_and_bold: [sub, ses, task, run, tmean_file, bold_4d_file, func_bids_template] (7 elements)
// Combined with anat_brain_for_func by [0,1] → creates 9-element tuple
// Then mapped to: [sub, ses, task, run, tmean_file, bold_4d_file, func_bids_template, anat_file] (8 elements)
```

**FUNC_CONFORM Outputs** (line 502-506):
- `FUNC_CONFORM.out.output`: `[sub, ses, task, run, conformed_4d_bold, bids_naming_template]` (6 elements) - **4D BOLD**
- `FUNC_CONFORM.out.tmean`: `[sub, ses, task, run, conformed_tmean, bids_naming_template]` (6 elements) - **tmean**
- `FUNC_CONFORM.out.transforms`: transform files
- `FUNC_CONFORM.out.template_resampled`: template file

**Channel Assignment** (line 712):
```groovy
func_after_conform = FUNC_CONFORM.out.output  // This is the conformed 4D BOLD
```

**⚠️ ISSUE**: `func_after_conform` contains **4D BOLD**, but later code sometimes expects **tmean**.

**If CONFORM disabled** (line 716):
```groovy
func_after_conform = func_after_despike.map(passThroughFunc)  // Use 4D BOLD, not tmean
```

### 4. SKULLSTRIPPING Step (Lines 719-734)

**Input to FUNC_SKULLSTRIPPING** (line 725):
```groovy
def func_conformed_tmean = func_conform_enabled ? FUNC_CONFORM.out.tmean : func_after_bias
FUNC_SKULLSTRIPPING(func_conformed_tmean, config_file)
```

**FUNC_SKULLSTRIPPING Outputs** (line 644-645):
- `FUNC_SKULLSTRIPPING.out.brain_mask`: `[sub, ses, task, run, mask_file, bids_naming_template]` (6 elements)
- `FUNC_SKULLSTRIPPING.out.brain`: `[sub, ses, task, run, brain_file, bids_naming_template]` (6 elements)

**Channel Assignment** (lines 727-730):
```groovy
func_skull_mask = FUNC_SKULLSTRIPPING.out.brain_mask
func_skull_brain = FUNC_SKULLSTRIPPING.out.brain
func_after_skull = func_skull_brain  // ⚠️ Uses brain from skullstripping
```

**If SKULLSTRIPPING disabled** (line 733):
```groovy
func_after_skull = func_conform_enabled ? FUNC_CONFORM.out.tmean : func_after_bias
```

**⚠️ CRITICAL ISSUE**: 
- When skullstripping **enabled**: `func_after_skull` = `func_skull_brain` (skull-stripped brain)
- When skullstripping **disabled**: `func_after_skull` = `FUNC_CONFORM.out.tmean` OR `func_after_bias` (tmean, not brain)

**Structure**: `func_after_skull` = `[sub, ses, task, run, processed_file, bids_naming_template]` (6 elements)

### 5. Registration Join Logic (Lines 736-804)

#### 5.1 Anatomical Channel Preparation (Lines 740-769)

**anat_reg_ch** (lines 740-744):
```groovy
def anat_reg_ch = anat_after_reg
    .join(anat_reg_transforms, by: [0, 1])
    .map { sub, ses, anat_file, trans -> 
        [sub, ses, anat_file, trans]  // 4 elements
    }
```

**anat_by_subject** (lines 755-769):
- Groups anatomical data by subject
- Takes first session (sorted)
- Output: `[sub, ses, reg_file, trans]` (4 elements)

#### 5.2 Exact Match Join (Lines 780-785)

```groovy
def func_anat_exact = func_after_skull
    .join(anat_reg_ch, by: [0, 1])  // Join by [subject_id, session_id]
    .map { sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans ->
        [sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses, false]
        //                                                                                    ^^^^  ^^^^^^
        //                                                                                    anat_ses, is_fallback
    }
```

**Input**: 
- `func_after_skull`: `[sub, ses, task, run, processed_file, bids_naming_template]` (6 elements)
- `anat_reg_ch`: `[sub, ses, anat_file, trans]` (4 elements)

**Join Result**: `[sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans]` (8 elements)

**Output**: `[sub, ses, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses, false]` (10 elements) ✅

#### 5.3 Fallback Join (Lines 789-798)

```groovy
def func_anat_fallback = func_after_skull
    .combine(anat_by_subject, by: 0)  // Combine by subject_id only
    .filter { sub, ses_func, task, run, processed_file, bids_naming_template, ses_anat, anat_reg, anat_trans ->
        ses_func != ses_anat  // Only keep if sessions don't match
    }
    .map { sub, ses_func, task, run, processed_file, bids_naming_template, ses_anat, anat_reg, anat_trans ->
        [sub, ses_func, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses_anat, true]
        //                                                                                                    ^^^^
        //                                                                                                    is_fallback=true
    }
```

**Input**:
- `func_after_skull`: `[sub, ses, task, run, processed_file, bids_naming_template]` (6 elements)
- `anat_by_subject`: `[sub, ses, reg_file, trans]` (4 elements)

**Combine Result**: `[sub, ses_func, task, run, processed_file, bids_naming_template, ses_anat, anat_reg, anat_trans]` (9 elements)

**Output**: `[sub, ses_func, task, run, processed_file, bids_naming_template, anat_reg, anat_trans, ses_anat, true]` (10 elements) ✅

#### 5.4 Final Join (Lines 801-804)

```groovy
def func_anat_joined = func_anat_exact
    .mix(func_anat_fallback)

FUNC_REGISTRATION(func_anat_joined, config_file)
```

**Final Input to FUNC_REGISTRATION**: 10-element tuple ✅

---

## Issues Identified

### Issue 1: Inconsistent `func_after_skull` Content
**Location**: Lines 719-734

**Problem**: 
- When skullstripping **enabled**: `func_after_skull` = skull-stripped **brain**
- When skullstripping **disabled**: `func_after_skull` = **tmean** (not brain)

This inconsistency means `func_after_skull` doesn't always contain the same type of file, which could cause confusion.

**Impact**: Medium - The registration process should handle both, but the naming is misleading.

### Issue 2: `func_after_conform` Contains 4D BOLD, Not tmean
**Location**: Line 712

**Problem**:
```groovy
func_after_conform = FUNC_CONFORM.out.output  // This is the conformed 4D BOLD
```

But later (line 725), when skullstripping is enabled:
```groovy
def func_conformed_tmean = func_conform_enabled ? FUNC_CONFORM.out.tmean : func_after_bias
```

The code correctly uses `FUNC_CONFORM.out.tmean` for skullstripping, but `func_after_conform` is set to the 4D BOLD output. This is fine for the 4D BOLD pipeline, but the variable name is misleading.

**Impact**: Low - The code correctly uses separate channels, but naming could be clearer.

### Issue 3: Complex Conditional Logic
**Location**: Lines 719-734, 771-810

**Problem**: Multiple nested conditionals create different code paths:
- CONFORM enabled/disabled
- SKULLSTRIPPING enabled/disabled  
- REGISTRATION enabled/disabled

Each combination creates a different data flow, making it hard to track what `func_after_skull` contains in each case.

**Impact**: High - This complexity makes debugging difficult and increases risk of bugs.

### Issue 4: Join Logic Complexity
**Location**: Lines 780-798

**Problem**: Two separate join operations (exact match + fallback) that are then mixed. The fallback logic uses `combine` which creates a cartesian product, then filters. This could be inefficient and error-prone.

**Impact**: Medium - Works but could be simplified.

---

## Recommendations

1. **Clarify Variable Names**: 
   - Rename `func_after_skull` to `func_for_registration` or `func_tmean_for_registration`
   - Consider separate channels for tmean vs 4D BOLD

2. **Simplify Conditional Logic**:
   - Extract the `func_after_skull` assignment into a helper function
   - Document all possible paths clearly

3. **Consolidate Join Logic**:
   - Consider using a single join operation with better fallback handling
   - Or clearly separate the exact-match and fallback cases

4. **Add Validation**:
   - Add assertions to verify channel structure at key points
   - Log the actual file type being used for registration

---

## Channel Structure Summary

| Channel | Structure | Elements | Content Type |
|---------|-----------|----------|--------------|
| `func_jobs_ch` | `[sub, ses, task, run, file, bids_template]` | 6 | Initial BOLD |
| `func_after_bias` | `[sub, ses, task, run, file, bids_template]` | 6 | **tmean** |
| `func_after_conform` | `[sub, ses, task, run, file, bids_template]` | 6 | **4D BOLD** |
| `FUNC_CONFORM.out.tmean` | `[sub, ses, task, run, file, bids_template]` | 6 | **tmean** |
| `func_skull_brain` | `[sub, ses, task, run, file, bids_template]` | 6 | **brain** |
| `func_after_skull` | `[sub, ses, task, run, file, bids_template]` | 6 | **brain** OR **tmean** (inconsistent!) |
| `func_anat_exact` | `[sub, ses, task, run, file, bids_template, anat_reg, anat_trans, anat_ses, is_fallback]` | 10 | Ready for registration |
| `func_anat_fallback` | `[sub, ses, task, run, file, bids_template, anat_reg, anat_trans, anat_ses, is_fallback]` | 10 | Ready for registration |
| `func_anat_joined` | `[sub, ses, task, run, file, bids_template, anat_reg, anat_trans, anat_ses, is_fallback]` | 10 | **FUNC_REGISTRATION input** ✅ |

---

## Conclusion

The input flow to `FUNC_REGISTRATION` is **functionally correct** but **complex and error-prone** due to:
1. Multiple conditional paths
2. Inconsistent variable naming
3. Mixed content types in the same channel (`func_after_skull`)
4. Complex join logic with fallback handling

The final 10-element tuple structure is correct, but the path to get there involves many transformations that could be simplified and better documented.

