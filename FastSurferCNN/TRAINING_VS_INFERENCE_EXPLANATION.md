# Training vs Inference: Why Skipping Resize/Padding Works Better

## The Key Insight

**The model is fully convolutional**, meaning it can handle variable input sizes. The resize and padding in training were primarily for:
1. **Batch consistency** - ensuring all images in a batch have the same size
2. **Memory efficiency** - limiting maximum image size
3. **Edge handling** - providing context at image boundaries

But they're **not strictly necessary** for the model to work correctly, and can actually **introduce artifacts** that hurt performance.

---

## Training Pipeline: How Images Are Processed

### Step 1: Data Preparation (`step2_create_hdf5.py`)

**Function:** `resize_volume_proportional(volume, target_size=256)`

```python
def resize_volume_proportional(volume, target_size=256, order=1):
    h, w = volume.shape[:2]
    max_dim = max(h, w)
    scale_factor = target_size / max_dim
    new_h, new_w = int(h * scale_factor), int(w * scale_factor)  # ⚠️ Uses int()
    
    # Resize proportionally
    if scale_factor != 1.0:
        zoom_factors = (new_h/h, new_w/w) + (1,) * (len(volume.shape) - 2)
        resized = ndimage.zoom(volume, zoom_factors, order=order)
    else:
        resized = volume.copy()
    
    # Pad to exact target_size (256×256) with ZEROS
    pad_shape = (target_size, target_size) + volume.shape[2:]
    padded = np.zeros(pad_shape, dtype=volume.dtype)
    padded[:new_h, :new_w] = resized  # Place in top-left corner
    
    return padded, scale_factor
```

**Examples:**

**Small image (96×96):**
- `scale_factor = 256 / 96 = 2.666667`
- `new_h = int(96 * 2.666667) = 256` ✅ (exact match, no padding needed)
- Result: **256×256 image, no padding** (fills entire space)

**Large image (320×320):**
- `scale_factor = 256 / 320 = 0.8` (downsampling)
- `new_h = int(320 * 0.8) = 256` ✅ (exact match, no padding needed)
- Result: **256×256 image, no padding** (downsampled to fit)

**Medium image (223×317):**
- `scale_factor = 256 / 317 = 0.8076`
- `new_h = int(223 * 0.8076) = 180`
- `new_w = int(317 * 0.8076) = 256` ✅
- Result: **256×256 image with ZERO padding** (76 pixels on bottom)

**Key point:** All images in HDF5 are stored as **256×256** (with zero padding if needed).

### Step 2: Training Data Loading (`MultiScaleDataset`)

**Function:** `_pad()` - adds edge padding to `PADDED_SIZE` (288×288)

```python
def _pad(self, image):
    h, w = image.shape[:2]
    if self.max_size < h:  # max_size = 288
        # Crop if larger than 288
        return image[0:h-32, 0:w-32]
    
    # Pad to 288×288 with EDGE padding (replicates edge pixels)
    pad_h = self.max_size - h  # 288 - 256 = 32
    pad_w = self.max_size - w  # 288 - 256 = 32
    padded_img = np.pad(image, ((0, pad_h), (0, pad_w)), mode='edge')
    return padded_img
```

**Pipeline:**
1. Load from HDF5: **256×256** image (with possible zero padding)
2. `_pad()`: Add **edge padding** to **288×288**
3. Model sees: **288×288** images during training

**Why edge padding?**
- Avoids artificial zero boundaries that the model might learn to ignore
- Provides context at image edges
- Helps with boundary predictions

---

## Inference Pipeline: What We Tried vs What Works

### ❌ **Previous Approach (Broken for Small Images):**

```
Conformed image (96×96×96)
  ↓
Resize2DTest → 256×256×96  (upsampling with interpolation!)
  ↓
EdgePad2DTest → 288×288×96
  ↓
Model → 288×288 predictions
  ↓
Crop padding → 256×256 predictions
  ↓
resize_from_target_size() → 96×96 predictions  (downsampling with interpolation!)
  ↓
Done
```

**Problems:**
1. **Forward interpolation artifacts** (96→256 upsampling creates smooth edges)
2. **Reverse interpolation artifacts** (256→96 downsampling loses precision)
3. **Edge artifacts** from upsampling can be misclassified as brain
4. **Two interpolation steps** compound errors

### ✅ **Current Approach (Works for All Sizes):**

```
Conformed image (96×96×96 or 320×320×320)
  ↓
ToTensorTest → normalized tensor (no resize, no padding!)
  ↓
Model → predictions at conformed size
  ↓
Done! (predictions already match conformed image size)
```

**Why it works:**
1. **No interpolation artifacts** - works directly with original resolution
2. **Model is fully convolutional** - can handle variable input sizes
3. **Preserves spatial relationships** - no distortion from resizing
4. **Simpler pipeline** - fewer steps = fewer opportunities for errors

---

## Why This Works: The Model Architecture

### Fully Convolutional Networks (FCNs)

The FastSurferCNN model uses **fully convolutional layers**, which means:
- ✅ **No fixed input size requirement** - can process any spatial dimensions
- ✅ **Spatial relationships preserved** - convolutions work at any scale
- ✅ **Translation invariant** - same features detected regardless of position

### What the Model Actually Learned

During training, the model learned:
1. **Feature patterns** (edges, textures, brain structures)
2. **Spatial relationships** (relative positions of brain regions)
3. **Scale-invariant features** (through data augmentation and multi-scale training)

It did **NOT** learn:
- ❌ A fixed input size requirement
- ❌ To depend on specific padding patterns
- ❌ To expect images at exactly 288×288

### Why Padding Was Used in Training

Padding in training served these purposes:
1. **Batch processing** - PyTorch DataLoader needs consistent batch dimensions
2. **Memory management** - limits maximum image size to 288×288
3. **Edge context** - provides boundary information for edge predictions
4. **Augmentation compatibility** - some augmentations need fixed-size inputs

But these are **training-time constraints**, not model requirements!

---

## The Mismatch: Training vs Inference

### Training:
- Images resized to **256×256** (with zero padding if needed)
- Then edge-padded to **288×288**
- Model processes **288×288** images
- **But model is fully convolutional** - size is just for batch consistency

### Inference (Old Broken Approach):
- Images resized to **256×256** (upsampling for small images!)
- Then edge-padded to **288×288**
- Model processes **288×288** images
- Then cropped and resized back → **interpolation artifacts!**

### Inference (Current Working Approach):
- Images kept at **conformed size** (no resize!)
- No padding
- Model processes at **conformed size** directly
- **No interpolation artifacts!**

---

## Key Insights

### 1. **Resize is the Problem, Not the Solution**

For small images:
- **Upsampling (96→256)** introduces smooth interpolation artifacts
- These artifacts can be misclassified as brain tissue
- **Downsampling back (256→96)** loses precision and compounds errors

For large images:
- **Downsampling (320→256)** is less problematic (information loss, not artifacts)
- But still unnecessary if model can handle 320×320 directly

### 2. **Padding is Optional**

- Padding was for **batch consistency** in training
- Model doesn't require it - fully convolutional architecture handles variable sizes
- In inference, we process one image at a time, so no batch constraint

### 3. **The Model is Scale-Invariant**

- Training data includes various sizes (stored in HDF5 with size groups)
- Model learned features that work across scales
- Direct inference at conformed size preserves this scale-invariance

### 4. **Conformed Images Are Already Standardized**

- Conformed images are already in standard space (voxel size, orientation)
- They're ready for model input - no need for additional resizing
- Resizing adds unnecessary distortion

---

## Summary

**Why skipping resize/padding works better (current state):**

1. ✅ **No interpolation artifacts** - preserves original image quality
2. ✅ **Model is fully convolutional** - can handle variable input sizes
3. ✅ **Simpler pipeline** - fewer steps = fewer errors
4. ✅ **Preserves spatial relationships** - no distortion from resizing
5. ✅ **Matches model's scale-invariance** - learned from multi-scale training data

**However, the user raises an excellent point:** In principle, matching training preprocessing should be better. The fact that skipping resize/padding works better suggests there were **bugs in the resize implementation** that made it worse than skipping it.

---

## The Real Issue: Mismatch Between Training and Inference Resize

### Training Resize (`step2_create_hdf5.py`):
```python
new_h, new_w = int(h * scale_factor), int(w * scale_factor)  # Uses int()
```

### Inference Resize (`resize_to_target_size`):
```python
new_h, new_w = round(h * scale_factor), round(w * scale_factor)  # Uses round()
```

**This is a mismatch!** For example, for a 95×95 image:
- Training: `int(95 * 2.694737) = int(255.999) = 255` → 256×256 with 1px zero padding
- Inference: `round(95 * 2.694737) = round(255.999) = 256` → 256×256 with no padding

This mismatch means the model sees slightly different images during training vs inference, which can hurt performance.

### Additional Issues with Old Resize Approach:

1. **Forward/Reverse Resize Mismatch**: The reverse resize (`resize_from_target_size`) was not an exact inverse, leading to cumulative errors
2. **Interpolation Artifacts**: Upsampling small images (96→256) creates smooth interpolation artifacts that can be misclassified
3. **Edge Artifacts**: The combination of resize + padding + reverse resize compounds errors at boundaries

---

## Should We Match Training Preprocessing?

**Yes, ideally we should!** But we need to:

1. **Fix the resize implementation** to match training exactly:
   - Use `int()` instead of `round()` to match training
   - Ensure exact inverse for reverse resize
   - Match zero padding behavior from training

2. **Fix the reverse resize** to be an exact inverse:
   - Track the exact forward resize parameters
   - Use those parameters for exact reverse resize
   - Handle padding correctly

3. **Test both approaches**:
   - Current approach (no resize/padding): Works, simpler, no artifacts
   - Fixed resize approach (matching training): Should work better IF implemented correctly

**The current approach works because:**
- It avoids the bugs in the resize implementation
- The model is flexible enough to handle variable sizes
- No interpolation artifacts from upsampling

**But the ideal approach would be:**
- Match training preprocessing exactly
- Fix the resize bugs (int vs round, exact inverse)
- This should give the best results since it matches what the model was trained on

---

## Training Data Sizes

The HDF5 files store images grouped by size:
- Small images (< 256): resized to 256×256, stored in size group
- Large images (> 256): downsampled to 256×256, stored in size group
- All images: edge-padded to 288×288 during training

The model learned from this multi-scale training data, but ideally inference should match the exact preprocessing used during training for best results.

