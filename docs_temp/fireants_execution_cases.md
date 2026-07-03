# FireANTs Execution Cases

This note summarizes when FireANTs runs and when the pipeline uses ANTs CPU.

## Key Principle

**FireANTs = GPU only.** FireANTs' deformable (greedy) registration requires CUDA.
Its fused Adam optimizer (`adam_update_fused`) is a compiled CUDA extension with no CPU
fallback. ANTs CPU is used whenever a working GPU is not confirmed.

## Decision Logic

```
xfm_type == "syn" AND enable_fireants == true
    → _use_fireants():
        1. FireANTs importable?          → no  → ANTs CPU
        2. GPU usable? (torch.zeros)     → no  → ANTs CPU
        3. Fused Adam works on GPU?      → no  → ANTs CPU
           (+ cuda.synchronize to catch async errors)
        → yes to all → FireANTs on GPU

xfm_type != "syn" OR enable_fireants == false
    → ANTs CPU directly
```

## Case Table

| Case | `enable_fireants` | `xfm_type` | Docker `--gpus` | CUDA state | Registration engine | Device |
|---|---:|---|---|---|---|---|
| A | false | syn | any | any | ANTs CPU | CPU |
| B | true | rigid/affine/translation | any | any | ANTs CPU | CPU |
| C | true | syn | any | FireANTs import fails | ANTs CPU | CPU |
| D | true | syn | **no** | GPU_COUNT=0 → `CUDA_VISIBLE_DEVICES=""` → no usable GPU | ANTs CPU | CPU |
| E | true | syn | **no** | basic CUDA broken (`torch.zeros` fails) | ANTs CPU | CPU |
| F | true | syn | yes | basic CUDA ok, fused Adam fails (driver/runtime mismatch) | ANTs CPU | CPU |
| G | true | syn | yes | GPU fully usable | **FireANTs** | GPU |

## Defence-in-depth Strategy

Two layers protect all CUDA tools (not just FireANTs); the FireANTs gate is separate.

### Layer 0 — `entrypoint.sh` (Docker only)

When `GPU_COUNT=0` inside the container (e.g. `docker run` without `--gpus`) and
`CUDA_VISIBLE_DEVICES` is not already set, exports `CUDA_VISIBLE_DEVICES=""`.

**Effect:** All CUDA tools (FastSurfer, skullstripping, FireANTs) see no devices.
`torch.cuda.is_available()` returns `False` pipeline-wide. Covers Case D.

### Layer 1 — `_cuda_is_usable()` in `gpu_device.py`

`torch.cuda.is_available()` can return `True` with a broken CUDA stack.
Probes `torch.zeros(1, device="cuda")` instead.

**Effect:** `auto` device resolves to CPU when basic tensor ops fail.
Safety net for local (non-Docker) runs. Covers Case E.

### FireANTs gate — `_use_fireants()` in `registration.py`

Single decision point for whether FireANTs runs at all:

1. **Import check** — FireANTs installed?
2. **GPU check** — calls `_cuda_is_usable()` (Layer 1 probe)
3. **Fused op check** — probes `adam_update_fused` with CUDA tensors + `cuda.synchronize()`
   to catch driver/runtime mismatches where basic PyTorch CUDA succeeds but compiled
   FireANTs extensions fail (Case F)

If any check fails → ANTs CPU, no attempt at FireANTs CPU.
