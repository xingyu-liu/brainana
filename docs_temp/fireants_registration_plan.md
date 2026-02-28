# FireANTs registration — plan (same format as ANTs)

**Goal:** Complete `fireants_registration()` in `brainana/tests/test_fireants_py` so it matches the interface and output format of `ants_register()` in `brainana/src/nhp_mri_prep/operations/registration.py`, with xfm_type-driven stages. Transform files are used directly (no composite assembly needed).

**References:**
- FireANTs: https://github.com/rohitrango/FireANTs  
- ANTs transform format: https://github.com/ANTsX/ANTsPy/wiki/ANTs-transform-concepts-and-file-formats
- Local: `ants_register` (registration.py ~L149), `compose_ants_registration_cmd` (registration.py ~L86)

---

## 1. Target behavior (mirror ANTs)

### 1.1 Function signature and return (same as `ants_register`)

- **Parameters:** `fixedf`, `movingf`, `working_dir`, `output_prefix=None`, `config=None`, `logger=None`, `xfm_type='syn'`.
- **Return:** `Dict[str, str]` with:
  - `output_path_prefix`: e.g. `working_dir/output_prefix`
  - `imagef_registered`: path to `{output_path_prefix}_registered.nii.gz`
  - `forward_transform`: path to transform file (`.mat` for rigid/affine, `.nii.gz` warp for syn)
  - `inverse_transform`: path to inverse transform file (`.mat` for rigid/affine, `.nii.gz` inverse warp for syn)
- **Validation:** Reuse or mirror `ants_register` (input validation, `ensure_working_directory`, optional `validate_output_file`).
- **Errors:** Same style: `FileNotFoundError` for missing inputs, `RuntimeError` on registration failure, `ValueError` for bad config/xfm_type.

### 1.2 xfm_type behavior (stages)

| xfm_type | FireANTs steps |
|----------|----------------|
| `rigid`  | Run **RigidRegistration** only. |
| `affine` | Run **AffineRegistration** only. |
| `syn`    | Forward: Run **AffineRegistration** then **GreedyRegistration** with `init_affine`. Inverse: Run separate **AffineRegistration** then **GreedyRegistration** with swapped images (moving → fixed) without initialization. |

- Reject any other `xfm_type` with `ValueError` (e.g. only allow `'rigid'`, `'affine'`, `'syn'`).
- For `syn`, forward registration follows FireANTs quickstart/tutorial: affine → greedy (compositive). Inverse registration runs a separate forward registration with swapped images for better accuracy.

---

## 2. Output format: Direct transform files (no composites)

FireANTs writes transform files directly:

- **Rigid/Affine:** `.mat` (ITK affine) via `save_as_ants_transforms(path)`.
- **Greedy (syn):** displacement field (e.g. `.nii.gz`) via `save_as_ants_transforms(path)`; optional **inverse** via `save_as_ants_transforms(path, save_inverse=True)` (see `DeformableMixin.save_as_ants_transforms`).

**Important:** For `syn` type registration:
- **Forward:** When `GreedyRegistration` is initialized with `init_affine`, the saved warp transform **already includes the affine component intrinsically**.
- **Inverse:** Instead of computing the inverse of the forward warp (which is an approximation), we run a separate forward registration with swapped images (moving → fixed) without initialization. This produces a more accurate inverse transform.

Therefore, we use the warp files directly as complete transforms without needing to create composite transforms.

### 2.1 Per xfm_type: what to produce

- **CompositeTransformUtil.cxx:**
  - `--assemble CompositeName transform1 [transform2 ...]`: reads a list of transforms and writes a single composite (first transform = first in list).
  - Order for **antsApplyTransforms** is “last on command line applied first” (right-to-left), so the **file** order for the composite should match the logical order: e.g. first affine, then warp (so when ANTs applies the composite it does warp then affine, i.e. affine first then warp in moving→fixed direction).
- **antsRegistration --write-composite-transform 1:**  
  Produces `_Composite.h5` (forward) and `_InverseComposite.h5` (inverse) directly.

So for FireANTs we need to:

1. Get one or more forward transform files (affine `.mat` and optionally warp `.nii.gz`).
2. Assemble them into **one** forward composite → `{prefix}_Composite.h5`.
3. Get inverse transform file(s) (inverse affine and optionally inverse warp).
4. Assemble them into **one** inverse composite → `{prefix}_InverseComposite.h5`.

### 2.2 Per xfm_type: what to produce

- **rigid**
  - Forward: one affine (rigid) `.mat`.
  - Inverse: one inverse affine `.mat`.
  - Composite: forward = that one affine; inverse = that one inverse affine. So `_Composite.h5` and `_InverseComposite.h5` each contain a single transform (still in composite form for API consistency).

- **affine**
  - Same as rigid: one affine `.mat`, one inverse affine `.mat` → `_Composite.h5` and `_InverseComposite.h5`.

- **syn**
  - Forward: affine `.mat` + displacement field (e.g. `warp.nii.gz`). Order for composite: **[affine, warp]** (so application order is: apply affine then warp when going moving→fixed).
  - Inverse: inverse warp + inverse affine. Order for composite: **[inverse_warp, inverse_affine]** so that applying the inverse composite does inverse_warp then inverse_affine (fixed→moving).
  - FireANTs: `GreedyRegistration.save_as_ants_transforms(forward_path)` and `save_as_ants_transforms(inverse_path, save_inverse=True)` give us the warp files; we also have affine from `AffineRegistration.save_as_ants_transforms` and can compute inverse affine (matrix inverse) for the inverse composite.

### 2.3 How to create `_Composite.h5` and `_InverseComposite.h5`

**Option A — Use ANTs CompositeTransformUtil (preferred if ANTs is available):**

- After FireANTs has written all pieces:
  - Forward:  
    `CompositeTransformUtil --assemble {prefix}_Composite.h5 affine.mat [warp.nii.gz]`  
    (for syn: two files; for rigid/affine: one file).
  - Inverse:  
    `CompositeTransformUtil --assemble {prefix}_InverseComposite.h5 inverse_affine.mat [inverse_warp.nii.gz]`  
    (for syn: two files; for rigid/affine: one file).
- Requires: ANTs on PATH; CompositeTransformUtil callable (check how brainana invokes ANTs elsewhere).
- Order of arguments must match ANTs convention (same as in CompositeTransformUtil.cxx: first transform in list = first in composite).

**Option B — Python/ITK (if ANTs not desired or unavailable):**

- Use ITK (or SimpleITK + itk) to:
  - Read each transform file (affine `.mat`, displacement field image).
  - Build an `itk.CompositeTransform` (or equivalent), add transforms in the correct order.
  - Write the composite to `.h5` (ITK supports writing composite transforms to file).
- For inverse: either use FireANTs’ inverse warp + invert affine matrix and write inverse affine, then assemble; or use ITK’s transform inversion APIs if available for composite.
- Requires: itk / SimpleITK with transform IO for composite and displacement; correct ordering and inverse semantics to match ANTs.

**Recommendation:** Prefer Option A for maximum compatibility with existing ANTs pipelines and with ANTs’ own composite format. Add a fallback or clear error if CompositeTransformUtil is not found. Document in the plan that implementation will call CompositeTransformUtil for assembly.

---

## 3. Inverse transforms

- **Rigid/Affine:**  
  FireANTs rigid/affine classes do not expose a “save inverse” API. Compute inverse by inverting the 4×4 (or 3×3+translation) matrix and write a new `.mat` (ITK affine format). Either use ANTs `antsApplyTransforms` with invert, or use Python (e.g. numpy + same ITK/ANTs .mat write convention), or call a small ANTs/ITK utility that reads one affine and writes inverse. Then use that inverse `.mat` as the single component of `_InverseComposite.h5`.

- **Syn:**  
  Run a separate forward registration with swapped images (moving → fixed) without initialization. Save the forward warp from this second registration as the inverse warp. This produces a more accurate inverse transform than computing the inverse of the forward warp. The inverse warp file is used directly (no separate inverse affine needed).

---

## 4. File layout and naming (match ANTs)

- `output_path_prefix` = `os.path.join(working_dir, output_prefix)` (same as ANTs).
- All outputs in `os.path.dirname(output_path_prefix)` with base name `os.path.basename(output_path_prefix)`:
  - `{output_path_prefix}_registered.nii.gz`
  - `{output_path_prefix}_Composite.h5`
  - `{output_path_prefix}_InverseComposite.h5`
- Intermediate FireANTs files (e.g. `affine.mat`, `warp.nii.gz`, `inverse_affine.mat`, `inverse_warp.nii.gz`) can live in the same directory with a clear naming scheme (e.g. `{prefix}_0_affine.mat`, `{prefix}_1_warp.nii.gz`) to avoid clashes and to pass to CompositeTransformUtil in order. Optionally delete intermediates after assembly to match ANTs’ “only composite + registered image” output, or keep them for debugging (configurable).

---

## 5. Implementation checklist (no code yet)

1. **Signature and validation**
   - Align `fireants_registration` signature and docstring with `ants_register`.
   - Validate inputs (paths, working_dir), resolve `output_prefix`, create `output_path_prefix`, init `outputs` dict with same keys as ANTs.

2. **xfm_type dispatch**
   - If `xfm_type == 'rigid'`: run only `RigidRegistration`; save forward affine; compute and save inverse affine.
   - If `xfm_type == 'affine'`: run only `AffineRegistration`; save forward affine; compute and save inverse affine.
   - If `xfm_type == 'syn'`: 
     - Forward: run `AffineRegistration` then `GreedyRegistration(init_affine=...)`; save forward warp.
     - Inverse: run separate `AffineRegistration` then `GreedyRegistration` with swapped images (moving → fixed) without initialization; save inverse warp.

3. **Registered image**
   - For rigid/affine: use registration’s `evaluate` or equivalent to get moved image; write to `{output_path_prefix}_registered.nii.gz` (same as ANTs).
   - For syn: use `GreedyRegistration.evaluate(batch_fixed, batch_moving)` and write same path.

4. **Forward transform**
   - Rigid/affine: save affine `.mat` file; use it directly as `forward_transform`.
   - Syn: save warp `.nii.gz` file (which includes affine); use it directly as `forward_transform`.

5. **Inverse transform**
   - Rigid/affine: compute and save inverse affine `.mat` file; use it directly as `inverse_transform`.
   - Syn: run separate forward registration with swapped images; save the forward warp as inverse warp `.nii.gz` file; use it directly as `inverse_transform`.

6. **Inverse affine**
   - Implement utility to invert the rigid/affine matrix and write ITK .mat format (for rigid/affine cases only; syn case doesn't need separate inverse affine).

7. **Return**
   - Set `outputs["imagef_registered"]`, `outputs["forward_transform"]`, `outputs["inverse_transform"]` only if the corresponding files exist (mirror ANTs’ exists checks); log warnings for missing files; return `outputs`.

8. **Config and logging**
   - Use `config` / `logger` same way as ANTs (defaults, optional verbose). Registration parameters (scales, iterations, etc.) can come from config or from FireANTs defaults used in the current test script.

9. **Dependencies**
   - FireANTs (RigidRegistration, AffineRegistration, GreedyRegistration, BatchedImages, Image, etc.).
   - scipy (for reading/writing `.mat` files and matrix inversion).
   - **No ANTs required:** We use transform files directly, so CompositeTransformUtil is not needed.

10. **Tests**
    - Add or extend tests that run `fireants_registration` for `rigid`, `affine`, and `syn` and check that the returned paths exist and that `forward_transform` / `inverse_transform` point to the correct transform files (`.mat` for rigid/affine, `.nii.gz` for syn).

---

## 6. Summary

- **Behavior:** Same function contract as `ants_register`; xfm_type selects rigid-only, affine-only, or affine+syn.
- **Outputs:** `_registered.nii.gz`, `_Composite.h5`, `_InverseComposite.h5`, built from FireANTs’ native outputs and assembled in ANTs-style composite form using CompositeTransformUtil (or ITK fallback).
- **No implementation yet:** this document is the plan only; implementation will follow in code.

---

## 7. Installation and dependency tracking (FireANTs in brainana)

**Goal:** Install FireANTs for testing without touching the main brainana env. Use a **separate venv** (Option C) so “good old brainana” stays in `.venv` and FireANTs testing lives in `.venv-fireants`.

**Chosen approach:** **Option C — Separate venv for FireANTs.** Create `.venv-fireants`, install brainana + FireANTs there. In that env, use the **higher versions** (FireANTs’ requirements) first and verify brainana still works.

### 7.0 Installation order (streamlined)

From brainana repo root, in order:

| Step | Action | Details |
|------|--------|--------|
| 0 | System deps (once) | `sudo apt-get install -y --no-install-recommends libsuitesparse-dev` (for brainana’s scikit-sparse). See brainana `Dockerfile` python-builder. |
| 1 | Create venv | `uv venv .venv-fireants` then `source .venv-fireants/bin/activate` |
| 2 | Install FireANTs first | `uv pip install fireants` (so torch/SimpleITK versions match FireANTs) |
| 3 | Install brainana | `LDFLAGS="-L/usr/lib/x86_64-linux-gnu" uv pip install -e .` (LDFLAGS needed if FSL’s linker is first in PATH). §7.6 |
| 4 | Verify brainana | `python -c "import nhp_mri_prep; print('ok')"` |
| 5 | (Optional) Fused CUDA ops | Clone FireANTs to `.fireants-src`, build/install with **system** compiler. Required for `xfm_type='syn'`. §7.8 |
| 6 | (Optional) Verify fused_ops | `python -c "import fireants_fused_ops; from fireants.registration.greedy import GreedyRegistration; print('OK')"`. After fused_ops, **deactivate and re-activate** so the patched `activate` sets `LD_LIBRARY_PATH` and `LD_PRELOAD`. §7.8 |

**Note:** ANTs is **not required** since we use transform files directly (no composite assembly). `.venv-fireants/` and `.fireants-src/` are in `.gitignore`.

### 7.1 What FireANTs needs (from their Dockerfile and pyproject.toml)

- **FireANTs Dockerfile** (https://github.com/rohitrango/FireANTs/blob/main/docker/Dockerfile):
  - Python 3, venv, build-essential, ninja-build (for compiling fused_ops).
  - PyTorch: they use `torch==2.5.1` with CUDA 12.1 (`--index-url https://download.pytorch.org/whl/cu121`).
  - Install: `pip install .` (main package), then `cd fused_ops && python setup.py build_ext && python setup.py install` (optional fused CUDA ops for speed/memory).
- **FireANTs pyproject.toml** (runtime deps):
  - `torch>=2.3.0`
  - `SimpleITK==2.2.1` (pinned)
  - `nibabel`, `numpy`, `scipy`, `scikit-image`, `matplotlib`, `typing`, `tqdm`, `pandas`, `hydra-core`, `pytest`

For testing phase: install the **main FireANTs package** (PyPI); skip **fused_ops** unless we later build from the FireANTs repo.

### 7.2 brainana current setup

- **Tool:** `uv` (sync / pip install from `pyproject.toml`).
- **Main env:** `.venv` — “good old brainana” only; no change to its deps or lockfile.
- **Deps:** brainana has `torch>=2.0.0`, `SimpleITK>=2.1.0`, nibabel, numpy, scipy, etc. in `pyproject.toml`; `uv.lock` stays for this env only.

### 7.3 Option C: Separate venv for FireANTs (chosen)

- **Create a dedicated venv:** `uv venv .venv-fireants` (from repo root).
- **Use it only for FireANTs testing:** install brainana (editable) + FireANTs inside `.venv-fireants`.
- **Tracking:**
  - **Good old brainana** = `.venv` + `pyproject.toml` + `uv.lock` (unchanged).
  - **FireANTs (testing)** = `.venv-fireants`; whatever gets installed there (brainana + fireants and their resolved versions). No change to `pyproject.toml` or `uv.lock` for FireANTs.
- **Pros:** Full isolation; core env never sees FireANTs or version bumps; easy to delete `.venv-fireants` if we drop FireANTs.
- **Cons:** Two envs to maintain; brainana must be installed again in the FireANTs venv.

### 7.4 Version conflict: try higher versions first in FireANTs env

- **Conflict:** FireANTs wants `torch>=2.3.0`, `SimpleITK==2.2.1`; brainana has `torch>=2.0.0`, `SimpleITK>=2.1.0`.
- **Strategy:** In the **FireANTs venv only**, install with FireANTs’ **higher** requirements first (i.e. let FireANTs pull `torch>=2.3.0` and `SimpleITK==2.2.1`), then install brainana in that same env. After install, **verify brainana still works** (e.g. run a quick test or import of nhp_mri_prep / existing tests). If something breaks, we then document the failure and consider relaxing versions only in that venv (e.g. try older SimpleITK or torch) as a fallback.
- **Summary:** In `.venv-fireants`, prefer FireANTs’ versions; validate brainana compatibility there. Main `.venv` is never changed.

### 7.5 What gets installed in `.venv-fireants`

- **brainana** (editable): `uv pip install -e .` so the FireANTs test script and nhp_mri_prep use the repo code.
- **FireANTs:** `uv pip install fireants` (PyPI). This will pull in FireANTs’ deps (torch>=2.3.0, SimpleITK==2.2.1, hydra-core, etc.). Do **not** add fused_ops to this flow; document that fused_ops can be built from the FireANTs repo later if needed.

### 7.6 Concrete steps (Option C)

Same order as §7.0; details below.

1. **Create venv:** `uv venv .venv-fireants` then `source .venv-fireants/bin/activate` (Windows: `.venv-fireants\Scripts\activate`).
2. **Install FireANTs first:** `uv pip install fireants` — brings in torch≥2.3, SimpleITK 2.2.1, etc.
3. **Install brainana:**  
   - **System:** `sudo apt-get install -y --no-install-recommends libsuitesparse-dev` (once; same as brainana Dockerfile python-builder).  
   - **In venv:** `LDFLAGS="-L/usr/lib/x86_64-linux-gnu" uv pip install -e .`  
   If FSL (or another custom toolchain) is first in PATH, its linker may not see system libs; `LDFLAGS` points to `libcholmod`. Without it you get “cannot find -lcholmod” when building scikit-sparse.
4. **Verify:** `python -c "import nhp_mri_prep; print('ok')"`.
5. **Optional:** Add `.venv-fireants/` (and `.fireants-src/`) to `.gitignore`.

### 7.7 Summary table (quick reference)

| What                         | How to install                          | Tracked in                          |
|-----------------------------|-----------------------------------------|-------------------------------------|
| Good old brainana           | `source .venv/bin/activate` then `uv sync` or `uv pip install -e .` | `pyproject.toml` `dependencies` + `uv.lock`; env = `.venv` |
| FireANTs (testing)          | §7.0 table steps 1–4; LDFLAGS for step 3 if FSL in PATH | Env `.venv-fireants` only; no change to pyproject or lockfile |
| Fused ops (optional)         | §7.0 step 5; §7.8 (clone, build with system compiler, install) | `.fireants-src/` (gitignored)       |
| Runtime (fused_ops)         | `.venv-fireants/bin/activate` patched: `LD_LIBRARY_PATH` + `LD_PRELOAD` for torch and venv libcudart | §7.8; re-activate after installing fused_ops |

### 7.8 Fused CUDA operations

FireANTs provides **fused CUDA operations** for better memory and runtime (especially for `xfm_type='syn'` / GreedyRegistration). They are built from source and installed into `.venv-fireants`; the PyPI `fireants` package does not include them.

**Requirements:** NVIDIA GPU, CUDA toolkit (`nvcc` on PATH), and the FireANTs source repo (for the `fused_ops` directory).

**Use the system compiler.** If FSL (or another custom toolchain) is first in your `PATH`, the build will use its `gcc`/`g++`/`ld`. That can cause:
- Linker not searching system paths (we already saw this with scikit-sparse and `libcholmod`).
- ABI or toolchain mismatches with CUDA/PyTorch.

So run both **build** and **install** with the system compiler first in `PATH`:

```bash
# From brainana repo root
git clone --depth 1 https://github.com/rohitrango/FireANTs.git .fireants-src
cd .fireants-src/fused_ops

# Use system gcc/g++/ld (not FSL’s) so CUDA extension links correctly
export PATH="/usr/bin:$PATH"

# Build and install into .venv-fireants
/path/to/brainana/.venv-fireants/bin/python setup.py build_ext
/path/to/brainana/.venv-fireants/bin/python setup.py install
cd ../..
```

Set `BRAINANA` to the brainana repo path if not in it. Or activate `.venv-fireants` and run:

```bash
source .venv-fireants/bin/activate
cd .fireants-src/fused_ops
env PATH="/usr/bin:$PATH" python setup.py build_ext
env PATH="/usr/bin:$PATH" python setup.py install
cd ../..
```

Optional: install `ninja` for faster rebuilds (e.g. `apt install ninja-build` or `pip install ninja`).

`.fireants-src/` is gitignored.

**Runtime:** `.venv-fireants/bin/activate` is **patched** to set `LD_LIBRARY_PATH` (nvidia/cuda_runtime + torch lib) and `LD_PRELOAD` (venv’s `libcudart.so.12`) so the venv’s CUDA runtime is used and you avoid `undefined symbol: cudaGetDriverEntryPointByVersion`. **Deactivate and re-activate** after installing fused_ops. If you recreate the venv:  
`export LD_LIBRARY_PATH=$VIRTUAL_ENV/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:$VIRTUAL_ENV/lib/python3.11/site-packages/torch/lib:$LD_LIBRARY_PATH`  
`export LD_PRELOAD=$VIRTUAL_ENV/lib/python3.11/site-packages/nvidia/cuda_runtime/lib/libcudart.so.12`

### 7.9 Implementation notes (Option C done)

- **Done:**
  - Created `.venv-fireants` with `uv venv .venv-fireants`.
  - Installed FireANTs first: `uv pip install --python .venv-fireants/bin/python fireants` (FireANTs 1.0.0, torch 2.10.0, SimpleITK 2.2.1, etc.).
  - Added `.venv-fireants/` to `.gitignore`.
- **brainana install in `.venv-fireants`:** Failed on `scikit-sparse` because it needs SuiteSparse (CHOLMOD) at **build** time. Use the same system deps as in **brainana’s Dockerfile**:
  - **Build (for `uv pip install -e .`):** `libsuitesparse-dev` — see `Dockerfile` **python-builder** stage (around line 49): `apt-get install ... libsuitesparse-dev ...`.
  - **Runtime (optional on host):** The Docker **runtime** stage also installs `libcholmod3` and sets OpenBLAS alternatives so CHOLMOD/scikit-sparse find threaded symbols; on a typical Debian/Ubuntu host, `libsuitesparse-dev` usually brings in the runtime libs too, so for local `.venv-fireants` you often only need the dev package.
  **Steps to finish brainana in `.venv-fireants` (Debian/Ubuntu):**
  ```bash
  # Same as brainana Dockerfile python-builder: build deps for scikit-sparse
  sudo apt-get update && sudo apt-get install -y --no-install-recommends libsuitesparse-dev

  source .venv-fireants/bin/activate
  # If FSL (or another custom toolchain) is in PATH, its linker may not search
  # system paths; point it to system libcholmod so scikit-sparse builds:
  LDFLAGS="-L/usr/lib/x86_64-linux-gnu" uv pip install -e .
  python -c "import nhp_mri_prep; print('ok')"
  ```
  If at runtime you see CHOLMOD/OpenBLAS symbol errors, install runtime and set alternatives like the Dockerfile runtime stage (e.g. `libcholmod3`, `update-alternatives` for libblas/liblapack).
- **FireANTs and syn:** `GreedyRegistration` requires `fireants_fused_ops`; **rigid** and **affine** work without it. To enable **syn**, install fused_ops per §7.8 (system compiler).
- **Done in this repo:** `.venv-fireants` created; FireANTs then brainana (with LDFLAGS) installed; `.fireants-src` cloned and fused_ops built/installed with system compiler; activate script patched for `LD_LIBRARY_PATH` and `LD_PRELOAD`. See §7.0 and §7.6 for the step-by-step to repeat elsewhere.
