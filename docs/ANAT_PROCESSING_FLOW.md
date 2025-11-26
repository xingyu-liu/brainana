# Anatomical Processing Flow and File Management

## Processing Pipeline Flowchart

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUT: Original Anatomical File                  │
│                         (self.anat_file)                                 │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  1. ANAT PRECHECK     │
                    │  - Reorientation      │
                    │  (if template provided)│
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  2. BIAS CORRECTION  │
                    │  (if enabled)        │
                    │  Input: anatf_cur    │
                    │  Output: anat_bias_corrected.nii.gz │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Save to output_dir: │
                    │  desc-preproc_T1w.nii.gz │
                    │  (anatf_cur)         │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  3. SKULL STRIPPING  │
                    │  Input: anatf_cur    │
                    │  (bias-corrected)    │
                    │                      │
                    │  FastSurferCNN:      │
                    │  - Pass 1: Full image│
                    │  - Check if refinement│
                    │    needed            │
                    └──────────┬───────────┘
                               │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌──────────────────────┐
        │  NO TWO-PASS      │   │  TWO-PASS REFINEMENT  │
        │  (Normal case)    │   │  (Brain < 20% FOV)    │
        │                   │   │                      │
        │  Outputs:         │   │  Step 1: Move pass_1 │
        │  - brain_mask     │   │    outputs to pass_1/│
        │  - skullstripped  │   │                      │
        │  - segmentation   │   │  Step 2: Crop input  │
        │  - hemimask       │   │    (bias-corrected) │
        │                   │   │    → input_cropped   │
        └───────────┬───────┘   │                      │
                    │           │  Step 3: Run pass 2  │
                    │           │    on cropped image  │
                    │           │                      │
                    │           │  Outputs:            │
                    │           │  - brain_mask        │
                    │           │  - skullstripped     │
                    │           │  - segmentation      │
                    │           │  - hemimask          │
                    │           │  - input_cropped     │
                    │           └──────────┬───────────┘
                    │                      │
                    └───────────┬──────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  HANDLE input_cropped│
                    │  (if exists)         │
                    │                      │
                    │  - Rename desc-preproc│
                    │    → desc-preprocOrigSize│
                    │  - Copy input_cropped│
                    │    → desc-preproc    │
                    │  (input_cropped is   │
                    │   already bias-      │
                    │   corrected!)        │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  4. REGISTRATION     │
                    │  (if enabled & not   │
                    │   native space)      │
                    │                      │
                    │  Input: anatf_cur    │
                    │  (skull-stripped,   │
                    │   in cropped space  │
                    │   if two-pass used)  │
                    │                      │
                    │  Output:             │
                    │  - space-template_   │
                    │    desc-preproc_T1w  │
                    │  - forward xfm       │
                    │  - inverse xfm       │
                    └──────────────────────┘
```

## File Management Details

### Standard Flow (No Two-Pass Refinement)

**Files Created:**
1. `desc-preproc_T1w.nii.gz` - Bias-corrected anatomical (full size)
2. `desc-preproc_T1w_brain.nii.gz` - Skull-stripped anatomical
3. `desc-brain_mask.nii.gz` - Brain mask
4. `desc-brain_segmentation.nii.gz` - Segmentation (if available)
5. `desc-brain_hemimask.nii.gz` - Hemisphere mask (if available)
6. `space-{template}_desc-preproc_T1w.nii.gz` - Registered to template
7. `from-T1w_to-{template}_mode-image_xfm.h5` - Forward transform
8. `from-{template}_to-T1w_mode-image_xfm.h5` - Inverse transform

### Two-Pass Refinement Flow

**Files Created:**
1. `desc-preprocOrigSize_T1w.nii.gz` - Original bias-corrected (full size) - **RENAMED**
2. `desc-preproc_T1w.nii.gz` - Cropped bias-corrected anatomical - **UPDATED**
3. `desc-preproc_T1w_brain.nii.gz` - Skull-stripped (in cropped space)
4. `desc-brain_mask.nii.gz` - Brain mask (in cropped space)
5. `desc-brain_segmentation.nii.gz` - Segmentation (in cropped space)
6. `desc-brain_hemimask.nii.gz` - Hemisphere mask (in cropped space)
7. `space-{template}_desc-preproc_T1w.nii.gz` - Registered to template (in cropped space)
8. Transform files (as above)

### Key Points

1. **Input to Skull Stripping**: `anatf_cur` is the bias-corrected image (if bias correction enabled)
2. **Two-Pass Refinement**: FastSurferCNN crops the **input image** (which is already bias-corrected)
3. **input_cropped**: This is the cropped version of the bias-corrected image, NOT the original
4. **File Replacement**: When `input_cropped` exists:
   - Original `desc-preproc_T1w.nii.gz` → `desc-preprocOrigSize_T1w.nii.gz`
   - `input_cropped` → `desc-preproc_T1w.nii.gz`
5. **Subsequent Processing**: All downstream steps (registration) use the cropped space if two-pass was used

## Variable Flow

```
anatf_cur (initial) = self.anat_file (original)
    ↓
[Precheck] → anatf_cur = reoriented (if reorientation needed)
    ↓
[Bias Correction] → anatf_cur = bias_corrected
    ↓
[Save] → desc-preproc_T1w.nii.gz (copy of anatf_cur)
    ↓
[Skull Stripping] → Input: anatf_cur (bias-corrected)
                    ↓
                    [FastSurferCNN]
                    - If two-pass: crops input_image (bias-corrected)
                      → input_cropped (cropped bias-corrected)
                    - Output: skull-stripped (in cropped space if two-pass)
    ↓
[Handle input_cropped] → If exists:
                         - Rename desc-preproc → desc-preprocOrigSize
                         - Copy input_cropped → desc-preproc
    ↓
anatf_cur = skull-stripped (in cropped space if two-pass)
    ↓
[Registration] → Uses anatf_cur (already in correct space)
```

