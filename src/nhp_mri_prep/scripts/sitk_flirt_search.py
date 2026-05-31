"""FLIRT-faithful rigid search + schedule for SimpleITK (ports flirt.cc search_cost)."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import SimpleITK as sitk

logger = logging.getLogger("test_anat_conformation")

_SITK_SEARCH_RANGE_DEG = (-180.0, 180.0)
_SITK_STAGE1_TARGET_MM = 8.0
_SITK_STAGE4_TARGET_MM = 4.0
_SITK_SCHEDULE_SCALES_MM = (4.0, 2.0, 1.0)
_SITK_FLIRT_TOP_K = 10
_SITK_TRANSLATION_REFINE_CONVERGENCE = 1e-4


def _unwrap_euler3d(tx: sitk.Transform) -> sitk.Euler3DTransform:
    if isinstance(tx, sitk.Euler3DTransform):
        return tx
    inner: sitk.Transform = (
        tx.GetNthTransform(0) if isinstance(tx, sitk.CompositeTransform) else tx
    )
    result = sitk.Euler3DTransform()
    result.SetParameters(inner.GetParameters())
    result.SetFixedParameters(inner.GetFixedParameters())
    return result


def _set_sitk_metric(
    reg: sitk.ImageRegistrationMethod,
    sitk_config: dict[str, Any],
    *,
    search_stage: bool = False,
    schedule_stage: bool = False,
) -> None:
    if schedule_stage:
        metric = sitk_config.get("schedule_metric", sitk_config.get("search_metric", "Correlation"))
    elif search_stage:
        metric = sitk_config.get("search_metric", sitk_config["metric"])
    else:
        metric = sitk_config["metric"]
    if metric == "Correlation":
        reg.SetMetricAsCorrelation()
    elif metric == "MattesMI":
        bins = int(sitk_config.get("number_of_histogram_bins", 32))
        reg.SetMetricAsMattesMutualInformation(bins)
    else:
        raise ValueError(f"Unknown SimpleITK metric: {metric}")


def _sitk_min_spacing(img: sitk.Image) -> float:
    return float(min(img.GetSpacing()))


def _sitk_shrink_for_target_mm(img: sitk.Image, target_mm: float) -> int:
    return max(1, int(round(target_mm / _sitk_min_spacing(img))))


def _sitk_apply_sampling(
    reg: sitk.ImageRegistrationMethod, sitk_config: dict[str, Any], modality: str, *, heavy: bool = False
) -> None:
    pct = float(sitk_config.get("search_sampling_pct", 0.2))
    if heavy and modality == "func":
        pct = max(pct, 0.25)
    reg.SetMetricSamplingPercentage(pct)
    reg.SetMetricSamplingStrategy(reg.RANDOM)


def _sitk_rotation_samples_deg(deg_min: float, deg_max: float, step_deg: float) -> np.ndarray:
    """Mirror FLIRT set_rot_sampling / set_rot_samplings grid size."""
    span = float(deg_max - deg_min)
    n_pts = max(1, int(round(span / step_deg)) + 1)
    if n_pts == 1:
        return np.array([0.5 * (deg_min + deg_max)])
    return np.linspace(deg_min, deg_max, n_pts)


def _sitk_image_cog_mm(img: sitk.Image) -> np.ndarray:
    arr = sitk.GetArrayFromImage(img).astype(np.float64)
    weights = np.maximum(arr, 0.0)
    total = float(weights.sum())
    if total <= 0:
        idx = [(float(s) - 1.0) / 2.0 for s in img.GetSize()]
        return np.array(img.TransformContinuousIndexToPhysicalPoint(idx), dtype=np.float64)
    z_idx, y_idx, x_idx = np.indices(weights.shape)
    cz = float((weights * z_idx).sum() / total)
    cy = float((weights * y_idx).sum() / total)
    cx = float((weights * x_idx).sum() / total)
    return np.array(
        img.TransformContinuousIndexToPhysicalPoint((cx, cy, cz)), dtype=np.float64
    )


def _sitk_fixed_geometric_center(fixed: sitk.Image) -> tuple[float, float, float]:
    return fixed.TransformContinuousIndexToPhysicalPoint(
        [(float(sz) - 1.0) / 2.0 for sz in fixed.GetSize()]
    )


def _sitk_euler_from_rot_trans(
    center: tuple[float, float, float],
    rx_rad: float,
    ry_rad: float,
    rz_rad: float,
    tx_param: float,
    ty_param: float,
    tz_param: float,
) -> sitk.Euler3DTransform:
    tx_obj = sitk.Euler3DTransform()
    tx_obj.SetCenter(center)
    tx_obj.SetParameters([rx_rad, ry_rad, rz_rad, tx_param, ty_param, tz_param])
    return tx_obj


def _sitk_flirt_cog_seed(
    fixed: sitk.Image,
    moving: sitk.Image,
    center: tuple[float, float, float],
    rx_rad: float,
    ry_rad: float,
    rz_rad: float,
) -> sitk.Euler3DTransform:
    """FLIRT search_cost COG init: trans = ref_cog - R @ mov_cog (centered Euler)."""
    ref_cog = _sitk_image_cog_mm(fixed)
    mov_cog = _sitk_image_cog_mm(moving)
    rot_tx = _sitk_euler_from_rot_trans(center, rx_rad, ry_rad, rz_rad, 0.0, 0.0, 0.0)
    rotation = np.array(rot_tx.GetMatrix(), dtype=np.float64).reshape(3, 3)
    c = np.array(center, dtype=np.float64)
    t_param = ref_cog - rotation @ (mov_cog - c) - c
    return _sitk_euler_from_rot_trans(
        center, rx_rad, ry_rad, rz_rad, float(t_param[0]), float(t_param[1]), float(t_param[2])
    )


def _sitk_refine_translation_only(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    *,
    learning_rate_mm: float,
    iters: int,
) -> tuple[sitk.Euler3DTransform, float]:
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, search_stage=True)
    reg.SetInterpolator(sitk.sitkLinear)
    _sitk_apply_sampling(reg, sitk_config, modality, heavy=True)
    reg.SetOptimizerAsGradientDescent(
        learningRate=learning_rate_mm,
        numberOfIterations=iters,
        convergenceMinimumValue=_SITK_TRANSLATION_REFINE_CONVERGENCE,
        convergenceWindowSize=5,
    )
    reg.SetOptimizerScales([1e6, 1e6, 1e6, 1.0, 1.0, 1.0])
    reg.SetInitialTransform(init_tx, inPlace=False)
    refined = _unwrap_euler3d(reg.Execute(fixed, moving))
    return refined, float(reg.GetMetricValue())


def _sitk_eval_metric(
    fixed: sitk.Image,
    moving: sitk.Image,
    tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
) -> float:
    """Evaluate search metric at tx without moving parameters (ITK needs >=1 iter)."""
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, search_stage=True)
    reg.SetInterpolator(sitk.sitkLinear)
    _sitk_apply_sampling(reg, sitk_config, modality)
    reg.SetOptimizerAsGradientDescent(
        learningRate=0.0,
        numberOfIterations=1,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=1,
    )
    # Freeze all DOF so the single iteration only samples the metric at init.
    reg.SetOptimizerScales([1e6] * 6)
    reg.SetInitialTransform(tx, inPlace=False)
    reg.Execute(fixed, moving)
    return float(reg.GetMetricValue())


def _trilinear_interp_volumes(
    tx_vol: np.ndarray,
    ty_vol: np.ndarray,
    tz_vol: np.ndarray,
    xf: float,
    yf: float,
    zf: float,
) -> tuple[float, float, float]:
    """Trilinear interp in rotation-index space (FLIRT tx.interpolate)."""

    def _interp(vol: np.ndarray, x: float, y: float, z: float) -> float:
        nx, ny, nz = vol.shape
        if nx <= 1 or ny <= 1 or nz <= 1:
            return float(vol[0, 0, 0])
        x = float(np.clip(x, 0.0, nx - 1.001))
        y = float(np.clip(y, 0.0, ny - 1.001))
        z = float(np.clip(z, 0.0, nz - 1.001))
        x0, y0, z0 = int(np.floor(x)), int(np.floor(y)), int(np.floor(z))
        x1 = min(x0 + 1, nx - 1)
        y1 = min(y0 + 1, ny - 1)
        z1 = min(z0 + 1, nz - 1)
        xd, yd, zd = x - x0, y - y0, z - z0
        c000, c100 = vol[x0, y0, z0], vol[x1, y0, z0]
        c010, c110 = vol[x0, y1, z0], vol[x1, y1, z0]
        c001, c101 = vol[x0, y0, z1], vol[x1, y0, z1]
        c011, c111 = vol[x0, y1, z1], vol[x1, y1, z1]
        c00 = c000 * (1 - xd) + c100 * xd
        c10 = c010 * (1 - xd) + c110 * xd
        c01 = c001 * (1 - xd) + c101 * xd
        c11 = c011 * (1 - xd) + c111 * xd
        c0 = c00 * (1 - yd) + c10 * yd
        c1 = c01 * (1 - yd) + c11 * yd
        return float(c0 * (1 - zd) + c1 * zd)

    return _interp(tx_vol, xf, yf, zf), _interp(ty_vol, xf, yf, zf), _interp(tz_vol, xf, yf, zf)


def _sitk_copy_euler(tx: sitk.Euler3DTransform) -> sitk.Euler3DTransform:
    out = sitk.Euler3DTransform()
    out.SetFixedParameters(tx.GetFixedParameters())
    out.SetParameters(tx.GetParameters())
    return out


def _sitk_flirt_search_cost(
    fixed_8: sitk.Image,
    moving_8: sitk.Image,
    fixed_4: sitk.Image,
    moving_4: sitk.Image,
    sitk_config: dict[str, Any],
    modality: str,
) -> list[tuple[float, sitk.Euler3DTransform]]:
    """Port of FLIRT search_cost + optimise_strategy3 candidate list."""
    t0 = time.perf_counter()
    deg_min, deg_max = sitk_config.get("search_range_deg", _SITK_SEARCH_RANGE_DEG)
    coarse_step = float(sitk_config["coarse_step_deg"])
    fine_step = float(sitk_config["fine_step_deg"])
    tx_iters = int(sitk_config.get("search_tx_iters", 50))
    cost_frac = float(sitk_config.get("cost_thresh_fraction", 0.2))
    lr_tx = _sitk_min_spacing(fixed_8) * 0.5

    center = _sitk_fixed_geometric_center(fixed_8)
    rx_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    ry_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    rz_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    nx, ny, nz = len(rx_c), len(ry_c), len(rz_c)
    tx_vol = np.zeros((nx, ny, nz), dtype=np.float64)
    ty_vol = np.zeros((nx, ny, nz), dtype=np.float64)
    tz_vol = np.zeros((nx, ny, nz), dtype=np.float64)

    logger.info(
        "FLIRT search coarse: %dx%dx%d rotations @ ~%.1f mm, tx_iters=%d",
        nx,
        ny,
        nz,
        _sitk_min_spacing(fixed_8) * _sitk_shrink_for_target_mm(fixed_8, _SITK_STAGE1_TARGET_MM),
        tx_iters,
    )
    n_coarse = 0
    for ix, rx in enumerate(rx_c):
        for iy, ry in enumerate(ry_c):
            for iz, rz in enumerate(rz_c):
                seed = _sitk_flirt_cog_seed(
                    fixed_8, moving_8, center, np.deg2rad(rx), np.deg2rad(ry), np.deg2rad(rz)
                )
                refined, _ = _sitk_refine_translation_only(
                    fixed_8,
                    moving_8,
                    seed,
                    sitk_config,
                    modality,
                    learning_rate_mm=lr_tx,
                    iters=tx_iters,
                )
                params = list(refined.GetParameters())
                tx_vol[ix, iy, iz] = params[3]
                ty_vol[ix, iy, iz] = params[4]
                tz_vol[ix, iy, iz] = params[5]
                n_coarse += 1
    logger.info(
        "FLIRT search coarse done: %d cells in %.1f s",
        n_coarse,
        time.perf_counter() - t0,
    )

    t1 = time.perf_counter()
    rx_f = _sitk_rotation_samples_deg(deg_min, deg_max, fine_step)
    ry_f = _sitk_rotation_samples_deg(deg_min, deg_max, fine_step)
    rz_f = _sitk_rotation_samples_deg(deg_min, deg_max, fine_step)
    fx = (nx - 1) / max(1.0, len(rx_f) - 1)
    fy = (ny - 1) / max(1.0, len(ry_f) - 1)
    fz = (nz - 1) / max(1.0, len(rz_f) - 1)
    costs = np.zeros((len(rx_f), len(ry_f), len(rz_f)), dtype=np.float64)
    logger.info(
        "FLIRT search fine cost grid: %dx%dx%d @ ~%.1f mm",
        len(rx_f),
        len(ry_f),
        len(rz_f),
        _sitk_min_spacing(fixed_4) * _sitk_shrink_for_target_mm(fixed_4, _SITK_STAGE4_TARGET_MM),
    )
    for ix, rx in enumerate(rx_f):
        for iy, ry in enumerate(ry_f):
            for iz, rz in enumerate(rz_f):
                txv, tyv, tzv = _trilinear_interp_volumes(
                    tx_vol, ty_vol, tz_vol, ix * fx, iy * fy, iz * fz
                )
                tx_init = _sitk_euler_from_rot_trans(
                    center,
                    np.deg2rad(rx),
                    np.deg2rad(ry),
                    np.deg2rad(rz),
                    txv,
                    tyv,
                    tzv,
                )
                costs[ix, iy, iz] = _sitk_eval_metric(
                    fixed_4, moving_4, tx_init, sitk_config, modality
                )
    cost_min = float(costs.min())
    cost_max = float(costs.max())
    p20 = float(np.percentile(costs, 20))
    thresh = min(cost_min + cost_frac * (cost_max - cost_min), p20)
    if thresh <= cost_min:
        thresh = max(cost_min * 1.0001, cost_min + 1e-9)
    survivors = int(np.sum(costs <= thresh))
    logger.info(
        "FLIRT search fine costs: min=%.6f max=%.6f thresh=%.6f survivors=%d (%.1f s)",
        cost_min,
        cost_max,
        thresh,
        survivors,
        time.perf_counter() - t1,
    )

    t2 = time.perf_counter()
    results: list[tuple[float, sitk.Euler3DTransform]] = []
    if survivors <= 0:
        ix, iy, iz = np.unravel_index(int(np.argmin(costs)), costs.shape)
        rx, ry, rz = rx_f[ix], ry_f[iy], rz_f[iz]
        txv, tyv, tzv = _trilinear_interp_volumes(tx_vol, ty_vol, tz_vol, ix * fx, iy * fy, iz * fz)
        seed = _sitk_euler_from_rot_trans(
            center, np.deg2rad(rx), np.deg2rad(ry), np.deg2rad(rz), txv, tyv, tzv
        )
        refined, m = _sitk_refine_translation_only(
            fixed_4, moving_4, seed, sitk_config, modality, learning_rate_mm=lr_tx, iters=tx_iters
        )
        results.append((m, refined))
    else:
        for ix, rx in enumerate(rx_f):
            for iy, ry in enumerate(ry_f):
                for iz, rz in enumerate(rz_f):
                    if costs[ix, iy, iz] > thresh:
                        continue
                    txv, tyv, tzv = _trilinear_interp_volumes(
                        tx_vol, ty_vol, tz_vol, ix * fx, iy * fy, iz * fz
                    )
                    seed = _sitk_euler_from_rot_trans(
                        center,
                        np.deg2rad(rx),
                        np.deg2rad(ry),
                        np.deg2rad(rz),
                        txv,
                        tyv,
                        tzv,
                    )
                    refined, m = _sitk_refine_translation_only(
                        fixed_4,
                        moving_4,
                        seed,
                        sitk_config,
                        modality,
                        learning_rate_mm=lr_tx,
                        iters=tx_iters,
                    )
                    results.append((m, refined))
    results.sort(key=lambda x: x[0])
    logger.info(
        "FLIRT search fine refine: %d poses in %.1f s (total %.1f s)",
        len(results),
        time.perf_counter() - t2,
        time.perf_counter() - t0,
    )
    return results[:_SITK_FLIRT_TOP_K]


def _sitk_rigid_refine_at_scale(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    target_mm: float,
    iters: int,
) -> sitk.Euler3DTransform:
    shrink = _sitk_shrink_for_target_mm(fixed, target_mm)
    shrink_factors = [shrink]
    sigmas = [max(0.0, target_mm / 2.0)]
    lr = _sitk_min_spacing(fixed) * 0.5 * float(sitk_config.get("learning_rate", 1.0))

    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, schedule_stage=True)
    reg.SetInterpolator(sitk.sitkLinear)
    _sitk_apply_sampling(reg, sitk_config, modality, heavy=True)
    reg.SetOptimizerAsGradientDescent(
        learningRate=lr,
        numberOfIterations=iters,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10,
    )
    reg.SetOptimizerScalesFromPhysicalShift()
    reg.SetShrinkFactorsPerLevel(shrink_factors)
    reg.SetSmoothingSigmasPerLevel(sigmas)
    reg.SetSmoothingSigmasAreSpecifiedInPhysicalUnits(True)
    reg.SetInitialTransform(init_tx, inPlace=False)
    init_metric = _sitk_eval_metric(fixed, moving, init_tx, sitk_config, modality)
    out_tx = _unwrap_euler3d(reg.Execute(fixed, moving))
    out_metric = float(reg.GetMetricValue())
    if out_metric > init_metric:
        logger.info(
            "FLIRT schedule @ %.1f mm: metric worsened (%.6f > %.6f); keeping init",
            target_mm,
            out_metric,
            init_metric,
        )
        return _sitk_copy_euler(init_tx)
    return out_tx


def _sitk_flirt_schedule(
    fixed: sitk.Image,
    moving: sitk.Image,
    candidates: list[tuple[float, sitk.Euler3DTransform]],
    sitk_config: dict[str, Any],
    modality: str,
) -> sitk.Euler3DTransform:
    """Simplified defaultschedule: 4 mm top-3, 2 mm best, 1 mm polish."""
    if not candidates:
        raise RuntimeError("FLIRT schedule: no search candidates")
    schedule_iters = int(sitk_config.get("schedule_iters", 40))
    scales = sitk_config.get("schedule_scales_mm", _SITK_SCHEDULE_SCALES_MM)

    pool = list(candidates[:3])
    logger.info("FLIRT schedule: re-score %d candidates", len(pool))
    rescored: list[tuple[float, sitk.Euler3DTransform]] = []
    for _, tx in pool:
        m = _sitk_eval_metric(fixed, moving, tx, sitk_config, modality)
        rescored.append((m, tx))
    rescored.sort(key=lambda x: x[0])

    best_tx = _sitk_copy_euler(rescored[0][1])
    for scale_mm in scales:
        logger.info("FLIRT schedule: rigid optimise @ %.1f mm (%d iters)", scale_mm, schedule_iters)
        best_tx = _sitk_rigid_refine_at_scale(
            fixed, moving, best_tx, sitk_config, modality, float(scale_mm), schedule_iters
        )
    return best_tx


def sitk_flirt_register(
    fixed: sitk.Image,
    moving: sitk.Image,
    sitk_config: dict[str, Any],
    modality: str,
) -> sitk.Euler3DTransform:
    """Full FLIRT-like pipeline on in-memory images."""
    shrink_8 = _sitk_shrink_for_target_mm(fixed, _SITK_STAGE1_TARGET_MM)
    shrink_4 = _sitk_shrink_for_target_mm(fixed, _SITK_STAGE4_TARGET_MM)
    fixed_8 = sitk.Shrink(fixed, [shrink_8] * 3)
    moving_8 = sitk.Shrink(moving, [shrink_8] * 3)
    fixed_4 = sitk.Shrink(fixed, [shrink_4] * 3)
    moving_4 = sitk.Shrink(moving, [shrink_4] * 3)

    candidates = _sitk_flirt_search_cost(
        fixed_8, moving_8, fixed_4, moving_4, sitk_config, modality
    )
    return _sitk_flirt_schedule(fixed, moving, candidates, sitk_config, modality)
