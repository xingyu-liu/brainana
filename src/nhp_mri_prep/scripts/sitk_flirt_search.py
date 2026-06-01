"""FLIRT-faithful rigid search + schedule for SimpleITK (ports flirt.cc search_cost)."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import SimpleITK as sitk

logger = logging.getLogger("test_anat_conformation")

# Bump when search/schedule semantics change (benchmark resume invalidation).
SITK_PIPELINE_REV = "corratio_powell_minima_v8"

# GEOMETRY seed is preferred only when its fixed/moving overlap beats the COG seed
# by this relative margin, so near-ties keep the FLIRT-faithful COG seed (no
# regression on cases where COG overlap already matches GEOMETRY overlap).
_SITK_SEED_GEOMETRY_MARGIN = 0.1

_SITK_SEARCH_RANGE_DEG = (-180.0, 180.0)
_SITK_STAGE1_TARGET_MM = 8.0
_SITK_STAGE4_TARGET_MM = 4.0
_SITK_SCHEDULE_SCALES_MM = (4.0, 2.0, 1.0)
_SITK_FLIRT_TOP_K = 10
_SITK_TRANSLATION_REFINE_CONVERGENCE = 1e-4
# Corratio + Powell refinement (FLIRT-faithful path): multi-scale pyramid, max Powell
# iterations per scale, and the cap on how many coarse local minima we refine.
_SITK_POWELL_SCALES_MM = (8.0, 4.0, 2.0, 1.0)
_SITK_POWELL_MAXITER = 120
_SITK_CORRATIO_MAX_MINIMA = 8


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
    reg: sitk.ImageRegistrationMethod,
    sitk_config: dict[str, Any],
    modality: str,
    *,
    heavy: bool = False,
    full: bool = False,
) -> None:
    # Full (all-voxel) sampling for the coarse search: the 8/4 mm images are tiny so
    # it is nearly free, and it removes the random-sampling noise that otherwise lets a
    # 180 deg flip out-rank the true pose (their cost gap is only ~0.12-0.17).
    if full:
        reg.SetMetricSamplingStrategy(reg.NONE)
        return
    pct = float(sitk_config.get("search_sampling_pct", 0.2))
    if heavy and modality == "func":
        pct = max(pct, 0.25)
    reg.SetMetricSamplingPercentage(pct)
    reg.SetMetricSamplingStrategy(reg.RANDOM)


def _sitk_rotation_samples_deg(deg_min: float, deg_max: float, step_deg: float) -> np.ndarray:
    """Rotation grid CENTERED on 0 (identity): samples 0, +/-step, +/-2*step, ... in range.

    A rotation search must always try identity. The old linspace(deg_min, deg_max, n)
    only landed on 0 when the interval count was even, so the default 40 deg step over
    (-180, 180) skipped 0 while sampling the 180 deg flip exactly — biasing the search to
    flips and never generating the (correct) near-identity pose for cases whose true
    rotation is small (e.g. 032142 ~4.6 deg, 032123 ~12.8 deg). Centering on 0, like
    FLIRT's search, samples identity and symmetric +/- rotations and drops the exact
    180 deg endpoint.
    """
    step = abs(float(step_deg))
    if step <= 0.0:
        return np.array([0.0])
    k_lo = int(np.ceil(deg_min / step))
    k_hi = int(np.floor(deg_max / step))
    if k_hi < k_lo:
        return np.array([0.0])
    return np.arange(k_lo, k_hi + 1, dtype=np.float64) * step


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
    """COG init for the fixed->moving resample transform: place the fixed COG onto the
    moving COG, i.e. tx(ref_cog) = mov_cog, so trans = mov_cog - R @ (ref_cog - c) - c.

    The transform is consumed by ``sitk.Resample(moving, fixed, tx)``, which maps points
    from the FIXED domain into the MOVING domain (each fixed voxel samples moving at
    ``tx(p)``). Overlap therefore requires the fixed COG to sample the moving COG. The
    previous form (``ref_cog - R @ (mov_cog - c) - c``) instead enforced tx(mov_cog) =
    ref_cog — the inverse direction — leaving tx(ref_cog) displaced by ~2x the COG offset
    and, crucially, rotation-invariant (rotating pivots around the wrong correspondence).
    That was harmless when ref_cog ~ mov_cog but produced zero overlap for off-centre FOVs
    (e.g. sub-03), trapping the corratio search in a flat (no-overlap) cost region.
    """
    ref_cog = _sitk_image_cog_mm(fixed)
    mov_cog = _sitk_image_cog_mm(moving)
    rot_tx = _sitk_euler_from_rot_trans(center, rx_rad, ry_rad, rz_rad, 0.0, 0.0, 0.0)
    rotation = np.array(rot_tx.GetMatrix(), dtype=np.float64).reshape(3, 3)
    c = np.array(center, dtype=np.float64)
    t_param = mov_cog - rotation @ (ref_cog - c) - c
    return _sitk_euler_from_rot_trans(
        center, rx_rad, ry_rad, rz_rad, float(t_param[0]), float(t_param[1]), float(t_param[2])
    )


def _sitk_overlap_voxels(
    fixed: sitk.Image, moving: sitk.Image, tx: sitk.Euler3DTransform
) -> int:
    """Count voxels where fixed and resampled moving are both positive."""
    resampled = sitk.Resample(
        moving, fixed, tx, sitk.sitkLinear, 0.0, moving.GetPixelID()
    )
    fixed_arr = sitk.GetArrayFromImage(fixed)
    moving_arr = sitk.GetArrayFromImage(resampled)
    return int(((fixed_arr > 0) & (moving_arr > 0)).sum())


def _sitk_geometry_seed(
    fixed: sitk.Image,
    moving: sitk.Image,
    rx_rad: float,
    ry_rad: float,
    rz_rad: float,
) -> sitk.Euler3DTransform:
    """GEOMETRY-centered init with explicit rotation (fallback when COG seed has no overlap)."""
    geom = sitk.CenteredTransformInitializer(
        fixed,
        moving,
        sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY,
    )
    params = list(geom.GetParameters())
    params[0:3] = [rx_rad, ry_rad, rz_rad]
    out = sitk.Euler3DTransform()
    out.SetFixedParameters(geom.GetFixedParameters())
    out.SetParameters(params)
    return out


def _sitk_seed_transform(
    fixed: sitk.Image,
    moving: sitk.Image,
    center: tuple[float, float, float],
    rx_rad: float,
    ry_rad: float,
    rz_rad: float,
) -> sitk.Euler3DTransform:
    """Pick the seed (COG vs GEOMETRY) with the larger fixed/moving overlap.

    The COG seed is FLIRT-faithful, but a whole-head / off-center FOV (neck,
    shoulders) drags the intensity centre off the brain, leaving little or no
    overlap with the template. Choosing by overlap — rather than "COG unless
    overlap is exactly zero" — also rescues partial-overlap traps (e.g. 032142),
    where COG overlap is nonzero yet far smaller than the GEOMETRY-centred seed.
    """
    cog_seed = _sitk_flirt_cog_seed(fixed, moving, center, rx_rad, ry_rad, rz_rad)
    cog_overlap = _sitk_overlap_voxels(fixed, moving, cog_seed)
    geom_seed = _sitk_geometry_seed(fixed, moving, rx_rad, ry_rad, rz_rad)
    geom_overlap = _sitk_overlap_voxels(fixed, moving, geom_seed)
    if geom_overlap > cog_overlap * (1.0 + _SITK_SEED_GEOMETRY_MARGIN):
        logger.debug(
            "GEOMETRY seed wins overlap (geom=%d > cog=%d) rot=%.0f,%.0f,%.0f deg",
            geom_overlap,
            cog_overlap,
            np.degrees(rx_rad),
            np.degrees(ry_rad),
            np.degrees(rz_rad),
        )
        return geom_seed
    return cog_seed


def _sitk_refine_translation_only(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    *,
    learning_rate_mm: float,
    iters: int,
    full_sampling: bool = False,
) -> tuple[sitk.Euler3DTransform, float]:
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, search_stage=True)
    reg.SetInterpolator(sitk.sitkLinear)
    _sitk_apply_sampling(reg, sitk_config, modality, heavy=True, full=full_sampling)
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
    *,
    full_sampling: bool = False,
) -> float:
    """Evaluate search metric at tx without moving parameters (ITK needs >=1 iter)."""
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, search_stage=True)
    reg.SetInterpolator(sitk.sitkLinear)
    _sitk_apply_sampling(reg, sitk_config, modality, full=full_sampling)
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


def _sitk_corratio_cost(
    fixed: sitk.Image, moving: sitk.Image, tx: sitk.Euler3DTransform, nbins: int = 32
) -> float:
    """FLIRT-style correlation ratio CR(fixed | moving), negated so lower = better.

    Bins the resampled moving intensities and measures the residual within-bin variance
    of the fixed image. Unlike normalized cross-correlation it is robust to the 180 deg
    flip ambiguity at coarse scale (verified: it ranks the true pose above a flip by a
    ~2x larger margin), which is what NCC's thin margin cannot do once the coarse pose
    is only crudely positioned.
    """
    resampled = sitk.Resample(moving, fixed, tx, sitk.sitkLinear, 0.0, moving.GetPixelID())
    x = sitk.GetArrayViewFromImage(fixed).astype(np.float64).ravel()
    y = sitk.GetArrayViewFromImage(resampled).astype(np.float64).ravel()
    ymin, ymax = float(y.min()), float(y.max())
    tot_var = float(x.var())
    if ymax <= ymin or tot_var <= 0.0:
        return 0.0
    bins = np.clip(((y - ymin) / (ymax - ymin) * nbins).astype(np.intp), 0, nbins - 1)
    n = np.bincount(bins, minlength=nbins).astype(np.float64)
    sx = np.bincount(bins, weights=x, minlength=nbins)
    sx2 = np.bincount(bins, weights=x * x, minlength=nbins)
    nz = n > 0
    within = np.zeros(nbins, dtype=np.float64)
    within[nz] = sx2[nz] - (sx[nz] ** 2) / n[nz]  # = n_k * Var_k(fixed)
    cr = 1.0 - within.sum() / (x.size * tot_var)
    return -float(cr)


def _sitk_rank_cost(
    fixed: sitk.Image,
    moving: sitk.Image,
    tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    *,
    full_sampling: bool = False,
) -> float:
    """Scalar cost used to RANK coarse-search poses (lower = better).

    Defaults to the SimpleITK search metric; set ``search_rank_metric='CorrelationRatio'``
    to rank by correlation ratio instead (translation refinement still uses the SimpleITK
    metric, which has no corratio). Opt-in: the func/MattesMI path is unaffected.
    """
    if sitk_config.get("search_rank_metric") == "CorrelationRatio":
        return _sitk_corratio_cost(fixed, moving, tx, int(sitk_config.get("corratio_bins", 32)))
    return _sitk_eval_metric(fixed, moving, tx, sitk_config, modality, full_sampling=full_sampling)


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
    """FLIRT-faithful coarse rotation search returning the lowest-cost candidates.

    For every rotation on the coarse grid we optimise the translation, then score the
    cost *at that rotation's own optimised translation*, and rank rotations by cost.

    The previous implementation discarded each rotation's cost and instead trilinearly
    interpolated the optimised translations across the (coarse, ~40 deg-spaced) grid
    before scoring a finer rotation grid. That interpolation handed good rotations a
    wrong translation, so their cost looked bad and they were filtered out before the
    schedule — verified on 032142/032123: the correctly-aligned coarse cell was found
    (full-res masked NCC ~0.17/0.26) yet never survived into the candidate list (~0.02/
    0.11). Scoring each rotation at its own translation, with no interpolation, keeps it.
    """
    t0 = time.perf_counter()
    deg_min, deg_max = sitk_config.get("search_range_deg", _SITK_SEARCH_RANGE_DEG)
    coarse_step = float(sitk_config["coarse_step_deg"])
    tx_iters = int(sitk_config.get("search_tx_iters", 50))
    lr_tx = _sitk_min_spacing(fixed_8) * 0.5

    center = _sitk_fixed_geometric_center(fixed_8)
    rx_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    ry_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    rz_c = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    logger.info(
        "FLIRT search coarse: %dx%dx%d rotations @ ~%.1f mm, tx_iters=%d",
        len(rx_c),
        len(ry_c),
        len(rz_c),
        _sitk_min_spacing(fixed_8),
        tx_iters,
    )

    scored: list[tuple[float, sitk.Euler3DTransform]] = []
    for rx in rx_c:
        for ry in ry_c:
            for rz in rz_c:
                seed = _sitk_seed_transform(
                    fixed_8, moving_8, center, np.deg2rad(rx), np.deg2rad(ry), np.deg2rad(rz)
                )
                # FLIRT-faithful: optimise TRANSLATION only, holding the grid rotation
                # fixed (FLIRT's search_cost does the same). Refining rotation here lets
                # poses drift into high-correlation 180 deg flips; FLIRT instead stays
                # robust via its corratio cost + per-local-minimum refinement.
                refined, _ = _sitk_refine_translation_only(
                    fixed_8,
                    moving_8,
                    seed,
                    sitk_config,
                    modality,
                    learning_rate_mm=lr_tx,
                    iters=tx_iters,
                    full_sampling=True,
                )
                # Score at the finer 4 mm scale with full (all-voxel) sampling.
                cost = _sitk_rank_cost(
                    fixed_4, moving_4, refined, sitk_config, modality, full_sampling=True
                )
                scored.append((cost, refined))
    scored.sort(key=lambda r: r[0])
    logger.info(
        "FLIRT search coarse done: %d cells in %.1f s; best cost=%.6f",
        len(scored),
        time.perf_counter() - t0,
        scored[0][0],
    )

    # Polish the top candidates' translation at 4 mm and re-rank before the schedule.
    t1 = time.perf_counter()
    lr_tx4 = _sitk_min_spacing(fixed_4) * 0.5
    results: list[tuple[float, sitk.Euler3DTransform]] = []
    for _, tx in scored[:_SITK_FLIRT_TOP_K]:
        refined, _ = _sitk_refine_translation_only(
            fixed_4, moving_4, tx, sitk_config, modality,
            learning_rate_mm=lr_tx4, iters=tx_iters, full_sampling=True,
        )
        cost = _sitk_rank_cost(
            fixed_4, moving_4, refined, sitk_config, modality, full_sampling=True
        )
        results.append((cost, refined))
    results.sort(key=lambda r: r[0])
    logger.info(
        "FLIRT search refine top-%d @ 4 mm: best cost=%.6f (%.1f s, total %.1f s)",
        len(results),
        results[0][0],
        time.perf_counter() - t1,
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
        m = _sitk_rank_cost(fixed, moving, tx, sitk_config, modality)
        rescored.append((m, tx))
    rescored.sort(key=lambda x: x[0])

    best_tx = _sitk_copy_euler(rescored[0][1])
    for scale_mm in scales:
        logger.info("FLIRT schedule: rigid optimise @ %.1f mm (%d iters)", scale_mm, schedule_iters)
        best_tx = _sitk_rigid_refine_at_scale(
            fixed, moving, best_tx, sitk_config, modality, float(scale_mm), schedule_iters
        )
    return best_tx


def _sitk_euler_params(
    center: tuple[float, float, float], params: np.ndarray
) -> sitk.Euler3DTransform:
    tx = sitk.Euler3DTransform()
    tx.SetCenter(center)
    tx.SetParameters([float(v) for v in params])
    return tx


def _sitk_find_cost_minima(grid: np.ndarray, thresh: float) -> list[tuple[int, int, int]]:
    """Local minima (26-neighbour) of the cost-vs-rotation grid, below `thresh`.

    Port of FLIRT find_cost_minima: refining every basin (not just the global best)
    keeps a correctly-oriented but globally-suboptimal pose in contention.
    """
    nx, ny, nz = grid.shape
    minima: list[tuple[int, int, int]] = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                if grid[i, j, k] > thresh:
                    continue
                sub = grid[max(0, i - 1) : i + 2, max(0, j - 1) : j + 2, max(0, k - 1) : k + 2]
                if grid[i, j, k] <= float(sub.min()) + 1e-9:
                    minima.append((i, j, k))
    return minima


def _sitk_corratio_powell_refine(
    fixed: sitk.Image,
    moving: sitk.Image,
    center: tuple[float, float, float],
    params0: np.ndarray,
    scales_mm: tuple[float, ...],
    nbins: int,
    maxiter: int,
) -> np.ndarray:
    """Multi-scale Powell refinement of the 6 rigid params, minimising corratio.

    FLIRT optimises corratio with Powell (derivative-free). Gradient descent on
    correlation drifts into the higher-correlation 180 deg flip at coarse scale; Powell
    on corratio holds the true basin (verified: converges to FLIRT's exact rotation).
    """
    from scipy.optimize import minimize  # lazy: only the corratio path needs scipy

    p = np.array(params0, dtype=np.float64)
    for mm in scales_mm:
        shrink = _sitk_shrink_for_target_mm(fixed, mm)
        fs = sitk.Shrink(fixed, [shrink] * 3) if shrink > 1 else fixed
        ms = sitk.Shrink(moving, [shrink] * 3) if shrink > 1 else moving

        def _cost(q: np.ndarray) -> float:
            return _sitk_corratio_cost(fs, ms, _sitk_euler_params(center, q), nbins)

        p = minimize(
            _cost, p, method="Powell", options={"maxiter": maxiter, "xtol": 1e-3, "ftol": 1e-4}
        ).x
    return p


def _sitk_corratio_register(
    fixed: sitk.Image,
    moving: sitk.Image,
    fixed_8: sitk.Image,
    moving_8: sitk.Image,
    fixed_4: sitk.Image,
    moving_4: sitk.Image,
    sitk_config: dict[str, Any],
    modality: str,
) -> sitk.Euler3DTransform:
    """FLIRT-faithful corratio path (search_rank_metric='CorrelationRatio').

    Coarse corratio cost-vs-rotation grid (translation-only per cell) -> find_cost_minima
    (local minima) PLUS the identity/COG seed -> refine each with corratio+Powell -> pick
    the best by final corratio. The identity seed is FLIRT's own initial estimate; it
    rescues co-oriented truths whose near-identity region is not itself a coarse local
    minimum (e.g. 032123), which local-minima selection alone would miss.
    """
    t0 = time.perf_counter()
    deg_min, deg_max = sitk_config.get("search_range_deg", _SITK_SEARCH_RANGE_DEG)
    coarse_step = float(sitk_config["coarse_step_deg"])
    tx_iters = int(sitk_config.get("search_tx_iters", 50))
    lr_tx = _sitk_min_spacing(fixed_8) * 0.5
    nbins = int(sitk_config.get("corratio_bins", 32))
    center = _sitk_fixed_geometric_center(fixed_8)
    rs = _sitk_rotation_samples_deg(deg_min, deg_max, coarse_step)
    n = len(rs)

    grid = np.full((n, n, n), np.inf, dtype=np.float64)
    params_at: dict[tuple[int, int, int], np.ndarray] = {}
    for i, rx in enumerate(rs):
        for j, ry in enumerate(rs):
            for k, rz in enumerate(rs):
                seed = _sitk_seed_transform(
                    fixed_8, moving_8, center, np.deg2rad(rx), np.deg2rad(ry), np.deg2rad(rz)
                )
                refined, _ = _sitk_refine_translation_only(
                    fixed_8, moving_8, seed, sitk_config, modality,
                    learning_rate_mm=lr_tx, iters=tx_iters, full_sampling=True,
                )
                grid[i, j, k] = _sitk_corratio_cost(fixed_4, moving_4, refined, nbins)
                params_at[(i, j, k)] = np.array(refined.GetParameters(), dtype=np.float64)

    thresh = float(np.percentile(grid, 20))
    minima = _sitk_find_cost_minima(grid, thresh)
    minima.sort(key=lambda c: grid[c])
    minima = minima[:_SITK_CORRATIO_MAX_MINIMA]
    seeds = [params_at[c] for c in minima]
    # FLIRT's initial estimate: identity rotation at the COG/geometry seed.
    id_seed = _sitk_seed_transform(fixed_8, moving_8, center, 0.0, 0.0, 0.0)
    seeds.append(np.array(id_seed.GetParameters(), dtype=np.float64))
    logger.info(
        "FLIRT corratio search: %d coarse cells, %d minima + identity seed (%.1f s)",
        grid.size, len(minima), time.perf_counter() - t0,
    )

    scales = sitk_config.get("powell_scales_mm", _SITK_POWELL_SCALES_MM)
    maxiter = int(sitk_config.get("powell_maxiter", _SITK_POWELL_MAXITER))
    best_cost = float("inf")
    best_params = seeds[-1]
    for p0 in seeds:
        p = _sitk_corratio_powell_refine(fixed, moving, center, p0, scales, nbins, maxiter)
        cost = _sitk_corratio_cost(fixed, moving, _sitk_euler_params(center, p), nbins)
        if cost < best_cost:
            best_cost = cost
            best_params = p
    logger.info(
        "FLIRT corratio refine: %d seeds, best corratio cost=%.6f (total %.1f s)",
        len(seeds), best_cost, time.perf_counter() - t0,
    )
    return _sitk_euler_params(center, best_params)


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

    # FLIRT-faithful corratio + Powell + find_cost_minima path (anat default); the
    # correlation/MattesMI gradient-descent path is unchanged for func and other configs.
    if sitk_config.get("search_rank_metric") == "CorrelationRatio":
        return _sitk_corratio_register(
            fixed, moving, fixed_8, moving_8, fixed_4, moving_4, sitk_config, modality
        )

    candidates = _sitk_flirt_search_cost(
        fixed_8, moving_8, fixed_4, moving_4, sitk_config, modality
    )
    return _sitk_flirt_schedule(fixed, moving, candidates, sitk_config, modality)
