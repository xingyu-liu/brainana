# Transform Application and Interpolation Summary

This document summarizes all cases where transformations (xfm) are applied in the banana pipeline and what interpolation methods are used.

## Overview

The pipeline uses two main transformation tools:
1. **ANTs** (`antsApplyTransforms`) - for non-linear and composite transforms
2. **FLIRT** (`flirt -applyxfm`) - for affine/linear transforms

## Interpolation Methods Used

### ANTs Interpolation Options
- `LanczosWindowedSinc` - High-quality interpolation (for continuous-value anatomical and functional images)
- `trilinear` - Trilinear interpolation (for FLIRT transforms on continuous-value images)
- `NearestNeighbor` - For binary masks and discrete labels/parcellations

### FLIRT Interpolation Options
- `trilinear` - Trilinear interpolation (default for FLIRT)

---

## 1. ANATOMICAL PROCESSING

### 1.1 T1w Registration to Template
**Location:** `modules/anatomical.nf` (ANAT_REGISTRATION, line ~707)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `'LanczosWindowedSinc'`
- **Use Case:** Apply registration transform to unskullstripped T1w (when skullstripping is enabled)
- **Note:** Transform is computed on skullstripped version but applied to unskullstripped version. Uses high-quality interpolation for continuous-value anatomical images.

### 1.2 T2w to T1w Registration
**Location:** `macacaMRIprep/steps/anatomical.py` (anat_t2w_to_t1w_registration, line ~329)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply rigid transform to register T2w to T1w space

### 1.3 T2w Apply Conform Transform
**Location:** `modules/anatomical.nf` (ANAT_APPLY_CONFORM, line ~1204)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply conform transform to T2w images

### 1.4 T2w Apply Registration Transform
**Location:** `modules/anatomical.nf` (ANAT_APPLY_TRANSFORMATION, line ~1374)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `'LanczosWindowedSinc'`
- **Use Case:** Apply T1w's registration transform to T2w (to template space)
- **Note:** Uses high-quality interpolation for continuous-value anatomical images.

### 1.5 Anatomical Mask Transformation
**Location:** `modules/anatomical.nf` (ANAT_APPLY_TRANSFORM_MASK, line ~1469)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `'NearestNeighbor'`
- **Use Case:** Transform brain mask to template space (preserves binary values)
- **Note:** NearestNeighbor is essential for binary masks to avoid interpolation artifacts

---

## 2. FUNCTIONAL PROCESSING

### 2.1 BOLD Apply Conform Transform
**Location:** `modules/functional.nf` (FUNC_APPLY_CONFORM, line ~863)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply conform transform to 4D BOLD timeseries

### 2.2 BOLD Apply Conform Transform (Python)
**Location:** `macacaMRIprep/steps/functional.py` (func_conform, line ~331)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply conform transform to full 4D BOLD when conform is enabled

### 2.3 BOLD Within-Session Coregistration (tmean)
**Location:** `macacaMRIprep/steps/functional.py` (func_within_ses_coreg, line ~640)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply within-session coregistration transform to tmean

### 2.4 BOLD Within-Session Coregistration (4D BOLD)
**Location:** `macacaMRIprep/steps/functional.py` (func_within_ses_coreg, line ~661)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply within-session coregistration transform to full 4D BOLD

### 2.5 BOLD Apply Registration (func2anat)
**Location:** `modules/functional.nf` (FUNC_APPLY_REGISTRATION, line ~1534)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `config.get("registration", {}).get("interpolation", "LanczosWindowedSinc")`
- **Default:** `"LanczosWindowedSinc"`
- **Use Case:** Apply func2anat transform to 4D BOLD (moving_type=3, time series)
- **Note:** Uses configurable interpolation, defaults to LanczosWindowedSinc for high-quality functional data

### 2.6 BOLD Apply Registration (anat2template)
**Location:** `modules/functional.nf` (FUNC_APPLY_REGISTRATION, line ~1585)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `config.get("registration", {}).get("interpolation", "LanczosWindowedSinc")`
- **Default:** `"LanczosWindowedSinc"`
- **Use Case:** Apply anat2template transform to 4D BOLD in anatomical space (moving_type=3, time series)
- **Note:** Uses configurable interpolation, defaults to LanczosWindowedSinc

### 2.7 Functional Mask Transformation
**Location:** `modules/functional.nf` (FUNC_APPLY_MASK_TRANSFORM, line ~1816)
- **Tool:** ANTs (`ants_apply_transforms`)
- **Interpolation:** `'NearestNeighbor'`
- **Use Case:** Transform functional brain mask to template space (preserves binary values)
- **Note:** NearestNeighbor is essential for binary masks

---

## 3. PREPROCESSING OPERATIONS

### 3.1 Conform to Template
**Location:** `macacaMRIprep/operations/preprocessing.py` (conform_to_template, line ~556)
- **Tool:** FLIRT (`flirt_apply_transforms`)
- **Interpolation:** `'trilinear'`
- **Use Case:** Apply conform transform during preprocessing

---

## 4. TRANSFORM COMPUTATION (NOT APPLICATION)

### 4.1 ANTs Registration (Transform Computation)
**Location:** `macacaMRIprep/operations/registration.py` (ants_register, line ~108)
- **Tool:** ANTs (`antsRegistration`)
- **Interpolation:** `config.get('interpolation', 'Linear')`
- **Default:** `'Linear'`
- **Use Case:** Compute registration transform (not applying, but setting interpolation for registration process)
- **Note:** This is for the registration process itself, not for applying transforms

---

## 5. RESAMPLING OPERATIONS (Not Transform Application)

### 5.1 3dresample for Resolution Matching
**Location:** `modules/functional.nf` (FUNC_APPLY_REGISTRATION, lines ~1520, 1572)
- **Tool:** AFNI (`3dresample`)
- **Interpolation:** `-rmode Cu` (cubic interpolation)
- **Use Case:** Resample reference images to functional resolution before applying transforms
- **Note:** This is resampling, not transform application

---

## Summary Table

| Use Case | Tool | Interpolation | Location | Notes |
|----------|------|---------------|----------|-------|
| T1w registration (unskullstripped) | ANTs | `LanczosWindowedSinc` | `modules/anatomical.nf:707` | Applied to unskullstripped version, continuous values |
| T2w→T1w registration | FLIRT | `trilinear` | `steps/anatomical.py:329` | Rigid transform, continuous values |
| T2w apply conform | FLIRT | `trilinear` | `modules/anatomical.nf:1204` | Conform transform, continuous values |
| T2w apply registration | ANTs | `LanczosWindowedSinc` | `modules/anatomical.nf:1374` | To template space, continuous values |
| Anatomical mask transform | ANTs | `NearestNeighbor` | `modules/anatomical.nf:1469` | Binary mask |
| BOLD apply conform | FLIRT | `trilinear` | `modules/functional.nf:863` | Conform transform |
| BOLD apply conform (Python) | FLIRT | `trilinear` | `steps/functional.py:331` | Conform transform |
| BOLD within-session coreg | FLIRT | `trilinear` | `steps/functional.py:640,661` | tmean and 4D BOLD |
| BOLD func2anat | ANTs | `LanczosWindowedSinc`* | `modules/functional.nf:1534` | Configurable, default Lanczos |
| BOLD anat2template | ANTs | `LanczosWindowedSinc`* | `modules/functional.nf:1585` | Configurable, default Lanczos |
| Functional mask transform | ANTs | `NearestNeighbor` | `modules/functional.nf:1816` | Binary mask |
| Conform preprocessing | FLIRT | `trilinear` | `operations/preprocessing.py:556` | Preprocessing step |

*Configurable via `config.registration.interpolation`, defaults to `LanczosWindowedSinc`

---

## Key Patterns

1. **Continuous-Value Anatomical Images (T1w, T2w):**
   - ANTs transforms: `LanczosWindowedSinc` interpolation (high-quality)
   - FLIRT transforms: `trilinear` interpolation

2. **Continuous-Value Functional Images (BOLD):**
   - ANTs transforms: `LanczosWindowedSinc` (configurable, high-quality default)
   - FLIRT transforms: `trilinear` interpolation

3. **Discrete-Value Data (Masks, Parcellations, Labels):**
   - Always: `NearestNeighbor` interpolation (preserves discrete/binary values)

4. **Default Configuration:**
   - Functional registration interpolation: `LanczosWindowedSinc` (in `defaults.yaml`)
   - Anatomical registration interpolation: `LanczosWindowedSinc` (for continuous-value images)

---

## Recommendations

1. **For continuous-value anatomical images (T1w, T2w):** 
   - Use `LanczosWindowedSinc` for ANTs transforms (high-quality interpolation)
   - Use `trilinear` for FLIRT transforms (standard for continuous data)

2. **For continuous-value functional images (BOLD):**
   - Use `LanczosWindowedSinc` for ANTs transforms (high-quality interpolation for time series)
   - Use `trilinear` for FLIRT transforms (standard for continuous data)

3. **For discrete-value data (masks, parcellations, labels):**
   - Always use `NearestNeighbor` to preserve binary/discrete values and avoid interpolation artifacts

4. **General Rule:**
   - Continuous values → `LanczosWindowedSinc` (ANTs) or `trilinear` (FLIRT)
   - Discrete values → `NearestNeighbor` (both tools)

---

## Configuration

The interpolation method for functional data registration can be configured in:
- `macacaMRIprep/config/defaults.yaml`: `registration.interpolation` (default: `"LanczosWindowedSinc"`)
- Valid options: `"Linear"`, `"NearestNeighbor"`, `"MultiLabel"`, `"Gaussian"`, `"BSpline"`, `"CosineWindowedSinc"`, `"WelchWindowedSinc"`, `"HammingWindowedSinc"`, `"LanczosWindowedSinc"`, `"GenericLabel"`
