# GPU Usage and Resource Management Review

Review of where brainana uses GPU and how resource identification and management are implemented. Includes findings and a proposed improvement plan for more consistent, standard, and robust handling.

---

## 1. Where GPU Is Used

### 1.1 Python Components

| Component | Location | Device Selection | Notes |
|-----------|----------|------------------|-------|
| **nhp_skullstrip_nn** | `src/nhp_skullstrip_nn/utils/gpu.py` | `get_device()`, `setup_device()` | Least-busy GPU via nvidia-smi or PyTorch fallback |
| **fastsurfer_nn** | `src/fastsurfer_nn/utils/gpu_utils.py`, `utils/common.py` | `find_device()`, `get_least_busy_gpu()` | Same idea, plus MPS (Apple Silicon), min_memory check |
| **FireANTs registration** | `src/nhp_mri_prep/operations/fireants_registration.py` | Hardcoded `"cuda:0" if torch.cuda.is_available() else "cpu"` | No config, no CUDA_VISIBLE_DEVICES awareness |
| **nhp_mri_prep environment** | `src/nhp_mri_prep/environment.py` | `check_system_resources()` | Read-only: nvidia-smi for GPU info (name, memory) |

### 1.2 Nextflow GPU Processes

| Process | Label | GPU Token | CUDA_VISIBLE_DEVICES |
|---------|-------|-----------|----------------------|
| ANAT_SKULLSTRIPPING | `gpu` | Yes | `export CUDA_VISIBLE_DEVICES=${gpu_id}` |
| FUNC_COMPUTE_BRAIN_MASK | `gpu` | Yes | `export CUDA_VISIBLE_DEVICES=${gpu_id}` |
| ANAT_REGISTRATION | `cpu` | No | Not set |
| FUNC_COMPUTE_REGISTRATION | `cpu` | No | Not set |

**Important:** When FireANTs is used, `ants_register` runs FireANTs inside ANAT_REGISTRATION and FUNC_COMPUTE_REGISTRATION, which are labeled `cpu`. Those processes use GPU but do not participate in the GPU token pool and do not set `CUDA_VISIBLE_DEVICES`. They can run in parallel with skull stripping and compete for GPU resources.

---

## 2. Resource Identification and Management

### 2.1 Nextflow Level

**Configuration** (`nextflow.config`):

- `gpuCount`: from `nvidia-smi --list-gpus` at config parse time (0 if unavailable)
- `maxJobsPerGpu`: `floor(min(memory.free across GPUs) / 4096)`, clamped to [1, 4]
- `perJobVramMiB`: 4096 (4 GiB per job assumption)
- `withLabel: 'gpu'`: `maxForks = gpuCount * maxJobsPerGpu`

**Token pool** (`main.nf`):

- `DataflowQueue` with `gpu_count * max_jobs_per_gpu` tokens (each token = gpu_id 0..N-1)
- ANAT_SKULLSTRIPPING and FUNC_COMPUTE_BRAIN_MASK take a token, run with `CUDA_VISIBLE_DEVICES=${gpu_id}`, and return it when done

**Module assignment** (`modules/anatomical.nf`, `modules/functional.nf`):

```groovy
# GPU Assignment: Assign this job to GPU ${gpu_id} (round-robin distribution)
export CUDA_VISIBLE_DEVICES=${gpu_id}
echo "[GPU Assignment] Task ${task.index} -> GPU ${gpu_id} (of ${params.gpu_count} available)"
```

When `CUDA_VISIBLE_DEVICES` is set, the Python process sees exactly one GPU as `cuda:0`. The token pool ensures the right physical GPU is exposed.

### 2.2 Python Level

**nhp_skullstrip_nn** (`src/nhp_skullstrip_nn/utils/gpu.py`):

- `get_device()`: returns `cuda:{get_least_busy_gpu()}` or `cpu`
- `get_least_busy_gpu()`: nvidia-smi `memory.used` (min usage) or PyTorch `memory_allocated` fallback
- `setup_device(device_id)`: maps `'auto' | -1 | int | 'cuda:N'` → `torch.device`

**fastsurfer_nn** (`src/fastsurfer_nn/utils/gpu_utils.py`, `utils/common.py`):

- Same pattern as nhp_skullstrip_nn, with extra logging and `memory.total` for “unused” reporting
- `find_device()`: supports `auto`, `cuda`, `cuda:N`, `mps`, `cpu`; optional `min_memory`; fallback to CPU if GPU memory insufficient

**FireANTs** (`fireants_registration.py`):

- `device = "cuda:0" if torch.cuda.is_available() else "cpu"`
- No config, no `CUDA_VISIBLE_DEVICES` handling, no `gpu_device` option

**Config-driven device**:

- `anat.skullstripping_segmentation.fastSurferCNN.gpu_device`: `"auto"` | int ≥ -1
- `anat.skullstripping.gpu_device`, `func.skullstripping.gpu_device`: same for nhp_skullstrip_nn

### 2.3 Environment Check

`nhp_mri_prep/environment.check_system_resources()`:

- Runs `nvidia-smi --query-gpu=name,memory.total,memory.free`
- Used for reporting and validation (e.g. “GPU not available but skull stripping requires it”)

---

## 3. Inconsistencies and Gaps

| Issue | Description |
|-------|-------------|
| **Duplicate GPU utils** | `nhp_skullstrip_nn/utils/gpu.py` and `fastsurfer_nn/utils/gpu_utils.py` both implement `get_least_busy_gpu` and `setup_device` with minor differences |
| **FireANTs device** | Always `cuda:0`; ignores config and `CUDA_VISIBLE_DEVICES` |
| **Registration vs GPU token** | ANAT_REGISTRATION and FUNC_COMPUTE_REGISTRATION can use FireANTs on GPU but are labeled `cpu`; no token, no `CUDA_VISIBLE_DEVICES` → contention with skull stripping |
| **Mixed device APIs** | `device_id` (int/str), `device` (torch.device), `gpu_device` (config) used in different layers |
| **MPS support** | Only fastsurfer_nn supports Apple Silicon MPS; nhp_skullstrip_nn and FireANTs do not |
| **CUDA_VISIBLE_DEVICES** | Nextflow sets it for GPU-labeled processes; Python code does not explicitly read it for registration (FireANTs) |
| **Nextflow GPU detection timing** | `gpuCount` and `maxJobsPerGpu` are computed at config parse time; long-lived runs may not reflect dynamic GPU changes |

---

## 4. Proposed Improvement Plan

### 4.1 Centralized GPU Device Module

**Goal:** Single source of truth for GPU selection and device setup.

- **New module:** `src/nhp_utils/gpu_device.py` (or shared under `nhp_mri_prep` if preferred)
- **API:**
  - `resolve_device(spec: str | int = "auto") -> torch.device`
  - `get_least_busy_gpu() -> int` (internal)
- **Behavior:**
  - If `CUDA_VISIBLE_DEVICES` is set: treat visible GPU(s) as 0..N; resolve `"auto"` → `cuda:0` (no “least busy” across invisible GPUs)
  - If not set: use existing nvidia-smi / PyTorch logic for least-busy selection
  - Support `spec`: `"auto"`, `-1`/`"cpu"`, `0`, `1`, `"cuda:1"`, etc.
  - Optional: MPS detection (Apple Silicon) with fallback to CPU
- **Migration:** nhp_skullstrip_nn, fastsurfer_nn, and nhp_mri_prep call into this module instead of their own utils.

### 4.2 Config-Driven FireANTs Device

**Goal:** FireANTs to respect config and environment.

- Add `general.gpu_device` in `defaults.yaml` (single top-level setting shared by registration, skull stripping, etc.)
- In `fireants_registration.py`, use `resolve_device(config.get("general", {}).get("gpu_device", "auto"))` instead of hardcoded `cuda:0`
- When run under Nextflow with `CUDA_VISIBLE_DEVICES` set, `"auto"` should resolve to `cuda:0` (the only visible GPU)

### 4.3 GPU Token for Registration When FireANTs Is Used

**Goal:** Avoid GPU contention between skull stripping and FireANTs.

- Add conditional label `gpu` for ANAT_REGISTRATION and FUNC_COMPUTE_REGISTRATION when FireANTs is enabled (e.g. via config flag or runtime detection)
- Alternatively: introduce `ANAT_REGISTRATION_GPU` / `FUNC_COMPUTE_REGISTRATION_GPU` processes that use the GPU token and run FireANTs; keep CPU-labeled versions for ANTs-only path
- Ensure these processes set `CUDA_VISIBLE_DEVICES` from the token and use `resolve_device("auto")` → `cuda:0`

### 4.4 Standard Device Spec Convention

**Goal:** Consistent interface across all GPU-using code.

- **Canonical spec:** `"auto"` | `-1` (CPU) | `0..N` (GPU index) | `"cuda:N"` | `"cpu"`
- **Internal representation:** `torch.device` wherever possible
- **Config key:** Single `general.gpu_device` for all GPU-using steps (registration, skull stripping, segmentation); document in schema/config docs

### 4.5 Optional Enhancements

- **AMD ROCm:** If PyTorch reports ROCm, treat similarly to CUDA
- **Memory checks:** Extend `find_device`-style `min_memory` checks to all GPU users
- **Logging:** Unified `[GPU]` or `[Device]` prefix for device selection messages
- **Tests:** Unit tests for `resolve_device` with mocked `CUDA_VISIBLE_DEVICES` and `torch.cuda`

---

## 5. Summary

| Layer | Current State | Proposed |
|-------|---------------|----------|
| **Nextflow** | Token pool for skull stripping; registration unmanaged for GPU | Extend token pool to FireANTs-based registration when used |
| **Python device selection** | Duplicate logic in nhp_skullstrip_nn and fastsurfer_nn | Central `resolve_device()` with CUDA_VISIBLE_DEVICES awareness |
| **FireANTs** | Hardcoded `cuda:0` | Config-driven + `resolve_device()` |
| **Config** | `gpu_device` scattered (skull stripping, fastSurferCNN) | Single `general.gpu_device` for all GPU steps |
| **MPS/ROCm** | Only fastsurfer_nn has MPS | Optional: add in shared module |

Implementing these changes would make GPU handling more consistent, predictable, and robust across skull stripping, segmentation, and registration.
