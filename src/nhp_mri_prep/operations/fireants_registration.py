"""
FireANTs (GPU) registration for nhp_mri_prep.

Same interface and output contract as ants_cpu_register: returns paths to
registered image and transform files (.mat for rigid/affine, .nii.gz warp for syn).
Optional dependency: fireants, torch, scipy. When unavailable, use ants_cpu_register.
"""

import os
import re
import time
from dataclasses import dataclass, field
from typing import Union, Optional, Dict, Any, List

import numpy as np
import torch
import logging
from pathlib import Path

from fireants.io import BatchedImages, FakeBatchedImages, Image
from fireants.registration.affine import AffineRegistration
from fireants.registration.rigid import RigidRegistration
from fireants.registration.greedy import GreedyRegistration

from fireants.utils.globals import MIN_IMG_SIZE

from .validation import validate_input_file, ensure_working_directory
from ..utils.gpu_device import resolve_device
from ..utils.mri import pad_image_to_min_size, crop_image_to_original

try:
    from scipy.io import loadmat, savemat
except ImportError:
    loadmat = savemat = None

VALID_XFM_TYPES = ("translation", "rigid", "affine", "syn")

# Order of linear stages for the staged pipeline.
_LINEAR_STAGE_ORDER = ("translation", "rigid", "affine")


@dataclass
class FireANTsRegistrationParams:
    """FireANTs registration parameters (hardcoded defaults).

    The staged pipeline mirrors ANTs: translation → rigid → affine → SyN.
    Each linear stage initialises from the previous stage's result.

    Loss functions are chosen to match ANTs defaults:
    - Translation/Rigid/Affine stages use MI (Mutual Information) for
      cross-modality robustness.
    - SyN deformable stage uses CC (Cross-Correlation) for local structure
      capture, after the affine chain (which uses MI) has handled gross
      alignment.
    """
    scales: List[int] = field(default_factory=lambda: [4, 2, 1])
    iterations_translation: List[int] = field(default_factory=lambda: [500, 250, 100])
    iterations_affine: List[int] = field(default_factory=lambda: [500, 250, 100])
    iterations_deformable: List[int] = field(default_factory=lambda: [200, 100, 50])
    optimizer_affine: str = "Adam"
    optimizer_deformable: str = "Adam"
    lr_translation: float = 1e-1
    lr_rigid: float = 1e-2
    lr_affine: float = 3e-3
    lr_deformable: float = 0.5
    # Loss: MI for translation/rigid/affine (matches ANTs MI[fixed,moving,1,32,regular,0.25])
    loss_type_affine: str = "mi"
    mi_kernel_type: str = "gaussian"
    mi_num_bins: int = 32
    # Loss: CC for deformable (matches ANTs cc[fixed,moving,0.5,4,...])
    loss_type_deformable: str = "cc"
    cc_kernel_size: int = 5
    smooth_grad_sigma: float = 1.0
    deformation_type: str = "compositive"


DEFAULT_FIREANTS_PARAMS = FireANTsRegistrationParams()


class TranslationRegistration(RigidRegistration):
    """Translation-only registration (3 DOF in 3-D).

    Subclasses :class:`RigidRegistration` with rotation parameters frozen
    at identity, so only the translation vector is optimised.  Inherits
    ``save_as_ants_transforms()``, ``evaluate()``, and the full multi-scale
    optimisation loop from the parent.

    Overrides ``get_rigid_matrix()`` to build the homogeneous matrix
    directly from ``self.transl`` (identity rotation + translation).  This
    guarantees a clean autograd path: the gradient of the loss flows
    directly to ``self.transl`` without passing through the rotation
    computation.  ``self.rotation`` is excluded from the graph entirely,
    so the optimizer (which sees ``grad=None``) skips it automatically.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure rotation is at identity (zeros in the Lie-algebra
        # parameterisation).  It won't be updated because our overridden
        # get_rigid_matrix() never references it.
        self.rotation.data.zero_()
        if hasattr(self, 'logscale') and isinstance(self.logscale, torch.nn.Parameter):
            self.logscale.data.zero_()

    # ------------------------------------------------------------------
    def get_rigid_matrix(self, homogenous=True):
        """Return identity-rotation + translation matrix.

        Builds the matrix from ``self.transl`` alone, bypassing the
        parent's rotation computation.  For identity rotation the
        ``around_center`` correction vanishes (``center − I·center = 0``),
        so the output translation equals ``self.transl``.
        """
        dims = self.transl.shape[-1]
        batch = self.transl.shape[0]
        # Identity rotation block — no connection to self.rotation.
        eye = torch.eye(
            dims + 1, device=self.transl.device, dtype=self.transl.dtype,
        ).unsqueeze(0).expand(batch, -1, -1).clone()
        eye[:, :dims, -1] = self.transl
        if homogenous:
            return eye.contiguous()
        return eye[:, :dims, :].contiguous()


def _compute_safe_scales(
    fixed_shape: tuple,
    moving_shape: tuple,
    default_scales: List[int],
    default_iters: List[int],
    logger: logging.Logger,
) -> tuple:
    """Adapt multi-scale pyramid to image dimensions.

    FireANTs' ``downsample_fft`` assumes the target size is *smaller* than
    the source.  The actual downsampled size for dimension ``d`` at a given
    ``scale`` is ``max(d // scale, MIN_IMG_SIZE)``.  When this value is
    **≥ d** the operation becomes an upsample and the FFT crop + padding-
    removal produces a zero-length tensor (``ifftn`` raises
    ``RuntimeError: Invalid number of data points (0) specified``).

    A scale is safe as long as every spatial dimension of both images
    satisfies ``max(d // scale, MIN_IMG_SIZE) < d``.  In practice this
    means the dimension must be **> MIN_IMG_SIZE**; once that is true the
    clamped downsample is always strictly smaller than the original.

    Scale 1 is kept unconditionally (no downsampling).  Images with any
    dimension ≤ MIN_IMG_SIZE must be zero-padded beforehand — see the
    padding logic in ``fireants_registration()``.

    Returns:
        (safe_scales, safe_iters) with matching lengths.
    """
    all_dims = list(fixed_shape) + list(moving_shape)

    safe_scales: List[int] = []
    safe_iters: List[int] = []
    for scale, iters in zip(default_scales, default_iters):
        if scale <= 1:
            # Scale 1: no downsampling performed, always safe
            safe_scales.append(scale)
            safe_iters.append(iters)
        else:
            # Check that every dimension, after clamped downsampling, is
            # strictly smaller than the original (i.e. a true downsample).
            safe = all(
                max(d // scale, MIN_IMG_SIZE) < d for d in all_dims
            )
            if safe:
                safe_scales.append(scale)
                safe_iters.append(iters)
            else:
                # Find the problematic dimension for a helpful log message.
                bad = [(d, max(d // scale, MIN_IMG_SIZE))
                       for d in all_dims
                       if max(d // scale, MIN_IMG_SIZE) >= d]
                logger.info(
                    f"FireANTs: skipping scale {scale} "
                    f"(clamped downsample would not shrink: {bad})"
                )

    if not safe_scales:
        # All coarse levels were dropped — register at full resolution only
        safe_scales = [1]
        safe_iters = [default_iters[-1]]
        logger.warning(
            f"FireANTs: no multi-scale levels feasible for dims "
            f"fixed={list(fixed_shape)}, moving={list(moving_shape)}; "
            "using single-scale (scale=1) registration"
        )

    if safe_scales != default_scales:
        logger.info(
            f"FireANTs: adapted scales {default_scales} -> {safe_scales} "
            f"(iters {default_iters} -> {safe_iters}) "
            f"for image dims fixed={list(fixed_shape)}, moving={list(moving_shape)}"
        )

    return safe_scales, safe_iters


def _run_affine_registration(
    registration: Union[AffineRegistration, RigidRegistration],
    device: str,
    logger: logging.Logger,
    reg_type: str = "affine",
) -> float:
    start = time.perf_counter()
    registration.optimize()
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    logger.info(f"{reg_type.capitalize()} registration: {elapsed:.1f}s")
    return elapsed


def _run_greedy_registration(
    registration: GreedyRegistration,
    device: str,
    logger: logging.Logger,
    direction: str = "forward",
) -> float:
    start = time.perf_counter()
    registration.optimize()
    if device.startswith("cuda"):
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    logger.info(f"{direction.capitalize()} deformable registration: {elapsed:.1f}s")
    return elapsed


def _save_registered_image(
    registration: Union[AffineRegistration, RigidRegistration, GreedyRegistration],
    batch_fixed: BatchedImages,
    batch_moving: BatchedImages,
    output_path: Union[str, Path],
    logger: logging.Logger,
) -> None:
    moved = registration.evaluate(batch_fixed, batch_moving)
    moved_batch = FakeBatchedImages(moved, batch_fixed)
    moved_batch.write_image(str(output_path))
    logger.info(f"Wrote registered image: {output_path}")


def _get_output_paths(output_path_prefix: str, xfm_type: str) -> Dict[str, str]:
    output_dir = Path(output_path_prefix).parent
    base_name = Path(output_path_prefix).name
    paths = {"registered": str(output_dir / f"{base_name}_registered.nii.gz")}
    if xfm_type == "syn":
        paths["forward_transform"] = str(output_dir / f"{base_name}_warp.nii.gz")
        paths["inverse_transform"] = str(output_dir / f"{base_name}_inverse_warp.nii.gz")
    else:
        suffix = xfm_type  # "translation", "rigid", or "affine"
        paths["forward_transform"] = str(output_dir / f"{base_name}_{suffix}.mat")
        paths["inverse_transform"] = str(output_dir / f"{base_name}_inverse_{suffix}.mat")
    return paths


def _invert_affine_mat(
    affine_mat_path: Union[str, Path],
    inverse_mat_path: Union[str, Path],
    logger: logging.Logger,
) -> None:
    """Compute inverse of an ITK-style affine .mat and write to inverse_mat_path."""
    if loadmat is None or savemat is None:
        raise RuntimeError("scipy is required to invert affine .mat (pip install scipy)")
    data = loadmat(str(affine_mat_path))
    key = [k for k in data if k.startswith("AffineTransform_") and not k.startswith("__")]
    if not key:
        raise ValueError(f"No AffineTransform_* key found in {affine_mat_path}")
    key = key[0]
    params = data[key].flatten().astype(np.float64)
    original_shape = data[key].shape
    original_dtype = data[key].dtype
    total_params = params.size
    if total_params == 12:
        dims = 3
    elif total_params == 6:
        dims = 2
    else:
        match = re.search(r'_(\d+)_\d+', key)
        if match:
            dims = int(match.group(1))
            expected_params = dims * dims + dims
            if total_params != expected_params:
                raise ValueError(
                    f"Parameter count mismatch: got {total_params}, expected {expected_params} for {dims}D transform"
                )
        else:
            raise ValueError(
                f"Cannot infer dimensions from parameter count {total_params}. Expected 6 (2D) or 12 (3D)."
            )
    matrix_size = dims * dims
    A_flat = params[:matrix_size]
    t = params[matrix_size:]
    A = A_flat.reshape(dims, dims)
    A_inv = np.linalg.inv(A)
    t_inv = -A_inv @ t
    A_inv_flat = A_inv.flatten()
    params_inv = np.concatenate([A_inv_flat, t_inv])
    params_inv = params_inv.astype(original_dtype)
    mat_inv = params_inv.reshape(-1, 1) if original_shape[1] == 1 else params_inv
    output_data = {}
    for k, v in data.items():
        if k.startswith("__"):
            continue
        if k == key:
            output_data[k] = mat_inv
        else:
            output_data[k] = v
    if "fixed" not in output_data:
        output_data["fixed"] = np.zeros((dims, 1), dtype=np.float32)
    saved = False
    for fmt in ['4', '5']:
        try:
            savemat(str(inverse_mat_path), output_data, format=fmt, oned_as='column')
            saved = True
            break
        except (ValueError, NotImplementedError):
            continue
    if not saved:
        savemat(str(inverse_mat_path), output_data, oned_as='column')
    logger.info(f"Wrote inverse affine: {inverse_mat_path}")


def _compute_com_init_translation(
    batch_fixed: BatchedImages,
    batch_moving: BatchedImages,
    logger: logging.Logger,
) -> torch.Tensor:
    """Compute centre-of-mass offset between fixed and moving images.

    Mimics ANTs' ``--initial-moving-transform [fixed,moving,1]`` (centre-of-
    mass alignment).  The offset is returned in **physical (world)
    coordinates**, ready for use as ``init_translation`` in
    :class:`RigidRegistration` or :class:`TranslationRegistration`.

    Returns:
        Tensor of shape ``[N, D]`` (physical-space translation).
    """

    def _com_physical(batch_images: BatchedImages) -> torch.Tensor:
        """Centre of mass in physical coordinates for a single-image batch."""
        img = batch_images()  # [N, C, *spatial_dims]
        data = img[0, 0]      # first batch, first channel
        dims = data.ndim

        # Build coordinate grids in normalised [-1, 1] space (matches the
        # torch coordinate system that FireANTs uses internally).
        grids = []
        for i, s in enumerate(data.shape):
            coords = torch.linspace(-1, 1, s, device=data.device, dtype=data.dtype)
            view_shape = [1] * dims
            view_shape[i] = s
            grids.append(coords.view(*view_shape))

        weights = data.clamp(min=0)
        total_weight = weights.sum()
        if total_weight < 1e-8:
            # Degenerate: fall back to geometric centre (origin of normalised
            # space → physical centre via torch2phy).
            com_norm = torch.zeros(dims, device=data.device, dtype=data.dtype)
        else:
            com_norm = torch.stack(
                [(weights * g).sum() / total_weight for g in grids]
            )

        # Normalised → physical via the image's torch2phy matrix.
        torch2phy = batch_images.get_torch2phy()[0]  # [dim+1, dim+1]
        com_homo = torch.cat([com_norm, torch.ones(1, device=data.device, dtype=data.dtype)])
        com_phy = (torch2phy @ com_homo)[:dims]
        return com_phy

    fixed_com = _com_physical(batch_fixed)
    moving_com = _com_physical(batch_moving)
    # Pull convention (fixed→moving): the translation maps a point in
    # fixed space to the corresponding point in moving space, so the
    # offset is  moving_COM − fixed_COM.
    offset = (moving_com - fixed_com).unsqueeze(0)  # [1, D]
    logger.info(
        f"Centre-of-mass alignment: "
        f"fixed COM={fixed_com.tolist()}, "
        f"moving COM={moving_com.tolist()}, "
        f"offset={offset.squeeze().tolist()}"
    )
    return offset


def _run_linear_stages(
    batch_fixed: BatchedImages,
    batch_moving: BatchedImages,
    target_type: str,
    params: FireANTsRegistrationParams,
    fixed_shape: tuple,
    moving_shape: tuple,
    device: str,
    logger: logging.Logger,
    work_dir: Optional[Union[str, Path]] = None,
) -> tuple:
    """Run the staged linear registration chain: translation → rigid → affine.

    Each stage is initialised from the previous stage's result.  The chain
    stops at *target_type* (inclusive).  For example ``target_type='affine'``
    runs translation → rigid → affine.

    Args:
        batch_fixed: Fixed images.
        batch_moving: Moving images.
        target_type: Stop after this stage (``'translation'``, ``'rigid'``,
            or ``'affine'``).
        params: Registration parameters.
        fixed_shape: Spatial dims of fixed image (for safe-scale computation).
        moving_shape: Spatial dims of moving image.
        device: Torch device string.
        logger: Logger.
        work_dir: Working directory for debug outputs (optional).

    Returns:
        ``(final_reg, final_mat)`` — the last-stage registration object and
        its 4×4 homogeneous matrix (detached tensor).
    """
    target_idx = _LINEAR_STAGE_ORDER.index(target_type)
    stages = _LINEAR_STAGE_ORDER[:target_idx + 1]

    # Safe scales — translation may use different iterations from rigid/affine.
    scales_trans, iters_trans = _compute_safe_scales(
        fixed_shape, moving_shape,
        params.scales, params.iterations_translation, logger,
    )
    scales_lin, iters_lin = _compute_safe_scales(
        fixed_shape, moving_shape,
        params.scales, params.iterations_affine, logger,
    )

    mi_kwargs_base = dict(
        loss_type=params.loss_type_affine,
        mi_kernel_type=params.mi_kernel_type,
        loss_params={"num_bins": params.mi_num_bins},
        optimizer=params.optimizer_affine,
    )

    # Centre-of-mass pre-alignment (analogous to ANTs' initial moving
    # transform).  Provides a good starting point for the translation
    # stage so the optimiser does not get stuck in a local minimum.
    com_offset = _compute_com_init_translation(batch_fixed, batch_moving, logger)

    final_reg = None
    prev_mat = None  # [N, dim+1, dim+1] homogeneous matrix

    for stage in stages:
        logger.info(f"Running {stage} stage...")

        if stage == "translation":
            reg = TranslationRegistration(
                scales_trans, iters_trans,
                batch_fixed, batch_moving,
                init_translation=com_offset,
                optimizer_lr=params.lr_translation,
                # Relax convergence: MI loss changes slowly for translation,
                # default tolerance (1e-6) causes early stopping too soon.
                tolerance=1e-10,
                max_tolerance_iters=50,
                **mi_kwargs_base,
            )

            _run_affine_registration(reg, device, logger, reg_type="translation")
            prev_mat = reg.get_rigid_matrix(homogenous=True).detach()

        elif stage == "rigid":
            # Initialise from translation result.
            init_t = prev_mat[:, :-1, -1]  # [N, D] world-space translation
            reg = RigidRegistration(
                scales_lin, iters_lin,
                batch_fixed, batch_moving,
                init_translation=init_t,
                optimizer_lr=params.lr_rigid,
                **mi_kwargs_base,
            )
            _run_affine_registration(reg, device, logger, reg_type="rigid")
            prev_mat = reg.get_rigid_matrix(homogenous=True).detach()

        elif stage == "affine":
            # Initialise from rigid (or translation) result.
            reg = AffineRegistration(
                scales_lin, iters_lin,
                batch_fixed, batch_moving,
                init_rigid=prev_mat,
                optimizer_lr=params.lr_affine,
                **mi_kwargs_base,
            )
            _run_affine_registration(reg, device, logger, reg_type="affine")
            prev_mat = reg.get_affine_matrix(homogenous=True).detach()

        final_reg = reg

    return final_reg, prev_mat


def fireants_registration(
    fixedf: Union[str, Path],
    movingf: Union[str, Path],
    working_dir: Union[str, Path],
    output_prefix: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None,
    xfm_type: Optional[str] = 'syn',
    compute_inverse: Optional[bool] = True,
) -> Dict[str, Optional[str]]:
    """Run FireANTs (GPU) registration with same output format as ants_cpu_register.

    The pipeline mirrors ANTs by running staged linear registration
    (translation → rigid → affine) before the optional deformable (SyN)
    stage.  Each linear stage initialises from the previous stage's result.

    Args:
        fixedf: Fixed (template) image path.
        movingf: Moving image path.
        working_dir: Working directory.
        output_prefix: Prefix for output files (default: basename of moving
            without .nii.gz).
        config: Configuration dictionary (optional; only used to get
            xfm_type if not provided).
        logger: Logger instance (optional).
        xfm_type: One of ``'translation'``, ``'rigid'``, ``'affine'``,
            ``'syn'``.
        compute_inverse: If *True* (default), compute the inverse transform.

    Returns:
        Dictionary with keys: ``output_path_prefix``,
        ``imagef_registered``, ``forward_transform``,
        ``inverse_transform``.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    if output_prefix is None:
        output_prefix = os.path.basename(movingf).replace('.nii.gz', '').replace('.nii', '')
    if xfm_type is None and config is not None:
        reg_config = config.get("registration", {})
        xfm_type = reg_config.get("xfm_type", "syn")
    if xfm_type is None:
        xfm_type = "syn"
    if xfm_type not in VALID_XFM_TYPES:
        raise ValueError(f"Invalid xfm_type: {xfm_type}. Must be one of {VALID_XFM_TYPES}")

    work_dir = ensure_working_directory(working_dir, logger)
    output_path_prefix = os.path.join(str(work_dir), output_prefix)
    logger.info(f"Data: output prefix - {output_prefix}")

    fixed_path = validate_input_file(fixedf, logger)
    moving_path = validate_input_file(movingf, logger)

    outputs: Dict[str, Optional[str]] = {
        "output_path_prefix": output_path_prefix,
        "imagef_registered": None,
        "forward_transform": None,
        "inverse_transform": None,
    }
    output_paths = _get_output_paths(output_path_prefix, xfm_type)

    # ------------------------------------------------------------------
    # Pad images to MIN_IMG_SIZE if needed.
    #
    # FireANTs' GreedyRegistration.optimize() clamps the internal warp-
    # field grid to MIN_IMG_SIZE per dimension, but at scale=1 it does
    # NOT resize the fixed image to match.  This causes a shape mismatch
    # in the loss when any fixed-image spatial dim < MIN_IMG_SIZE.
    # Since either image can be the "fixed" (forward vs inverse), both
    # must satisfy the constraint.  Padding is transparent to the caller:
    # all outputs are cropped back to the original grids before return.
    # ------------------------------------------------------------------
    original_fixed_path = fixed_path
    original_moving_path = moving_path

    padded_fixed_f = os.path.join(str(work_dir), '_padded_fixed.nii.gz')
    fixed_pad_left = pad_image_to_min_size(fixed_path, MIN_IMG_SIZE, padded_fixed_f, logger)
    if fixed_pad_left is not None:
        fixed_path = Path(padded_fixed_f)

    padded_moving_f = os.path.join(str(work_dir), '_padded_moving.nii.gz')
    moving_pad_left = pad_image_to_min_size(moving_path, MIN_IMG_SIZE, padded_moving_f, logger)
    if moving_pad_left is not None:
        moving_path = Path(padded_moving_f)

    gpu_spec = "auto"
    if config is not None:
        gpu_spec = config.get("general", {}).get("gpu_device", "auto")
    dev = resolve_device(gpu_spec)
    device = str(dev)  # "cuda:0", "cpu", or "mps"
    if device == "cpu":
        logger.warning("Using CPU for FireANTs registration.")

    fixed_image = Image.load_file(str(fixed_path))
    moving_image = Image.load_file(str(moving_path))
    batch_fixed = BatchedImages([fixed_image])
    batch_moving = BatchedImages([moving_image])
    params = DEFAULT_FIREANTS_PARAMS

    fixed_shape = tuple(batch_fixed().shape[2:])
    moving_shape = tuple(batch_moving().shape[2:])
    logger.info(f"FireANTs: fixed shape={list(fixed_shape)}, moving shape={list(moving_shape)}")

    # ------------------------------------------------------------------
    # Staged linear registration: translation → rigid → affine
    # For SyN the full linear chain runs up to affine; for other types
    # the chain stops at the requested xfm_type.
    # ------------------------------------------------------------------
    linear_target = xfm_type if xfm_type != "syn" else "affine"
    final_reg, final_mat = _run_linear_stages(
        batch_fixed, batch_moving, linear_target, params,
        fixed_shape, moving_shape, device, logger,
        work_dir=work_dir,
    )

    if xfm_type in ("translation", "rigid", "affine"):
        # --- Linear-only: save the final .mat and its analytical inverse ---
        forward_mat_path = output_paths["forward_transform"]
        final_reg.save_as_ants_transforms(forward_mat_path)
        logger.info(f"Saved forward {xfm_type} transform: {forward_mat_path}")
        if compute_inverse:
            _invert_affine_mat(forward_mat_path, output_paths["inverse_transform"], logger)
        _save_registered_image(
            final_reg, batch_fixed, batch_moving,
            output_paths["registered"], logger,
        )
    else:
        # --- SyN: deformable registration on top of the affine chain ---
        scales_deformable, iters_deformable = _compute_safe_scales(
            fixed_shape, moving_shape,
            params.scales, params.iterations_deformable, logger,
        )
        greedy_kwargs = dict(
            loss_type=params.loss_type_deformable,
            cc_kernel_size=params.cc_kernel_size,
            deformation_type=params.deformation_type,
            smooth_grad_sigma=params.smooth_grad_sigma,
            optimizer=params.optimizer_deformable,
            optimizer_lr=params.lr_deformable,
        )

        # Forward deformable
        logger.info("Running forward deformable registration...")
        fwd_greedy = GreedyRegistration(
            scales=scales_deformable,
            iterations=iters_deformable,
            fixed_images=batch_fixed,
            moving_images=batch_moving,
            init_affine=final_mat,
            **greedy_kwargs,
        )
        _run_greedy_registration(fwd_greedy, device, logger, direction="forward")
        fwd_greedy.save_as_ants_transforms(output_paths["forward_transform"])
        logger.info(f"Saved forward warp: {output_paths['forward_transform']}")

        # Inverse deformable (analytical affine inverse + swapped images)
        if compute_inverse:
            inv_affine_mat = torch.inverse(final_mat)
            logger.info(
                "Running inverse deformable registration "
                "(analytical affine inverse + swapped deformable)..."
            )
            inv_greedy = GreedyRegistration(
                scales=scales_deformable,
                iterations=iters_deformable,
                fixed_images=batch_moving,
                moving_images=batch_fixed,
                init_affine=inv_affine_mat,
                **greedy_kwargs,
            )
            _run_greedy_registration(inv_greedy, device, logger, direction="inverse")
            inv_greedy.save_as_ants_transforms(output_paths["inverse_transform"])
            logger.info(f"Saved inverse warp: {output_paths['inverse_transform']}")

        _save_registered_image(
            fwd_greedy, batch_fixed, batch_moving,
            output_paths["registered"], logger,
        )

    # ------------------------------------------------------------------
    # Crop outputs back to original input grids if padding was applied.
    # Forward warp + registered image live in fixed-image space;
    # inverse warp lives in moving-image space.
    # Only NIfTI files need cropping (.mat affine transforms are grid-
    # independent).
    # ------------------------------------------------------------------
    if fixed_pad_left is not None:
        for p in [output_paths.get("registered"), output_paths.get("forward_transform")]:
            if p and p.endswith('.nii.gz') and os.path.exists(p):
                crop_image_to_original(p, str(original_fixed_path), fixed_pad_left, p, logger)
    if moving_pad_left is not None and compute_inverse:
        p = output_paths.get("inverse_transform")
        if p and p.endswith('.nii.gz') and os.path.exists(p):
            crop_image_to_original(p, str(original_moving_path), moving_pad_left, p, logger)

    # Clean up temporary padded files
    for tmp in [padded_fixed_f, padded_moving_f]:
        if os.path.exists(tmp):
            os.remove(tmp)

    for key, path in [("imagef_registered", output_paths["registered"]),
                      ("forward_transform", output_paths["forward_transform"]),
                      ("inverse_transform", output_paths["inverse_transform"] if compute_inverse else None)]:
        if path is not None and os.path.exists(path):
            outputs[key] = path
            logger.info(f"Output: {key} created - {path}")
        elif path is not None:
            logger.warning(f"Data: expected {key} not found - {path}")

    logger.info(f"Step: registration completed with {len([k for k, v in outputs.items() if v is not None])} output files - {list(outputs.keys())}")
    return outputs
