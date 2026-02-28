"""Run FireANTs chained pipeline. Steps before syn use MI; syn uses CC.

Pipeline (stop at xfm_type):
  moments (CC*) -> rigid (MI) -> affine (MI) -> [greedy (CC) if syn]
  * Moments uses CC: FireANTs _get_best_orientation expects per-voxel loss.
"""
# %%
import logging
import re
from pathlib import Path

import numpy as np
import torch

from fireants.io import BatchedImages, FakeBatchedImages, Image

try:
    from scipy.io import loadmat, savemat
except ImportError:
    loadmat = savemat = None
from fireants.registration.moments import MomentsRegistration
from fireants.registration.rigid import RigidRegistration
from fireants.registration.affine import AffineRegistration
from fireants.registration.greedy import GreedyRegistration

# %%
moving_f = Path('/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/T1wT2w/T2w_easy.nii.gz')
fixed_f = Path('/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/T1wT2w/T1w_easy.nii.gz')

xfm_type = 'rigid'  # 'rigid' | 'affine' | 'syn'

output_dir = moving_f.parent / 'registration'
output_dir.mkdir(parents=True, exist_ok=True)

base_name = moving_f.stem.replace('.nii', '')
output_prefix = output_dir / base_name


def _get_output_paths(prefix: Path, xfm: str) -> dict:
    p = Path(prefix)
    paths = {"registered": str(p.parent / f"{p.name}_registered.nii.gz")}
    if xfm == "syn":
        paths["forward"] = str(p.parent / f"{p.name}_warp.nii.gz")
        paths["inverse"] = str(p.parent / f"{p.name}_inverse_warp.nii.gz")
    else:
        suffix = "rigid" if xfm == "rigid" else "affine"
        paths["forward"] = str(p.parent / f"{p.name}_{suffix}.mat")
        paths["inverse"] = str(p.parent / f"{p.name}_inverse_{suffix}.mat")
    return paths


def _invert_affine_mat(affine_path: str, inverse_path: str, log: logging.Logger) -> None:
    if loadmat is None or savemat is None:
        raise RuntimeError("scipy required to invert affine .mat (pip install scipy)")
    data = loadmat(affine_path)
    key = next(k for k in data if k.startswith("AffineTransform_") and not k.startswith("__"))
    params = data[key].flatten().astype(np.float64)
    total_params = params.size
    if total_params == 12:
        dims = 3
    elif total_params == 6:
        dims = 2
    else:
        m = re.search(r'_(\d+)_\d+', key)
        dims = int(m.group(1)) if m else None
        if dims is None or total_params != dims * dims + dims:
            raise ValueError(f"Cannot infer dims from {total_params} params")
    matrix_size = dims * dims
    A = params[:matrix_size].reshape(dims, dims)
    t = params[matrix_size:]
    A_inv = np.linalg.inv(A)
    t_inv = -A_inv @ t
    params_inv = np.concatenate([A_inv.flatten(), t_inv]).astype(data[key].dtype)
    out = {k: v for k, v in data.items() if not k.startswith("__")}
    out[key] = params_inv.reshape(data[key].shape)
    if "fixed" not in out:
        out["fixed"] = np.zeros((dims, 1), dtype=np.float32)
    saved = False
    for fmt in ['4', '5']:
        try:
            savemat(inverse_path, out, format=fmt, oned_as='column')
            saved = True
            break
        except (ValueError, NotImplementedError):
            continue
    if not saved:
        savemat(inverse_path, out, oned_as='column')
    log.info(f"Wrote inverse affine: {inverse_path}")


def _save_registered(reg, batch_fixed, batch_moving, path: str, log: logging.Logger) -> None:
    moved = reg.evaluate(batch_fixed, batch_moving)
    FakeBatchedImages(moved, batch_fixed).write_image(path)
    log.info(f"Registered image: {path}")

# %%
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
device = "cuda:0" if torch.cuda.is_available() else "cpu"
if device == "cpu":
    logger.warning("CUDA not available, using CPU.")

# Load images
fixed_image = Image.load_file(str(fixed_f))
moving_image = Image.load_file(str(moving_f))
batch_fixed = BatchedImages([fixed_image])
batch_moving = BatchedImages([moving_image])

SCALES = [4, 2, 1]
ITERS_AFFINE = [200, 100, 50]
ITERS_DEFORMABLE = [200, 100, 50]
CC_KERNEL = 5
LR_AFFINE = 3e-3
LR_DEFORMABLE = 0.5

out = _get_output_paths(output_prefix, xfm_type)

# 1. Moments (CC) – coarse init; MI unsupported in FireANTs _get_best_orientation
logger.info("1. Moments (CC)...")
moments = MomentsRegistration(
    scale=4.0,
    fixed_images=batch_fixed,
    moving_images=batch_moving,
    moments=1,
    loss_type="cc",
    cc_kernel_size=CC_KERNEL,
)
moments.optimize()

# 2. Rigid (MI)
logger.info("2. Rigid (MI)...")
rigid = RigidRegistration(
    scales=SCALES,
    iterations=ITERS_AFFINE,
    fixed_images=batch_fixed,
    moving_images=batch_moving,
    loss_type="mi",
    init_translation=moments.get_rigid_transl_init(),
    init_moment=moments.get_rigid_moment_init(),
    optimizer="Adam",
    optimizer_lr=LR_AFFINE,
    cc_kernel_size=CC_KERNEL,
)
rigid.optimize()

if xfm_type == "rigid":
    rigid.save_as_ants_transforms(out["forward"])
    _invert_affine_mat(out["forward"], out["inverse"], logger)
    _save_registered(rigid, batch_fixed, batch_moving, out["registered"], logger)
    logger.info("Done (rigid).")
else:
    # 3. Affine (MI)
    logger.info("3. Affine (MI)...")
    affine = AffineRegistration(
        scales=SCALES,
        iterations=ITERS_AFFINE,
        fixed_images=batch_fixed,
        moving_images=batch_moving,
        loss_type="mi",
        init_rigid=rigid.get_rigid_matrix(homogenous=False),
        optimizer="Adam",
        optimizer_lr=LR_AFFINE,
        cc_kernel_size=CC_KERNEL,
    )
    affine.optimize()

    if xfm_type == "affine":
        affine.save_as_ants_transforms(out["forward"])
        _invert_affine_mat(out["forward"], out["inverse"], logger)
        _save_registered(affine, batch_fixed, batch_moving, out["registered"], logger)
        logger.info("Done (affine).")
    else:
        # 4. Greedy (CC) – syn
        logger.info("4. Greedy (CC)...")
        greedy = GreedyRegistration(
            scales=SCALES,
            iterations=ITERS_DEFORMABLE,
            fixed_images=batch_fixed,
            moving_images=batch_moving,
            cc_kernel_size=CC_KERNEL,
            deformation_type="compositive",
            smooth_grad_sigma=1.0,
            optimizer="Adam",
            optimizer_lr=LR_DEFORMABLE,
            init_affine=affine.get_affine_matrix().detach(),
        )
        greedy.optimize()
        greedy.save_as_ants_transforms(out["forward"])
        _save_registered(greedy, batch_fixed, batch_moving, out["registered"], logger)

        # Inverse warp (moving → fixed)
        logger.info("Inverse registration (moving → fixed)...")
        affine_inv = AffineRegistration(
            scales=SCALES,
            iterations=ITERS_AFFINE,
            fixed_images=batch_moving,
            moving_images=batch_fixed,
            loss_type="mi",
            optimizer="Adam",
            optimizer_lr=LR_AFFINE,
            cc_kernel_size=CC_KERNEL,
        )
        affine_inv.optimize()
        greedy_inv = GreedyRegistration(
            scales=SCALES,
            iterations=ITERS_DEFORMABLE,
            fixed_images=batch_moving,
            moving_images=batch_fixed,
            cc_kernel_size=CC_KERNEL,
            deformation_type="compositive",
            smooth_grad_sigma=1.0,
            optimizer="Adam",
            optimizer_lr=LR_DEFORMABLE,
            init_affine=affine_inv.get_affine_matrix().detach(),
        )
        greedy_inv.optimize()
        greedy_inv.save_as_ants_transforms(out["inverse"])
        logger.info(f"Inverse warp: {out['inverse']}")

        logger.info("Done (syn).")

# %%
