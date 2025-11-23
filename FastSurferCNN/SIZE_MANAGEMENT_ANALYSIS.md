# Size Management Analysis: Training vs Inference for Small Images

## Problem Summary
Small images (< 256) produce wrong segmentation results (including non-brain regions) in inference, while large images (> 256) work correctly.

## Training Pipeline (Data Preparation)

### Step 1: Data Preparation (`step2_create_hdf5.py`)

**Function:** `resize_volume_proportional()` (line 35-52)

```python
def resize_volume_proportional(volume, target_size=256, order=1):
    h, w = volume.shape[:2]
    max_dim = max(h, w)
    scale_factor = target_size / max_dim
    new_h, new_w = int(h * scale_factor), int(w * scale_factor)  # ⚠️ USES int()
    
    if scale_factor != 1.0:
        zoom_factors = (new_h/h, new_w/w) + (1,) * (len(volume.shape) - 2)
        resized = ndimage.zoom(volume, zoom_factors, order=order)
    else:
        resized = volume.copy()
    
    pad_shape = (target_size, target_size) + volume.shape[2:]
    padded = np.zeros(pad_shape, dtype=volume.dtype)
    padded[:new_h, :new_w] = resized  # Place in top-left
    
    return padded, scale_factor
```

**Example for 96×96 image:**
- `scale_factor = 256 / 96 = 2.666667`
- `new_h = int(96 * 2.666667) = int(256.0) = 256` ✅ (exact match)
- `new_w = int(96 * 2.666667) = int(256.0) = 256` ✅ (exact match)
- Result: 256×256 image with **no padding** (fills entire image)

**For non-exact cases (e.g., 95×95):**
- `scale_factor = 256 / 95 = 2.694737`
- `new_h = int(95 * 2.694737) = int(255.999) = 255` ⚠️
- `new_w = int(95 * 2.694737) = int(255.999) = 255` ⚠️
- Result: 256×256 image with **1 pixel padding** on right/bottom

### Step 2: Training Data Loading (`MultiScaleDataset`)

**Function:** `_pad()` (line 287-340)

```python
def _pad(self, image):
    h, w = image.shape[:2]
    pad_h = self.max_size - h  # max_size = PADDED_SIZE (e.g., 288)
    pad_w = self.max_size - w
    
    # Uses EDGE padding (replicates edge pixels)
    padded_img = np.pad(image, ((0, pad_h), (0, pad_w)), mode='edge')
    return padded_img
```

**Pipeline:**
1. HDF5 contains images at `target_size` (256×256) with possible padding
2. `_pad()` adds edge padding to `PADDED_SIZE` (288×288)
3. Model trains on 288×288 images with edge-padded boundaries

## Inference Pipeline

### Step 1: Image Conforming
- Input image (e.g., 67×95×96) → Conformed to standard space (e.g., 96×96×96)

### Step 2: Forward Resize (`Resize2DTest`)

**Function:** `resize_to_target_size()` (line 433-490)

```python
def resize_to_target_size(image, target_size=256, order=1):
    h, w = image.shape[:2]
    max_dim = max(h, w)
    scale_factor = target_size / max_dim
    new_h, new_w = round(h * scale_factor), round(w * scale_factor)  # ✅ USES round()
    
    if scale_factor != 1.0:
        zoom_factors = (new_h/h, new_w/w)
        resized = zoom(image, zoom_factors, order=order)
    else:
        resized = image.copy()
    
    pad_shape = (target_size, target_size) + image.shape[2:]
    padded = np.zeros(pad_shape, dtype=image.dtype)
    padded[:new_h, :new_w] = resized  # Place in top-left
    
    return padded, scale_factor
```

**Example for 96×96 conformed slice:**
- `scale_factor = 256 / 96 = 2.666667`
- `new_h = round(96 * 2.666667) = round(256.0) = 256` ✅
- `new_w = round(96 * 2.666667) = round(256.0) = 256` ✅
- Result: 256×256 image with **no padding** (fills entire image)

### Step 3: Edge Padding (`EdgePad2DTest`)
- Adds edge padding from 256×256 → 288×288
- Uses `mode='edge'` (replicates edge pixels)

### Step 4: Model Inference
- Model processes 288×288 images
- Output: 288×288 predictions

### Step 5: Remove Padding
- Crop from 288×288 → 256×256 (removes edge padding)

### Step 6: Reverse Resize (`resize_from_target_size`)

**Function:** `resize_from_target_size()` (line 493-650)

```python
def resize_from_target_size(image, target_size=256, output_h=96, output_w=96, order=0):
    max_output_dim = max(output_h, output_w)
    forward_scale = target_size / max_output_dim
    actual_content_h = round(output_h * forward_scale)  # What new_h was
    actual_content_w = round(output_w * forward_scale)  # What new_w was
    
    # For upsampled images, exclude last row/column to avoid edge artifacts
    if is_upsampled and actual_content_h == target_size:
        content_h = actual_content_h - 1  # Exclude last row
    else:
        content_h = actual_content_h
    
    # Crop to content region
    content_region = image[:content_h, :content_w]
    
    # Reverse zoom: (output_h/content_h, output_w/content_w)
    zoom_h = output_h / content_h
    zoom_w = output_w / content_w
    resized = zoom(content_region, (zoom_h, zoom_w), order=order)
    
    return resized
```

**Example for 96×96 output:**
- `actual_content_h = round(96 * 2.666667) = 256`
- `content_h = 256 - 1 = 255` (exclude last row)
- `zoom_h = 96 / 255 = 0.376471` (not 0.375!)
- Result: 255×255 → 96×96 via zoom

## Key Differences & Issues

### 1. **Mismatch: `int()` vs `round()`**

**Training:** Uses `int()` in `resize_volume_proportional()`
- For 96×96: `int(256.0) = 256` ✅ (works)
- For 95×95: `int(255.999) = 255` ⚠️ (creates 1px padding)

**Inference:** Uses `round()` in `resize_to_target_size()`
- For 96×96: `round(256.0) = 256` ✅ (works)
- For 95×95: `round(255.999) = 256` ✅ (no padding)

**Impact:** Training and inference may handle edge cases differently!

### 2. **Edge Artifact Exclusion in Reverse Resize**

**Current Fix:** Excludes last row/column for upsampled images
- `content_h = 256 - 1 = 255`
- This changes the zoom factor: `96/255 ≠ 96/256`
- This is **NOT** the exact inverse of forward resize!

**Problem:** Forward resize uses `zoom_factors = (256/96, 256/96) = (2.666667, 2.666667)`
- Reverse should use `zoom_factors = (96/256, 96/256) = (0.375, 0.375)`
- But we're using `zoom_factors = (96/255, 96/255) = (0.376471, 0.376471)`
- This mismatch causes incorrect resizing!

### 3. **Training vs Inference Padding**

**Training:**
- Data stored at 256×256 (with possible padding from `int()` truncation)
- Edge padding added to 288×288 during training
- Model sees edge-padded boundaries

**Inference:**
- Resize to 256×256 (with `round()`, may have no padding)
- Edge padding added to 288×288
- Model sees edge-padded boundaries
- **But:** Reverse resize excludes last row/column, causing mismatch

## Root Cause

The issue is that we're trying to exclude edge artifacts by cropping the last row/column, but this breaks the mathematical inverse relationship:

- **Forward:** `96 → 256` via zoom factor `256/96 = 2.666667`
- **Reverse (current):** `255 → 96` via zoom factor `96/255 = 0.376471` ❌ (wrong!)
- **Reverse (correct):** `256 → 96` via zoom factor `96/256 = 0.375` ✅

The exclusion of the last row/column is causing the reverse resize to not be the exact inverse, leading to incorrect results.

## Solution

**Fixed:** Removed the exclusion of last row/column to maintain exact inverse relationship.

**Current Status:**
- Forward resize: `96 → 256` via zoom `256/96 = 2.666667`
- Reverse resize: `256 → 96` via zoom `96/256 = 0.375` ✅ (exact inverse)

**If non-brain regions are still included:**
The issue may be that the model is over-predicting in edge regions that are interpolated during upsampling. This should be handled by:
1. Mask post-processing (dilation/erosion, largest component selection) - already implemented
2. Ensuring training data preparation matches inference (both use same resize logic)
3. Consider using edge-aware loss or post-processing to suppress edge predictions

**Recommendation:**
- Fix `resize_volume_proportional()` in training to use `round()` instead of `int()` to match inference
- This ensures training and inference use identical resize logic

