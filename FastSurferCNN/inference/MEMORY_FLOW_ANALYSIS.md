# 3-Plane Prediction Memory Consumption Flow

## Overview
This document traces the GPU memory consumption throughout the 3-plane prediction pipeline.

## OPTIMIZATIONS IMPLEMENTED

### 1. Lazy Model Loading (saves ~16 GB)
Instead of loading all 3 models upfront (~24 GB), models are now loaded one at a time:
- Load model → Run inference → Unload → Next plane
- Peak GPU memory: ~8 GB (1 model) instead of ~24 GB (3 models)
- Trade-off: Slightly slower (reloads checkpoints for each subject)

### 2. Padding Disabled for Large Images (prevents OOM)
For images with max dimension > 320 voxels:
- Edge padding is automatically disabled
- Prevents creation of huge padded tensors (~20+ GB)
- Trade-off: Edge predictions may be slightly less accurate for large images

---

## Memory Consumption Timeline (After Optimizations)

### Phase 1: Model Initialization (`predictor.py` __init__)

**Location**: `predictor.py` lines 284-320

**Memory Consumption**:
- **No models loaded** - only configs and checkpoint paths are stored
- GPU memory: ~0 GB
- CPU memory: Minimal (configs, metadata)

**Code Flow**:
```python
# Lazy loading: Don't load models upfront
self._prepared_configs = {}
for plane, view in self.view_ops.items():
    self._prepared_configs[plane] = {"cfg": cfg, "ckpt": ckpt}
# Models loaded on-demand in get_prediction()
```

**Memory State After Phase 1**:
- GPU: ~0 GB (no models loaded yet)
- CPU: Minimal (configs, checkpoint paths)

---

### Phase 2: Image Preprocessing (`predictor.py` get_prediction)

**Location**: `predictor.py` lines 536-605

**Memory Consumption**:
1. **Load image**: CPU memory
2. **Conform image**: CPU memory
3. **Create pred_prob tensor**: GPU memory
   - Shape: `(H, W, D, num_classes)`
   - Dtype: `float16` (2 bytes per element)
   - Size: ~5-10 GB (depends on dimensions)

**Memory State After Phase 2**:
- GPU: ~5-10 GB (pred_prob tensor only, no models yet)
- CPU: Image data

---

### Phase 3: 3-Plane Inference Loop (with Lazy Loading)

**Location**: `predictor.py` get_prediction

**New Flow** (optimized):

For each plane (coronal → sagittal → axial):

1. **Load model** (~8 GB GPU)
2. **Run inference** (batches processed, aggregated into pred_prob)
3. **Unload model** (free ~8 GB GPU)
4. **Clear GPU cache**
5. Proceed to next plane

**Padding Check** (for large images):
- If max dimension > 320: padding is **disabled**
- Avoids creation of huge padded tensors

**Memory State During Phase 3**:
- GPU: ~8 GB (1 model) + ~5-10 GB (pred_prob) = **~13-18 GB peak**
- CPU: Image data, batch data

---

## Memory Comparison

| Component | Before (OOM) | After (Optimized) |
|-----------|-------------|-------------------|
| Models in memory | ~24 GB (3 models) | ~8 GB (1 at a time) |
| pred_prob tensor | ~5-10 GB | ~5-10 GB |
| Padded tensor (large images) | ~23-28 GB | 0 GB (disabled) |
| **Peak Total** | **~52-62 GB** | **~13-18 GB** |

---

## Implementation Details

### Lazy Loading (`predictor.py`)

```python
# In __init__: Store configs only (no GPU memory)
self._prepared_configs = {}
for plane, view in self.view_ops.items():
    self._prepared_configs[plane] = {"cfg": cfg, "ckpt": ckpt}

# In get_prediction(): Load → Run → Unload
for plane, plane_config in self._prepared_configs.items():
    model = Inference(cfg, ckpt=ckpt, device=self.device)  # Load ~8 GB
    pred_prob = model.run(pred_prob, ...)                   # Run
    del model                                                # Unload
    torch.cuda.empty_cache()                                 # Free GPU
```

### Padding Disabled for Large Images (`inference.py`)

```python
LARGE_IMAGE_THRESHOLD = 320
max_dim = max(orig_data.shape)
if padding_percent > 0.0 and max_dim > LARGE_IMAGE_THRESHOLD:
    logger.warning("Disabling edge padding for large image...")
    padding_percent = 0.0
```

---

## Trade-offs

| Optimization | Memory Savings | Speed Impact | Accuracy Impact |
|--------------|---------------|--------------|-----------------|
| Lazy loading | ~16 GB | +10-20s/subject | None |
| Disable padding (large) | ~20 GB | None | Minor edge loss |

