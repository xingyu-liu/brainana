#!/usr/bin/env python3
"""
Benchmark FLIRT vs SimpleITK vs antsAI for anatomical conformation (rigid alignment).

Runs identical preprocessing (skullstrip, template pad/downsample, template resample),
then compares registration backends in order: FLIRT baseline, SimpleITK parameter
grid (exhaustive coarse rotation + gradient fine refinement), antsAI parameter grid,
with QC snapshots and a self-contained HTML report.
"""

from __future__ import annotations

import base64
import csv
import html
import logging
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from sklearn.metrics import normalized_mutual_info_score

# Add src/ to path for nhp_mri_prep imports (scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.operations.preprocessing import (
    DEFAULT_CONFORM_PADDING_PERCENTAGE,
    DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD,
    apply_skullstripping,
)
from nhp_mri_prep.operations.registration import (
    flirt_apply_transforms,
    flirt_register,
)
from nhp_mri_prep.operations.validation import (
    ensure_working_directory,
    validate_input_file,
    validate_output_file,
)
from nhp_mri_prep.quality_control.snapshots import create_conform_qc
from nhp_mri_prep.utils import run_command
from nhp_mri_prep.utils.mri import pad_image

MOVING_PREFIX = "moving_"
FIXED_PREFIX = "fixed_"
MOVING_GLOBS = ("moving_*.nii.gz", "moving_*.nii")

# %% FLIRT settings mirrored from conform_to_template (preprocessing.py)
FLIRT_CONFIG_ANAT = {
    "registration": {
        "flirt": {
            "cost": "corratio",
            "searchcost": "corratio",
            "coarsesearch": 40,
            "finesearch": 15,
        }
    }
}

FLIRT_CONFIG_FUNC = {
    "registration": {
        "flirt": {
            "cost": "mutualinfo",
            "searchcost": "mutualinfo",
            "coarsesearch": 30,
            "finesearch": 10,
        }
    }
}


def flirt_config_for_modality(modality: str) -> dict[str, Any]:
    """Return FLIRT config matching conform_to_template for anat/func."""
    if modality == "func":
        return FLIRT_CONFIG_FUNC
    # anat conform; t2w benchmark has no conform_to_template equivalent
    return FLIRT_CONFIG_ANAT

# Fixed antsAI settings (not swept in the grid)
_ANTS_AI_FIXED: dict[str, Any] = {
    # number_of_bins: histogram bins for Mattes/MI metrics
    "number_of_bins": 32,
    # sampling_strategy: how voxels are chosen for metric evaluation (Random = stochastic subset)
    "sampling_strategy": "Random",
    # transform: 6-DOF rigid (3 rotation + 3 translation)
    "transform": "Rigid",
    # gradient_step: step size for gradient descent after initialization
    "gradient_step": 0.1,
    # align_principal_axes: pre-align principal inertia axes before rotation search
    "align_principal_axes": 1,
    # arc_fraction: fraction of full circle to sweep (1.0 = 360° on each rotation axis)
    "arc_fraction": 1.0,
    # convergence_iterations: gradient-descent refinement steps after best init pose
    "convergence_iterations": 15,
    "dimensionality": 3,
    "verbose": 1,
    # random_seed: reproducible random voxel sampling
    "random_seed": 42,
}


def _antsai_param_label(metric: str, search_factor: int, sampling_percentage: float) -> str:
    samp = f"{sampling_percentage:.2f}".replace(".", "p")
    return f"antsai_{metric}_sf{search_factor:02d}_samp{samp}"


def _build_ants_ai_param_grid() -> list[dict[str, Any]]:
    """Build antsAI variants: n metrics × n search_factors × n sampling_percentages."""
    grid: list[dict[str, Any]] = []
    # metric: similarity function (Mattes/MI for cross-modal, GC for same-modality)
    metrics = ("Mattes", "MI")
    # search_factor: angular step in degrees (5°→72 samples/axis, 10°→36, 20°→18)
    search_factors = (40, 30, 20, 15)
    # sampling_percentage: fraction of voxels used per metric evaluation (speed vs stability)
    sampling_percentages = (0.5, 0.25)
    for metric in metrics:
        for search_factor in search_factors:
            for sampling_percentage in sampling_percentages:
                label = _antsai_param_label(metric, search_factor, sampling_percentage)
                grid.append(
                    {
                        **_ANTS_AI_FIXED,
                        "metric": metric,
                        "search_factor": search_factor,
                        "sampling_percentage": sampling_percentage,
                        "label": label,
                    }
                )
    return grid


ANTS_AI_PARAM_GRID = _build_ants_ai_param_grid()

_METHOD_ORDER = {"flirt": 0, "sitk": 1, "antsai": 2}


# %% SimpleITK: modality profiles + parameter grid
@dataclass(frozen=True)
class SitkModalityProfile:
    """Metric, optional Mattes bins/lr sweep, fine rotation step options, stage-2 pyramid (mm)."""

    pyramid_target_mm: tuple[float, ...]
    metric: str
    histogram_bins: tuple[int, ...] = ()
    learning_rates: tuple[float, ...] = (1.0,)
    fine_step_deg_options: tuple[int, ...] = (15,)


_SITK_COARSE_STEP_DEG = 40
_SITK_FINE_STEP_DEG_DEFAULT = 15
_SITK_FINE_ITERS = (100, 200, 300)
_SITK_STAGE1_TARGET_MM = 8.0
_SITK_STAGE15_TARGET_MM_MIN = 4.0
_SITK_COST_THRESH_FRACTION = 0.2
_SITK_TRANSLATION_REFINE_ITERS = 100
_SITK_TRANSLATION_REFINE_CONVERGENCE = 1e-4
_SITK_MAX_TRANSLATION_CANDIDATES = 100
_SITK_TRANSLATION_SAMPLING_PERCENTAGE = 0.25

# Both profiles use the same 8→4→2 mm pyramid; they differ only in bins and lr sweep.
_SITK_PROFILE_DEFAULT = SitkModalityProfile(
    pyramid_target_mm=(8.0, 4.0, 2.0),
    metric="MattesMI",
    histogram_bins=(32,),
    fine_step_deg_options=(15, 10),
)
_SITK_PROFILE_FUNC = SitkModalityProfile(
    pyramid_target_mm=(8.0, 4.0, 2.0),
    metric="MattesMI",
    histogram_bins=(24, 32),
    learning_rates=(0.5, 1.0),
    fine_step_deg_options=(15, 10),
)


def _sitk_profile(modality: str) -> SitkModalityProfile:
    return _SITK_PROFILE_FUNC if modality == "func" else _SITK_PROFILE_DEFAULT


def _sitk_min_spacing(img: sitk.Image) -> float:
    """Smallest voxel spacing (mm); used for resolution-adaptive shrinks and learning rate."""
    return float(min(img.GetSpacing()))


def _sitk_shrink_for_target_mm(img: sitk.Image, target_mm: float) -> int:
    """Shrink factor so effective voxel size is approximately target_mm."""
    return max(1, int(round(target_mm / _sitk_min_spacing(img))))


def _sitk_stage15_target_mm(img: sitk.Image) -> float:
    """Stage-1.5 resolution: at least 4 mm and 2× native spacing (avoids near-native func)."""
    return max(_SITK_STAGE15_TARGET_MM_MIN, 2.0 * _sitk_min_spacing(img))


def _sitk_adaptive_pyramid(
    fixed: sitk.Image,
    target_mm: tuple[float, ...],
) -> tuple[list[int], list[float]]:
    """Shrink factors and smoothing sigmas (mm) for a physical-resolution pyramid."""
    min_sp = _sitk_min_spacing(fixed)
    shrinks = [max(1, int(round(t / min_sp))) for t in target_mm]
    sigmas = [max(0.0, t / 2.0) for t in target_mm]
    return shrinks, sigmas


def _sitk_pyramid_for_modality(
    fixed: sitk.Image, modality: str
) -> tuple[list[int], list[float]]:
    profile = _sitk_profile(modality)
    return _sitk_adaptive_pyramid(fixed, profile.pyramid_target_mm)


def _sitk_pose_with_moments_translation(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    pose_params: list[float],
) -> sitk.Euler3DTransform:
    """Set rotation from exhaustive pose; re-align translation via MOMENTS (FLIRT-style per pose)."""
    rot_tx = sitk.Euler3DTransform()
    rot_tx.SetFixedParameters(init_tx.GetFixedParameters())
    pose = list(pose_params)
    pose[3:6] = [0.0, 0.0, 0.0]
    rot_tx.SetParameters(pose)
    return _unwrap_euler3d(
        sitk.CenteredTransformInitializer(
            fixed,
            moving,
            rot_tx,
            sitk.CenteredTransformInitializerFilter.MOMENTS,
        )
    )


def _sitk_refine_translation_only(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    *,
    learning_rate_mm: float,
    iters: int = _SITK_TRANSLATION_REFINE_ITERS,
) -> tuple[sitk.Euler3DTransform, float]:
    """Gradient refinement of translation only (rotation scales = 0 freeze angles)."""
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config)
    reg.SetInterpolator(sitk.sitkLinear)
    if modality == "func":
        reg.SetMetricSamplingPercentage(_SITK_TRANSLATION_SAMPLING_PERCENTAGE)
    reg.SetOptimizerAsGradientDescent(
        learningRate=learning_rate_mm,
        numberOfIterations=iters,
        convergenceMinimumValue=_SITK_TRANSLATION_REFINE_CONVERGENCE,
        convergenceWindowSize=5,
    )
    # Large scales suppress rotation updates; translation uses unit scales (mm step via lr).
    reg.SetOptimizerScales([1e6, 1e6, 1e6, 1.0, 1.0, 1.0])
    reg.SetInitialTransform(init_tx, inPlace=False)
    refined = _unwrap_euler3d(reg.Execute(fixed, moving))
    return refined, float(reg.GetMetricValue())


def _sitk_exhaustive_rotation(
    fixed: sitk.Image,
    moving: sitk.Image,
    init_tx: sitk.Euler3DTransform,
    step_deg: float,
    sitk_config: dict[str, Any],
    stage_label: str,
) -> tuple[list[tuple[float, list[float]]], sitk.Euler3DTransform]:
    """Full ±180° rotation exhaustive search at the resolution of fixed/moving."""
    step_rad = step_deg * np.pi / 180.0
    n_steps = max(1, int(round(180.0 / step_deg)))
    min_sp = _sitk_min_spacing(fixed)

    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config)
    reg.SetInterpolator(sitk.sitkLinear)
    reg.SetOptimizerAsExhaustive(
        numberOfSteps=[n_steps, n_steps, n_steps, 0, 0, 0],
        stepLength=step_rad,
    )
    reg.SetOptimizerScales([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    reg.SetInitialTransform(init_tx, inPlace=False)

    poses: list[tuple[float, list[float]]] = []

    def _capture_pose() -> None:
        poses.append((reg.GetMetricValue(), list(reg.GetOptimizerPosition())))

    reg.AddCommand(sitk.sitkIterationEvent, _capture_pose)
    best_tx = _unwrap_euler3d(reg.Execute(fixed, moving))
    expected = (2 * n_steps + 1) ** 3
    logger.info(
        "SimpleITK %s: exhaustive rotation (step=%.1f deg, poses=%d/%d, "
        "spacing=%.2f mm)",
        stage_label,
        step_deg,
        len(poses),
        expected,
        min_sp,
    )
    return poses, best_tx


def _sitk_select_translation_candidates(
    poses: list[tuple[float, list[float]]],
    fraction: float = _SITK_COST_THRESH_FRACTION,
    max_candidates: int = _SITK_MAX_TRANSLATION_CANDIDATES,
) -> list[tuple[float, list[float]]]:
    """Select poses within bottom fraction of cost range (FLIRT-style threshold)."""
    if not poses:
        return []
    metrics = [m for m, _ in poses]
    cost_min, cost_max = min(metrics), max(metrics)
    thresh = cost_min + fraction * (cost_max - cost_min)
    candidates = [(m, p) for m, p in poses if m <= thresh]
    candidates.sort(key=lambda x: x[0])
    return candidates[:max_candidates]


def _sitk_lr_tag(learning_rate: float) -> str:
    return f"lr{learning_rate:.1f}".replace(".", "p")


def _sitk_param_label(
    metric: str,
    fine_step_deg: int,
    fine_iters: int,
    histogram_bins: int | None = None,
    learning_rate: float = 1.0,
    include_bins: bool = False,
    include_learning_rate: bool = False,
) -> str:
    bins_part = f"_b{histogram_bins}" if include_bins and histogram_bins is not None else ""
    lr_part = f"_{_sitk_lr_tag(learning_rate)}" if include_learning_rate else ""
    return (
        f"sitk_{metric}{bins_part}{lr_part}_fs{fine_step_deg:02d}_fi{fine_iters}"
    )


def _build_sitk_param_grid(profile: SitkModalityProfile) -> list[dict[str, Any]]:
    """Two-pass rotation (40°+fine_step) fixed; sweep fine_iters and optional fine_step."""
    include_lr = len(profile.learning_rates) > 1
    include_bins = profile.metric == "MattesMI" and len(profile.histogram_bins) > 0
    grid: list[dict[str, Any]] = []
    bin_values: tuple[int | None, ...] = (
        profile.histogram_bins if include_bins else (None,)
    )
    lr_values = profile.learning_rates if include_lr else (1.0,)
    for histogram_bin in bin_values:
        for learning_rate in lr_values:
            for fine_step_deg in profile.fine_step_deg_options:
                for fine_iters in _SITK_FINE_ITERS:
                    label = _sitk_param_label(
                        profile.metric,
                        fine_step_deg,
                        fine_iters,
                        histogram_bins=histogram_bin,
                        learning_rate=learning_rate,
                        include_bins=include_bins,
                        include_learning_rate=include_lr,
                    )
                    entry: dict[str, Any] = {
                        "metric": profile.metric,
                        "coarse_step_deg": _SITK_COARSE_STEP_DEG,
                        "fine_step_deg": fine_step_deg,
                        "fine_iters": fine_iters,
                        "learning_rate": learning_rate,
                        "label": label,
                    }
                    if histogram_bin is not None:
                        entry["number_of_histogram_bins"] = histogram_bin
                    grid.append(entry)
    return grid


_SITK_PARAM_GRIDS: dict[str, list[dict[str, Any]]] = {
    "default": _build_sitk_param_grid(_SITK_PROFILE_DEFAULT),
    "func": _build_sitk_param_grid(_SITK_PROFILE_FUNC),
}


def sitk_param_grid_for_modality(modality: str) -> list[dict[str, Any]]:
    key = "func" if modality == "func" else "default"
    return _SITK_PARAM_GRIDS[key]


logger = logging.getLogger("test_anat_conformation")


def _antsai_metric_string(fixed: str, moving: str, ai: dict[str, Any]) -> str:
    return (
        f"{ai['metric']}[{fixed},{moving},{ai['number_of_bins']},"
        f"{ai['sampling_strategy']},{ai['sampling_percentage']}]"
    )


def _antsai_transform_string(ai: dict[str, Any]) -> str:
    return f"{ai['transform']}[{ai['gradient_step']}]"


def _antsai_search_string(ai: dict[str, Any]) -> str:
    return f"[{ai['search_factor']},{ai['arc_fraction']}]"


@dataclass
class PreprocessResult:
    brain_f: Path
    template_for_reg: Path
    template_for_xfm: Path
    full_head: Path


@dataclass
class MethodResult:
    conformed_f: Path
    conformed_brain_f: Path
    reg_time_s: float
    total_time_s: float


def conformed_brain_path(conformed_f: Path) -> Path:
    """Path for skull-stripped conformed volume (metrics), sibling of full-head output."""
    if conformed_f.name.endswith(".nii.gz"):
        return conformed_f.with_name(conformed_f.name.replace(".nii.gz", "_brain.nii.gz"))
    return conformed_f.with_name(f"{conformed_f.stem}_brain{conformed_f.suffix}")


@dataclass
class BenchmarkRow:
    image: str
    method: str
    param_set: str
    nmi: float
    ncc: float
    reg_time_s: float
    total_time_s: float
    modality: str = "anat"
    qc_snapshot_path: str = ""


@dataclass
class MovingFixedPair:
    moving: Path
    fixed: Path
    stem: str


def _strip_nii_basename(filename: str) -> str:
    """Remove .nii.gz or .nii extension from a filename."""
    if filename.endswith(".nii.gz"):
        return filename[: -len(".nii.gz")]
    if filename.endswith(".nii"):
        return filename[: -len(".nii")]
    return filename


def _find_matched_fixed(input_dir: Path, name: str) -> Path | None:
    """Return fixed_{name}.nii.gz or .nii if present in input_dir."""
    for ext in (".nii.gz", ".nii"):
        candidate = input_dir / f"{FIXED_PREFIX}{name}{ext}"
        if candidate.is_file():
            return candidate
    return None


def resolve_fixed_for_moving(
    moving_path: Path,
    input_dir: Path,
    default_fixed: Path,
) -> tuple[Path, str]:
    """Resolve fixed image for a moving file; return (fixed_path, source_label)."""
    basename = _strip_nii_basename(moving_path.name)
    if not basename.startswith(MOVING_PREFIX):
        raise ValueError(
            f"Expected moving file named moving_*.nii.gz, got: {moving_path.name}"
        )
    name = basename[len(MOVING_PREFIX) :]
    matched = _find_matched_fixed(input_dir, name)
    if matched is not None:
        return matched, "matched"
    if not default_fixed.is_file():
        raise FileNotFoundError(
            f"No fixed_{name}.nii.gz in {input_dir} and fallback fixed not found: "
            f"{default_fixed}"
        )
    return default_fixed, "default"


def discover_moving_fixed_pairs(
    input_dir: Path,
    default_fixed: Path,
) -> list[MovingFixedPair]:
    """Discover moving_* files and pair each with fixed_{name} or default fixed."""
    seen_stems: set[str] = set()
    pairs: list[MovingFixedPair] = []
    for pattern in MOVING_GLOBS:
        for moving_path in sorted(input_dir.glob(pattern)):
            if not moving_path.is_file():
                continue
            basename = _strip_nii_basename(moving_path.name)
            if not basename.startswith(MOVING_PREFIX):
                continue
            stem = basename[len(MOVING_PREFIX) :]
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            fixed_path, source = resolve_fixed_for_moving(
                moving_path, input_dir, default_fixed
            )
            logger.info(
                "Pair: %s -> %s (%s)",
                moving_path.name,
                fixed_path.name,
                source,
            )
            pairs.append(
                MovingFixedPair(moving=moving_path, fixed=fixed_path, stem=stem)
            )
    pairs.sort(key=lambda p: p.stem)
    return pairs


def _is_valid_output(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _try_load_preprocess_cache(
    shared_dir: Path, full_head: Path
) -> PreprocessResult | None:
    """Return PreprocessResult from cache when shared preprocess outputs exist."""
    brain_f = shared_dir / "brain_for_conform.nii.gz"
    template_for_xfm = shared_dir / "template_for_xfm.nii.gz"
    padded = shared_dir / "template_padded.nii.gz"
    downsampled = shared_dir / "template_padded_downsampled.nii.gz"
    has_template_for_reg = _is_valid_output(downsampled) or _is_valid_output(padded)
    if not (
        _is_valid_output(brain_f)
        and _is_valid_output(template_for_xfm)
        and has_template_for_reg
    ):
        return None
    template_for_reg = downsampled if _is_valid_output(downsampled) else padded
    return PreprocessResult(
        brain_f=brain_f,
        template_for_reg=template_for_reg,
        template_for_xfm=template_for_xfm,
        full_head=full_head,
    )


METRICS_CSV_FIELDS = [
    "image",
    "method",
    "param_set",
    "modality",
    "nmi",
    "ncc",
    "reg_time_s",
    "total_time_s",
    "qc_snapshot_path",
]


def load_metrics_store(csv_path: Path) -> dict[tuple[str, str], BenchmarkRow]:
    """Load metrics.csv keyed by (image, param_set)."""
    store: dict[tuple[str, str], BenchmarkRow] = {}
    if not csv_path.is_file():
        return store
    try:
        with csv_path.open(newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "image" not in reader.fieldnames:
                return store
            for row in reader:
                key = (row["image"], row["param_set"])
                store[key] = BenchmarkRow(
                    image=row["image"],
                    method=row["method"],
                    param_set=row["param_set"],
                    nmi=float(row["nmi"]),
                    ncc=float(row["ncc"]),
                    reg_time_s=float(row["reg_time_s"]),
                    total_time_s=float(row["total_time_s"]),
                    modality=row.get("modality", "anat"),
                    qc_snapshot_path=row.get("qc_snapshot_path", ""),
                )
    except (KeyError, ValueError) as exc:
        logger.warning("Could not parse %s: %s — starting fresh", csv_path, exc)
    return store


def _rows_from_store(store: dict[tuple[str, str], BenchmarkRow]) -> list[BenchmarkRow]:
    rows = list(store.values())
    rows.sort(
        key=lambda r: (
            r.modality,
            r.image,
            _METHOD_ORDER.get(r.method, 9),
            r.param_set,
        )
    )
    return rows


def load_all_modality_rows(
    output_dir: Path, modalities: tuple[str, ...] = ("anat", "func", "t2w")
) -> list[BenchmarkRow]:
    """Merge metrics from OUTPUT_DIR/{modality}/metrics.csv for combined reporting."""
    rows: list[BenchmarkRow] = []
    for modality in modalities:
        csv_path = output_dir / modality / "metrics.csv"
        rows.extend(_rows_from_store(load_metrics_store(csv_path)))
    rows.sort(
        key=lambda r: (
            r.modality,
            r.image,
            _METHOD_ORDER.get(r.method, 9),
            r.param_set,
        )
    )
    return rows


def write_metrics_store(
    csv_path: Path, store: dict[tuple[str, str], BenchmarkRow]
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METRICS_CSV_FIELDS)
        writer.writeheader()
        for row in _rows_from_store(store):
            writer.writerow(asdict(row))


def upsert_metrics_row(
    csv_path: Path,
    store: dict[tuple[str, str], BenchmarkRow],
    row: BenchmarkRow,
) -> None:
    """Upsert one benchmark row and rewrite metrics.csv immediately."""
    store[(row.image, row.param_set)] = row
    write_metrics_store(csv_path, store)
    logger.info(
        "metrics.csv updated (%d rows): %s / %s",
        len(store),
        row.image,
        row.param_set,
    )


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def shared_preprocess(
    imagef: Path,
    template_file: Path,
    work_dir: Path,
    modality: str = "anat",
) -> PreprocessResult:
    """Steps 1, 2, and 4 of conform_to_template (skullstrip + template prep)."""
    image_path = validate_input_file(imagef, logger)
    template_path = validate_input_file(template_file, logger)
    work_dir = ensure_working_directory(work_dir, logger)

    logger.info("Preprocess: skullstripping %s", image_path.name)
    brain_f = work_dir / "brain_for_conform.nii.gz"
    skull_result = apply_skullstripping(
        imagef=str(image_path),
        modal=modality,
        working_dir=str(work_dir),
        output_name="brain_for_conform.nii.gz",
        config=None,
        logger=logger,
    )
    brain_extracted = skull_result.get("imagef_skullstripped")
    if not brain_extracted or not Path(brain_extracted).exists():
        raise RuntimeError("Skullstripping failed: brain-extracted image not found")
    extracted_path = Path(brain_extracted)
    if extracted_path != brain_f:
        shutil.move(str(extracted_path), str(brain_f))

    logger.info(
        "Preprocess: padding template (padding_percentage=%s)",
        DEFAULT_CONFORM_PADDING_PERCENTAGE,
    )
    img = nib.load(template_path)
    data = img.get_fdata()
    source_for_padding = template_path
    if data.ndim == 4:
        logger.warning("4D template detected; averaging last dimension.")
        data = np.mean(data, axis=-1)
        source_for_padding = work_dir / "_template_3d.nii.gz"
        nib.save(
            nib.Nifti1Image(data.astype(img.get_data_dtype()), img.affine, img.header),
            str(source_for_padding),
        )

    original_shape = np.array(data.shape[:3])
    pad_amounts = (original_shape * DEFAULT_CONFORM_PADDING_PERCENTAGE).astype(int)
    template_f_padded = work_dir / "template_padded.nii.gz"
    pad_image(
        str(source_for_padding), str(template_f_padded), pad_amounts, logger=logger
    )
    padded_img = nib.load(str(template_f_padded))
    padded_img.header.set_xyzt_units("mm", "sec")
    nib.save(padded_img, str(template_f_padded))
    validate_output_file(template_f_padded, logger)

    template_f_for_reg = template_f_padded
    orig_template_voxel_sizes = np.sqrt(
        np.sum(nib.load(str(template_f_for_reg)).affine[:3, :3] ** 2, axis=0)
    )
    brain_affine = nib.load(brain_f).affine
    orig_brain_voxel_sizes = np.sqrt(np.sum(brain_affine[:3, :3] ** 2, axis=0))
    brain_voxel_sizes = np.round(np.min(orig_brain_voxel_sizes), 2)
    if brain_voxel_sizes <= 0:
        raise ValueError(f"Invalid target voxel size: {brain_voxel_sizes} mm")
    target_voxel_sizes = np.full((3,), brain_voxel_sizes)

    should_downsample = False
    downsample_voxel_sizes = None
    if any(orig_template_voxel_sizes < target_voxel_sizes - 0.01):
        should_downsample = True
        downsample_voxel_sizes = target_voxel_sizes.copy()
        if any(target_voxel_sizes < DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD - 0.01):
            downsample_voxel_sizes = np.full(
                (3,), DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD
            )

    if should_downsample:
        template_f_downsampled = Path(
            str(template_f_padded).split(".nii.gz")[0] + "_downsampled.nii.gz"
        )
        cmd = [
            "3dresample",
            "-dxyz",
            str(downsample_voxel_sizes[0]),
            str(downsample_voxel_sizes[1]),
            str(downsample_voxel_sizes[2]),
            "-input",
            str(template_f_for_reg),
            "-prefix",
            str(template_f_downsampled),
            "-rmode",
            "Cu",
        ]
        returncode, _, stderr = run_command(cmd, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(f"3dresample failed: {stderr}")
        validate_output_file(template_f_downsampled, logger)
        template_f_for_reg = template_f_downsampled

    template_f_for_xfm = work_dir / "template_for_xfm.nii.gz"
    if template_f_for_xfm.exists():
        template_f_for_xfm.unlink()
    cmd = [
        "3dresample",
        "-dxyz",
        str(target_voxel_sizes[0]),
        str(target_voxel_sizes[1]),
        str(target_voxel_sizes[2]),
        "-input",
        str(template_f_for_reg),
        "-prefix",
        str(template_f_for_xfm),
        "-rmode",
        "Cu",
    ]
    returncode, _, stderr = run_command(cmd, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"3dresample (template for xfm) failed: {stderr}")
    validate_output_file(template_f_for_xfm, logger)

    return PreprocessResult(
        brain_f=brain_f,
        template_for_reg=Path(template_f_for_reg),
        template_for_xfm=template_f_for_xfm,
        full_head=image_path,
    )


def t2w_preprocess(moving_f: Path, fixed_f: Path) -> PreprocessResult:
    """T2w→T1w rigid reg: no skullstrip or template prep; T1w is the fixed reference."""
    moving = validate_input_file(moving_f, logger)
    fixed = validate_input_file(fixed_f, logger)
    return PreprocessResult(
        brain_f=moving,
        template_for_reg=fixed,
        template_for_xfm=fixed,
        full_head=moving,
    )


def run_flirt(
    preprocess: PreprocessResult,
    work_dir: Path,
    output_name: str = "conformed_flirt.nii.gz",
    modality: str = "anat",
) -> MethodResult:
    """FLIRT rigid registration + apply (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)

    t_total_start = time.perf_counter()
    t_reg_start = time.perf_counter()
    registration_result = flirt_register(
        fixedf=str(preprocess.template_for_reg),
        movingf=str(preprocess.brain_f),
        working_dir=str(work_dir),
        output_prefix="conform_scanner2native",
        config=flirt_config_for_modality(modality),
        logger=logger,
        dof=6,
    )
    reg_time_s = time.perf_counter() - t_reg_start
    xfm_forward_f = Path(registration_result["forward_transform"])

    apply_result = flirt_apply_transforms(
        movingf=str(preprocess.full_head),
        outputf_name=output_name,
        reff=str(preprocess.template_for_xfm),
        working_dir=str(work_dir),
        transformf=str(xfm_forward_f),
        logger=logger,
        interpolation="trilinear",
        generate_tmean=False,
    )
    conformed_f = Path(apply_result["imagef_registered"])
    brain_output_name = conformed_brain_path(conformed_f).name
    brain_apply = flirt_apply_transforms(
        movingf=str(preprocess.brain_f),
        outputf_name=brain_output_name,
        reff=str(preprocess.template_for_xfm),
        working_dir=str(work_dir),
        transformf=str(xfm_forward_f),
        logger=logger,
        interpolation="trilinear",
        generate_tmean=False,
    )
    total_time_s = time.perf_counter() - t_total_start

    return MethodResult(
        conformed_f=conformed_f,
        conformed_brain_f=Path(brain_apply["imagef_registered"]),
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
    )


def _set_sitk_metric(
    reg: sitk.ImageRegistrationMethod,
    sitk_config: dict[str, Any],
    *,
    stage2_gradient: bool = False,
) -> None:
    """Set metric. Stage-2 gradient always uses Mattes MI (Correlation multi-res GD is unstable)."""
    if stage2_gradient:
        bins = int(sitk_config.get("number_of_histogram_bins", 32))
        reg.SetMetricAsMattesMutualInformation(bins)
        return
    metric = sitk_config["metric"]
    if metric == "Correlation":
        reg.SetMetricAsCorrelation()
    elif metric == "MattesMI":
        reg.SetMetricAsMattesMutualInformation(
            int(sitk_config["number_of_histogram_bins"])
        )
    else:
        raise ValueError(f"Unknown SimpleITK metric: {metric}")


def _sitk_ensure_3d(img: sitk.Image) -> sitk.Image:
    """Return a 3-D version of img, computing the temporal mean if img is 4-D.

    If the image is already 3-D it is returned unchanged.
    """
    if img.GetDimension() != 4:
        return img
    arr = sitk.GetArrayFromImage(img)  # shape (t, z, y, x) in SimpleITK array order
    mean_arr = arr.mean(axis=0).astype(np.float32)
    out = sitk.GetImageFromArray(mean_arr)
    out.SetSpacing(img.GetSpacing()[:3])
    out.SetOrigin(img.GetOrigin()[:3])
    out.SetDirection(
        [img.GetDirection()[i] for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
    )
    return out


def _unwrap_euler3d(tx: sitk.Transform) -> sitk.Euler3DTransform:
    """Return an Euler3DTransform from tx, unwrapping a CompositeTransform if needed.

    SimpleITK's ImageRegistrationMethod.Execute() with inPlace=False wraps the
    optimized transform inside a CompositeTransform.  The copy-constructor
    sitk.Euler3DTransform(composite) raises 'not of type Euler3DTransform', so we
    pull the parameters out of the inner transform and stuff them into a fresh
    Euler3DTransform instead.
    """
    if isinstance(tx, sitk.Euler3DTransform):
        return tx
    inner: sitk.Transform = (
        tx.GetNthTransform(0) if isinstance(tx, sitk.CompositeTransform) else tx
    )
    result = sitk.Euler3DTransform()
    result.SetParameters(inner.GetParameters())
    result.SetFixedParameters(inner.GetFixedParameters())
    return result


def _sitk_tx_to_matrix(tx: sitk.Euler3DTransform) -> np.ndarray:
    """Convert centered Euler3DTransform to 4x4 affine (world-space)."""
    matrix = np.eye(4, dtype=np.float64)
    rotation = np.array(tx.GetMatrix(), dtype=np.float64).reshape(3, 3)
    center = np.array(tx.GetCenter(), dtype=np.float64)
    translation = np.array(tx.GetTranslation(), dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation + center - rotation @ center
    return matrix


def _sitk_center_sidecar_path(mat_path: Path) -> Path:
    return mat_path.with_suffix(mat_path.suffix + ".center.txt")


def _sitk_save_transform_artifacts(
    tx: sitk.Euler3DTransform, mat_path: Path
) -> None:
    """Save 4x4 affine and rotation-center sidecar for resume/QC."""
    np.savetxt(mat_path, _sitk_tx_to_matrix(tx))
    np.savetxt(_sitk_center_sidecar_path(mat_path), np.array(tx.GetCenter(), dtype=np.float64))


def _sitk_copy_euler(tx: sitk.Euler3DTransform) -> sitk.Euler3DTransform:
    """Deep-copy a centered Euler3DTransform."""
    out = sitk.Euler3DTransform()
    out.SetFixedParameters(tx.GetFixedParameters())
    out.SetParameters(tx.GetParameters())
    return out


def _sitk_stage2_metric(
    fixed: sitk.Image,
    moving: sitk.Image,
    tx: sitk.Euler3DTransform,
    sitk_config: dict[str, Any],
    modality: str,
    shrink_factors: list[int],
    smoothing_sigmas: list[float],
) -> float:
    """Evaluate stage-2 Mattes MI at tx (0 gradient steps) for accept/reject guard."""
    reg = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg, sitk_config, stage2_gradient=True)
    reg.SetInterpolator(sitk.sitkLinear)
    if modality == "func":
        reg.SetMetricSamplingPercentage(_SITK_TRANSLATION_SAMPLING_PERCENTAGE)
    reg.SetOptimizerAsGradientDescent(
        learningRate=1.0,
        numberOfIterations=0,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10,
    )
    reg.SetOptimizerScalesFromPhysicalShift()
    reg.SetShrinkFactorsPerLevel(shrink_factors)
    reg.SetSmoothingSigmasPerLevel(smoothing_sigmas)
    reg.SetSmoothingSigmasAreSpecifiedInPhysicalUnits(True)
    reg.SetInitialTransform(tx, inPlace=False)
    reg.Execute(fixed, moving)
    return float(reg.GetMetricValue())


def _sitk_transform_from_matrix(
    mat: np.ndarray, center_path: Path | None = None
) -> sitk.Euler3DTransform:
    """Rebuild centered Euler3DTransform from saved affine + optional center sidecar."""
    rotation = mat[:3, :3].astype(np.float64)
    t_full = mat[:3, 3].astype(np.float64)
    tx = sitk.Euler3DTransform()
    if center_path is not None and center_path.is_file():
        center = np.loadtxt(center_path, dtype=np.float64).reshape(-1)
        t_param = t_full - center + rotation @ center
        tx.SetCenter(center.tolist())
        tx.SetMatrix(rotation.reshape(-1).tolist())
        tx.SetTranslation(t_param.tolist())
    else:
        tx.SetMatrix(rotation.reshape(-1).tolist())
        tx.SetTranslation(t_full.tolist())
    return tx


def _sitk_register(
    fixedf: Path,
    movingf: Path,
    work_dir: Path,
    output_prefix: str,
    sitk_config: dict[str, Any],
    modality: str = "anat",
) -> dict[str, Any]:
    """Rigid registration: coarse+fine rotation search, translation refine, gradient pyramid."""
    fixed_path = validate_input_file(fixedf, logger)
    moving_path = validate_input_file(movingf, logger)
    work_dir = ensure_working_directory(work_dir, logger)

    fixed = _sitk_ensure_3d(sitk.ReadImage(str(fixed_path), sitk.sitkFloat32))
    moving = _sitk_ensure_3d(sitk.ReadImage(str(moving_path), sitk.sitkFloat32))

    init_tx = _unwrap_euler3d(
        sitk.CenteredTransformInitializer(
            fixed,
            moving,
            sitk.Euler3DTransform(),
            sitk.CenteredTransformInitializerFilter.MOMENTS,
        )
    )

    min_sp = _sitk_min_spacing(fixed)
    lr_physical = min_sp * 0.5
    lr_multiplier = float(sitk_config["learning_rate"])
    lr_stage2 = lr_multiplier * lr_physical
    lr_stage15 = lr_physical

    coarse_step_deg = float(sitk_config.get("coarse_step_deg", _SITK_COARSE_STEP_DEG))
    fine_step_deg = float(
        sitk_config.get("fine_step_deg", _SITK_FINE_STEP_DEG_DEFAULT)
    )

    shrink_coarse = _sitk_shrink_for_target_mm(fixed, _SITK_STAGE1_TARGET_MM)
    fixed_coarse = sitk.Shrink(fixed, [shrink_coarse] * 3)
    moving_coarse = sitk.Shrink(moving, [shrink_coarse] * 3)
    _poses_coarse, fallback_coarse = _sitk_exhaustive_rotation(
        fixed_coarse,
        moving_coarse,
        init_tx,
        coarse_step_deg,
        sitk_config,
        f"stage 1a (coarse @ ~{shrink_coarse * min_sp:.1f} mm)",
    )
    coarse_tx, _ = _sitk_refine_translation_only(
        fixed_coarse,
        moving_coarse,
        fallback_coarse,
        sitk_config,
        modality,
        learning_rate_mm=lr_stage15,
    )
    logger.info(
        "SimpleITK stage 1a+: translation refined on coarse winner (lr=%.4f mm)",
        lr_stage15,
    )

    stage15_target_mm = _sitk_stage15_target_mm(fixed)
    shrink_fine = _sitk_shrink_for_target_mm(fixed, stage15_target_mm)
    fixed_fine = sitk.Shrink(fixed, [shrink_fine] * 3)
    moving_fine = sitk.Shrink(moving, [shrink_fine] * 3)
    poses_fine, fallback_fine = _sitk_exhaustive_rotation(
        fixed_fine,
        moving_fine,
        coarse_tx,
        fine_step_deg,
        sitk_config,
        f"stage 1b (fine @ ~{shrink_fine * min_sp:.1f} mm)",
    )

    candidates = _sitk_select_translation_candidates(poses_fine)
    logger.info(
        "SimpleITK stage 1.5: translation refinement for %d/%d fine poses "
        "(full-res; coarse poses=%d; lr=%.4f mm)",
        len(candidates),
        len(poses_fine),
        len(_poses_coarse),
        lr_stage15,
    )

    best_combined_metric = float("inf")
    best_combined_tx: sitk.Euler3DTransform | None = None
    for _, params in candidates:
        moments_tx = _sitk_pose_with_moments_translation(
            fixed, moving, init_tx, params
        )
        refined_tx, m = _sitk_refine_translation_only(
            fixed,
            moving,
            moments_tx,
            sitk_config,
            modality,
            learning_rate_mm=lr_stage15,
        )
        if m < best_combined_metric:
            best_combined_metric = m
            best_combined_tx = refined_tx

    fine_full_tx, fine_full_metric = _sitk_refine_translation_only(
        fixed,
        moving,
        _sitk_pose_with_moments_translation(
            fixed,
            moving,
            init_tx,
            list(fallback_fine.GetParameters()),
        ),
        sitk_config,
        modality,
        learning_rate_mm=lr_stage15,
    )
    if (
        best_combined_tx is not None
        and best_combined_metric <= fine_full_metric
    ):
        init_stage2 = best_combined_tx
    else:
        init_stage2 = fine_full_tx
        if best_combined_tx is not None:
            logger.info(
                "SimpleITK stage 1.5: using fine-grid winner "
                "(candidate %.6f vs fine %.6f)",
                best_combined_metric,
                fine_full_metric,
            )

    fine_iters = int(sitk_config["fine_iters"])
    shrink_factors, smoothing_sigmas = _sitk_pyramid_for_modality(fixed, modality)
    init_stage2_metric = _sitk_stage2_metric(
        fixed,
        moving,
        init_stage2,
        sitk_config,
        modality,
        shrink_factors,
        smoothing_sigmas,
    )
    logger.info(
        "SimpleITK stage 2: Mattes MI gradient (fine_iters=%d, lr=%.4f mm, "
        "pyramid shrinks=%s, sigmas_mm=%s, init_metric=%.6f)",
        fine_iters,
        lr_stage2,
        shrink_factors,
        smoothing_sigmas,
        init_stage2_metric,
    )
    reg2 = sitk.ImageRegistrationMethod()
    _set_sitk_metric(reg2, sitk_config, stage2_gradient=True)
    reg2.SetInterpolator(sitk.sitkLinear)
    if modality == "func":
        reg2.SetMetricSamplingPercentage(_SITK_TRANSLATION_SAMPLING_PERCENTAGE)
    reg2.SetOptimizerAsGradientDescent(
        learningRate=lr_stage2,
        numberOfIterations=fine_iters,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10,
    )
    reg2.SetOptimizerScalesFromPhysicalShift()
    reg2.SetShrinkFactorsPerLevel(shrink_factors)
    reg2.SetSmoothingSigmasPerLevel(smoothing_sigmas)
    reg2.SetSmoothingSigmasAreSpecifiedInPhysicalUnits(True)
    reg2.SetInitialTransform(init_stage2, inPlace=False)
    stage2_tx = _unwrap_euler3d(reg2.Execute(fixed, moving))
    stage2_metric = float(reg2.GetMetricValue())
    if stage2_metric > init_stage2_metric:
        logger.warning(
            "SimpleITK stage 2: metric worsened (%.6f > %.6f); keeping stage-1.5 init",
            stage2_metric,
            init_stage2_metric,
        )
        final_tx = _sitk_copy_euler(init_stage2)
    else:
        final_tx = stage2_tx
        logger.info("SimpleITK stage 2: final metric %.6f", stage2_metric)

    forward_transform = work_dir / f"{output_prefix}.mat"
    _sitk_save_transform_artifacts(final_tx, forward_transform)
    validate_output_file(forward_transform, logger)
    logger.info("SimpleITK transform saved to %s", forward_transform)

    return {
        "forward_transform": str(forward_transform),
        "transform_obj": final_tx,
    }


def _sitk_apply_transforms(
    movingf: Path,
    outputf_name: str,
    reff: Path,
    work_dir: Path,
    transform_obj: sitk.Euler3DTransform,
) -> dict[str, str]:
    """Apply SimpleITK rigid transform to an image via trilinear resampling."""
    moving_path = validate_input_file(movingf, logger)
    ref_path = validate_input_file(reff, logger)
    work_dir = ensure_working_directory(work_dir, logger)

    fixed = _sitk_ensure_3d(sitk.ReadImage(str(ref_path), sitk.sitkFloat32))
    moving = _sitk_ensure_3d(sitk.ReadImage(str(moving_path), sitk.sitkFloat32))
    resampled = sitk.Resample(
        moving,
        fixed,
        transform_obj,
        sitk.sitkLinear,
        0.0,
        moving.GetPixelID(),
    )

    output_path = work_dir / outputf_name
    sitk.WriteImage(resampled, str(output_path))
    validate_output_file(output_path, logger)
    return {"imagef_registered": str(output_path)}


def run_sitk(
    preprocess: PreprocessResult,
    work_dir: Path,
    sitk_config: dict[str, Any],
    output_name: str = "conformed_sitk.nii.gz",
    modality: str = "anat",
) -> MethodResult:
    """SimpleITK rigid registration + apply (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)
    label = sitk_config["label"]

    t_total_start = time.perf_counter()
    t_reg_start = time.perf_counter()
    registration_result = _sitk_register(
        fixedf=preprocess.template_for_reg,
        movingf=preprocess.brain_f,
        work_dir=work_dir,
        output_prefix=f"conform_scanner2native_sitk_{label}",
        sitk_config=sitk_config,
        modality=modality,
    )
    reg_time_s = time.perf_counter() - t_reg_start

    transform_obj = registration_result["transform_obj"]
    apply_result = _sitk_apply_transforms(
        movingf=preprocess.full_head,
        outputf_name=output_name,
        reff=preprocess.template_for_xfm,
        work_dir=work_dir,
        transform_obj=transform_obj,
    )
    conformed_f = Path(apply_result["imagef_registered"])
    brain_apply = _sitk_apply_transforms(
        movingf=preprocess.brain_f,
        outputf_name=conformed_brain_path(conformed_f).name,
        reff=preprocess.template_for_xfm,
        work_dir=work_dir,
        transform_obj=transform_obj,
    )
    total_time_s = time.perf_counter() - t_total_start

    return MethodResult(
        conformed_f=conformed_f,
        conformed_brain_f=Path(brain_apply["imagef_registered"]),
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
    )


def run_antsai(
    preprocess: PreprocessResult,
    work_dir: Path,
    antsai_config: dict[str, Any],
    output_name: str = "conformed_antsai.nii.gz",
) -> MethodResult:
    """antsAI rigid registration + antsApplyTransforms (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)
    xfm_path = work_dir / "antsAI_conform.mat"
    conformed_f = work_dir / output_name
    ai = antsai_config
    fixed = str(preprocess.template_for_reg)
    moving = str(preprocess.brain_f)

    cmd_reg = [
        "antsAI",
        "-d",
        str(ai["dimensionality"]),
        "-m",
        _antsai_metric_string(fixed, moving, ai),
        "-t",
        _antsai_transform_string(ai),
        "-p",
        str(ai["align_principal_axes"]),
        "-s",
        _antsai_search_string(ai),
        "-c",
        str(ai["convergence_iterations"]),
        "-o",
        str(xfm_path),
        "-v",
        str(ai["verbose"]),
        "--random-seed",
        str(ai["random_seed"]),
    ]

    t_total_start = time.perf_counter()
    t_reg_start = time.perf_counter()
    returncode, _, stderr = run_command(cmd_reg, step_logger=logger)
    reg_time_s = time.perf_counter() - t_reg_start
    if returncode != 0:
        raise RuntimeError(f"antsAI failed (exit {returncode}): {stderr}")
    validate_output_file(xfm_path, logger)

    conformed_brain_f = conformed_brain_path(conformed_f)
    for moving, output in (
        (preprocess.full_head, conformed_f),
        (preprocess.brain_f, conformed_brain_f),
    ):
        cmd_apply = [
            "antsApplyTransforms",
            "-d",
            "3",
            "-i",
            str(moving),
            "-r",
            str(preprocess.template_for_xfm),
            "-o",
            str(output),
            "-t",
            str(xfm_path),
            "-n",
            "Linear",
        ]
        returncode, _, stderr = run_command(cmd_apply, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(
                f"antsApplyTransforms failed (exit {returncode}): {stderr}"
            )
        validate_output_file(output, logger)
    total_time_s = time.perf_counter() - t_total_start

    return MethodResult(
        conformed_f=conformed_f,
        conformed_brain_f=conformed_brain_f,
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
    )


def _brain_mask(
    fixed: np.ndarray, moving: np.ndarray, percentile: float = 10.0
) -> np.ndarray:
    """Voxels used for overlap metrics (positive intensities in both images)."""
    pos_fixed = fixed[fixed > 0]
    pos_moving = moving[moving > 0]
    if pos_fixed.size == 0 or pos_moving.size == 0:
        return np.zeros(fixed.shape, dtype=bool)
    thr_fixed = np.percentile(pos_fixed, percentile)
    thr_moving = np.percentile(pos_moving, percentile)
    return (fixed > thr_fixed) & (moving > thr_moving)


def _discretize_for_nmi(values: np.ndarray, n_bins: int = 64) -> np.ndarray:
    vmin, vmax = float(values.min()), float(values.max())
    if vmax <= vmin:
        return np.zeros_like(values, dtype=np.int32)
    bins = np.linspace(vmin, vmax, n_bins + 1)[1:-1]
    return np.digitize(values, bins).astype(np.int32)


def _ensure_conformed_brain(
    preprocess: PreprocessResult,
    work_dir: Path,
    conformed_f: Path,
    method: str,
    param_set: str = "",
) -> Path:
    """Apply cached transform to brain_f when resuming without *_brain.nii.gz."""
    brain_out = conformed_brain_path(conformed_f)
    if _is_valid_output(brain_out):
        return brain_out
    work_dir = ensure_working_directory(work_dir, logger)
    if method == "flirt":
        xfm = work_dir / "conform_scanner2native.mat"
        if not xfm.is_file():
            raise FileNotFoundError(f"FLIRT transform not found for brain apply: {xfm}")
        flirt_apply_transforms(
            movingf=str(preprocess.brain_f),
            outputf_name=brain_out.name,
            reff=str(preprocess.template_for_xfm),
            working_dir=str(work_dir),
            transformf=str(xfm),
            logger=logger,
            interpolation="trilinear",
            generate_tmean=False,
        )
    elif method == "sitk":
        prefix = f"conform_scanner2native_sitk_{param_set}"
        xfm = work_dir / f"{prefix}.mat"
        if not xfm.is_file():
            raise FileNotFoundError(f"SimpleITK transform not found for brain apply: {xfm}")
        transform_obj = _sitk_transform_from_matrix(
            np.loadtxt(xfm),
            center_path=_sitk_center_sidecar_path(xfm),
        )
        _sitk_apply_transforms(
            movingf=preprocess.brain_f,
            outputf_name=brain_out.name,
            reff=preprocess.template_for_xfm,
            work_dir=work_dir,
            transform_obj=transform_obj,
        )
    elif method == "antsai":
        xfm = work_dir / "antsAI_conform.mat"
        if not xfm.is_file():
            raise FileNotFoundError(f"antsAI transform not found for brain apply: {xfm}")
        cmd_apply = [
            "antsApplyTransforms",
            "-d",
            "3",
            "-i",
            str(preprocess.brain_f),
            "-r",
            str(preprocess.template_for_xfm),
            "-o",
            str(brain_out),
            "-t",
            str(xfm),
            "-n",
            "Linear",
        ]
        returncode, _, stderr = run_command(cmd_apply, step_logger=logger)
        if returncode != 0:
            raise RuntimeError(
                f"antsApplyTransforms (brain) failed (exit {returncode}): {stderr}"
            )
        validate_output_file(brain_out, logger)
    else:
        raise ValueError(f"Unknown method for brain apply: {method}")
    return brain_out


def compute_metrics(
    conformed_brain_f: Path, template_f: Path, n_bins: int = 64
) -> dict[str, float]:
    """NMI and NCC between skull-stripped conformed brain and template (same grid)."""
    fixed_data = np.ascontiguousarray(
        nib.load(template_f).get_fdata(), dtype=np.float64
    )
    moving_data = np.ascontiguousarray(
        nib.load(conformed_brain_f).get_fdata(), dtype=np.float64
    )
    if moving_data.ndim == 4:
        moving_data = moving_data.mean(axis=-1)
    if fixed_data.shape != moving_data.shape:
        raise ValueError(
            f"Shape mismatch for metrics: template {fixed_data.shape} vs brain {moving_data.shape}"
        )

    mask = _brain_mask(fixed_data, moving_data)
    if not np.any(mask):
        return {"nmi": float("nan"), "ncc": float("nan")}

    fixed_vals = fixed_data[mask]
    moving_vals = moving_data[mask]
    fixed_disc = _discretize_for_nmi(fixed_vals, n_bins=n_bins)
    moving_disc = _discretize_for_nmi(moving_vals, n_bins=n_bins)
    nmi = float(normalized_mutual_info_score(fixed_disc, moving_disc))
    ncc = float(np.corrcoef(fixed_vals, moving_vals)[0, 1])
    return {"nmi": nmi, "ncc": ncc}


def _generate_conform_qc(
    preprocess: PreprocessResult,
    conformed_f: Path,
    qc_path: Path,
    modality: str = "anat",
    skip_if_exists: bool = False,
) -> str:
    """Create conform QC overlay PNG; return path or empty string on failure."""
    if skip_if_exists and _is_valid_output(qc_path):
        logger.info("QC: skip (exists) %s", qc_path.name)
        return str(qc_path)
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    result = create_conform_qc(
        conformed_file=str(conformed_f),
        template_file=str(preprocess.template_for_xfm),
        save_f=str(qc_path),
        modality=modality,
        num_slices=4,
        logger=logger,
    )
    if result:
        return next(iter(result.values()), "")
    return ""


def _benchmark_row_from_result(
    stem: str,
    method: str,
    param_set: str,
    conformed_f: Path,
    preprocess: PreprocessResult,
    qc_path: Path,
    reg_time_s: float,
    total_time_s: float,
    work_dir: Path,
    conformed_brain_f: Path | None = None,
    modality: str = "anat",
    resume: bool = True,
) -> BenchmarkRow:
    metrics_f = conformed_brain_f or conformed_brain_path(conformed_f)
    if not _is_valid_output(metrics_f):
        metrics_f = _ensure_conformed_brain(
            preprocess, work_dir, conformed_f, method, param_set
        )
    metrics = compute_metrics(metrics_f, preprocess.template_for_xfm)
    qc_snapshot_path = _generate_conform_qc(
        preprocess,
        conformed_f,
        qc_path,
        modality=modality,
        skip_if_exists=resume,
    )
    return BenchmarkRow(
        image=stem,
        method=method,
        param_set=param_set,
        nmi=metrics["nmi"],
        ncc=metrics["ncc"],
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
        modality=modality,
        qc_snapshot_path=qc_snapshot_path,
    )


def _print_summary_table(rows: list[BenchmarkRow]) -> None:
    if not rows:
        print("No results.")
        return
    headers = [
        "modality",
        "image",
        "method",
        "param_set",
        "nmi",
        "ncc",
        "reg_time_s",
        "total_time_s",
    ]
    col_widths = [
        max(len(h), max(len(str(getattr(r, h))) for r in rows)) for h in headers
    ]
    fmt = "  ".join(f"{{:{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("-" * (sum(col_widths) + 2 * (len(headers) - 1)))
    for row in rows:
        print(
            fmt.format(
                row.modality,
                row.image,
                row.method,
                row.param_set,
                f"{row.nmi:.4f}",
                f"{row.ncc:.4f}",
                f"{row.reg_time_s:.2f}",
                f"{row.total_time_s:.2f}",
            )
        )


def _fmt_float(val: float, decimals: int = 4) -> str:
    if val != val:
        return "—"
    return f"{val:.{decimals}f}"


def _fmt_float_attr(val: float) -> str:
    """Numeric string for HTML data-* sort attributes (empty if NaN)."""
    if val != val:
        return ""
    return str(val)


def _embed_image_base64(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_file():
        return ""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _best_row_for_image(image_rows: list[BenchmarkRow]) -> BenchmarkRow | None:
    valid = [r for r in image_rows if r.nmi == r.nmi]
    if not valid:
        return None
    return max(valid, key=lambda r: r.nmi)


def _qc_anchor_id(row: BenchmarkRow) -> str:
    return (
        f"qc-{html.escape(row.modality)}-{html.escape(row.image)}-"
        f"{html.escape(row.param_set)}"
    )


@dataclass
class ParamSummary:
    modality: str
    method: str
    param_set: str
    n: int
    nmi_mean: float
    nmi_std: float
    ncc_mean: float
    ncc_std: float
    reg_time_mean: float
    reg_time_std: float
    total_time_mean: float
    total_time_std: float


def _nanmean_std(values: list[float]) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return float("nan"), float("nan")
    if valid.size == 1:
        return float(valid[0]), 0.0
    return float(np.mean(valid)), float(np.std(valid, ddof=1))


def _summarize_by_param(rows: list[BenchmarkRow]) -> list[ParamSummary]:
    buckets: dict[tuple[str, str, str], list[BenchmarkRow]] = {}
    for row in rows:
        key = (row.modality, row.method, row.param_set)
        buckets.setdefault(key, []).append(row)
    summaries: list[ParamSummary] = []
    for (modality, method, param_set), group_rows in buckets.items():
        nmi_mean, nmi_std = _nanmean_std([r.nmi for r in group_rows])
        ncc_mean, ncc_std = _nanmean_std([r.ncc for r in group_rows])
        reg_mean, reg_std = _nanmean_std([r.reg_time_s for r in group_rows])
        total_mean, total_std = _nanmean_std([r.total_time_s for r in group_rows])
        summaries.append(
            ParamSummary(
                modality=modality,
                method=method,
                param_set=param_set,
                n=len(group_rows),
                nmi_mean=nmi_mean,
                nmi_std=nmi_std,
                ncc_mean=ncc_mean,
                ncc_std=ncc_std,
                reg_time_mean=reg_mean,
                reg_time_std=reg_std,
                total_time_mean=total_mean,
                total_time_std=total_std,
            )
        )
    summaries.sort(
        key=lambda s: (s.modality, _METHOD_ORDER.get(s.method, 9), s.param_set)
    )
    return summaries


def _best_summary_indices(summaries: list[ParamSummary]) -> set[int]:
    """Index of highest mean-NMI row per modality (ties: first wins)."""
    best: dict[str, tuple[int, float]] = {}
    for idx, summary in enumerate(summaries):
        if summary.nmi_mean != summary.nmi_mean:
            continue
        prev = best.get(summary.modality)
        if prev is None or summary.nmi_mean > prev[1]:
            best[summary.modality] = (idx, summary.nmi_mean)
    return {idx for idx, _ in best.values()}


def _fmt_mean_std(mean: float, std: float, decimals: int = 4) -> str:
    if mean != mean:
        return "—"
    mean_s = _fmt_float(mean, decimals)
    if std != std:
        return mean_s
    if std == 0.0:
        return mean_s
    return f"{mean_s} ± {_fmt_float(std, decimals)}"


def _html_metrics_row(
    row: BenchmarkRow,
    row_class: str,
    anchor_prefix: str = "qc",
) -> str:
    qc_cell = "—"
    anchor = _qc_anchor_id(row)
    if row.qc_snapshot_path and Path(row.qc_snapshot_path).is_file():
        qc_cell = f'<a href="#{anchor}">view</a>'
    return (
        f'<tr class="{row_class}" data-image="{html.escape(row.image)}" '
        f'data-modality="{html.escape(row.modality)}" '
        f'data-param="{html.escape(row.param_set)}" '
        f'data-method="{html.escape(row.method)}" '
        f'data-nmi="{_fmt_float_attr(row.nmi)}" data-ncc="{_fmt_float_attr(row.ncc)}" '
        f'data-reg="{_fmt_float_attr(row.reg_time_s)}">'
        f"<td>{html.escape(row.param_set)}</td>"
        f"<td>{html.escape(row.method)}</td>"
        f"<td>{_fmt_float(row.nmi, 4)}</td>"
        f"<td>{_fmt_float(row.ncc, 4)}</td>"
        f"<td>{_fmt_float(row.reg_time_s, 2)}</td>"
        f"<td>{qc_cell}</td>"
        f"</tr>"
    )


def _html_card_stats_table(row: BenchmarkRow) -> str:
    return (
        '<table class="stats-table">'
        f"<tr><th>NMI</th><td>{_fmt_float(row.nmi, 4)}</td></tr>"
        f"<tr><th>NCC</th><td>{_fmt_float(row.ncc, 4)}</td></tr>"
        f"<tr><th>reg</th><td>{_fmt_float(row.reg_time_s, 2)} s</td></tr>"
        "</table>"
    )


def _html_summary_row(summary: ParamSummary, row_class: str, show_modality: bool = True) -> str:
    vis_key = html.escape(f"{summary.modality}::{summary.param_set}")
    vis_cell = (
        f'<td class="vis-inspec-cell">'
        f'<input type="checkbox" class="vis-inspec-cb" data-vis-key="{vis_key}"/>'
        f"</td>"
    )
    modality_cell = f"<td>{html.escape(summary.modality)}</td>" if show_modality else ""
    return (
        f'<tr class="{row_class}" '
        f'data-modality="{html.escape(summary.modality)}" '
        f'data-param="{html.escape(summary.param_set)}" '
        f'data-method="{html.escape(summary.method)}" '
        f'data-n="{summary.n}" '
        f'data-nmi="{_fmt_float_attr(summary.nmi_mean)}" '
        f'data-ncc="{_fmt_float_attr(summary.ncc_mean)}" '
        f'data-reg="{_fmt_float_attr(summary.reg_time_mean)}">'
        f"{vis_cell}"
        f"{modality_cell}"
        f"<td>{html.escape(summary.param_set)}</td>"
        f"<td>{html.escape(summary.method)}</td>"
        f"<td>{summary.n}</td>"
        f"<td>{_fmt_mean_std(summary.nmi_mean, summary.nmi_std, 4)}</td>"
        f"<td>{_fmt_mean_std(summary.ncc_mean, summary.ncc_std, 4)}</td>"
        f"<td>{_fmt_mean_std(summary.reg_time_mean, summary.reg_time_std, 2)}</td>"
        f"</tr>"
    )


_SORTABLE_TABLE_JS = """
(function() {
  // Safe localStorage helpers — silently no-op if storage is unavailable.
  function lsGet(k)    { try { return localStorage.getItem(k); }    catch(e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); }        catch(e) {} }
  function lsDel(k)    { try { localStorage.removeItem(k); }        catch(e) {} }

  var reportId = (document.body.dataset.reportId || '').replace(/[^a-zA-Z0-9_\-\/\.]/g, '_');
  var VIS_PREFIX  = 'vis_inspec::' + reportId + '::';   // key prefix for checkbox state
  var SORT_PREFIX = 'sort_state::' + reportId + '::';   // key prefix for sort state per table

  function initSortableTable(table) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;

    var tableId = table.id || '';
    var colIndex = table.dataset.colIndex
      ? JSON.parse(table.dataset.colIndex)
      : { param_set: 1, method: 2 };
    var dataKey = { reg_time_s: 'reg', total_time_s: 'total', n: 'n' };

    // Restore per-table sort state from localStorage, fall back to data-* defaults.
    var defaultKey = table.dataset.defaultSort || 'nmi';
    var defaultAsc = table.dataset.defaultAsc === 'true';
    var sortKey = defaultKey;
    var sortAsc = defaultAsc;
    if (tableId) {
      var saved = lsGet(SORT_PREFIX + tableId);
      if (saved) {
        try {
          var parsed = JSON.parse(saved);
          if (parsed && parsed.key) { sortKey = parsed.key; sortAsc = !!parsed.asc; }
        } catch(e) {}
      }
    }

    function saveSortState() {
      if (tableId) lsSet(SORT_PREFIX + tableId, JSON.stringify({ key: sortKey, asc: sortAsc }));
    }

    function cellValue(row, key) {
      if (key in colIndex) return row.cells[colIndex[key]].textContent;
      var dk = dataKey[key] || key;
      var v = parseFloat(row.dataset[dk]);
      return isNaN(v) ? -Infinity : v;
    }

    function sortRows(key, asc) {
      var trs = Array.from(tbody.querySelectorAll('tr'));
      var normal = trs.filter(function(r) { return !r.classList.contains('vis-failed'); });
      var failed = trs.filter(function(r) { return r.classList.contains('vis-failed'); });
      function cmp(a, b) {
        var va = cellValue(a, key), vb = cellValue(b, key);
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
      }
      normal.sort(cmp);
      failed.sort(cmp);
      normal.concat(failed).forEach(function(r) { tbody.appendChild(r); });
    }

    // Restore inspec_fail checkbox states, then wire change → immediate save + re-sort.
    tbody.querySelectorAll('.vis-inspec-cb').forEach(function(cb) {
      var visKey = cb.dataset.visKey;
      if (lsGet(VIS_PREFIX + visKey) === '1') {
        cb.checked = true;
        cb.closest('tr').classList.add('vis-failed');
      }
      cb.addEventListener('change', function() {
        var tr = cb.closest('tr');
        if (cb.checked) {
          lsSet(VIS_PREFIX + visKey, '1');
          tr.classList.add('vis-failed');
        } else {
          lsDel(VIS_PREFIX + visKey);
          tr.classList.remove('vis-failed');
        }
        sortRows(sortKey, sortAsc);
      });
    });

    // Wire column-header sort clicks — save new sort state immediately per table.
    table.querySelectorAll('th.sortable').forEach(function(th) {
      th.addEventListener('click', function() {
        var key = th.dataset.sort;
        if (sortKey === key) { sortAsc = !sortAsc; }
        else { sortKey = key; sortAsc = key in colIndex; }
        saveSortState();
        sortRows(sortKey, sortAsc);
      });
    });

    sortRows(sortKey, sortAsc);
  }

  document.querySelectorAll('table.sortable-metrics-table').forEach(initSortableTable);
})();
"""


def _benchmark_methods_description(methods: list[str] | None = None) -> str:
    """Human-readable summary of active registration backends for the HTML report."""
    if methods is None:
        methods = ["flirt", "simpleitk", "antsai"]
    methods_set = set(methods)
    parts: list[str] = []
    if "flirt" in methods_set:
        parts.append("FLIRT baseline (1 run)")
    if "simpleitk" in methods_set:
        d, f = _SITK_PROFILE_DEFAULT, _SITK_PROFILE_FUNC
        parts.append(
            f"{len(_SITK_PARAM_GRIDS['default'])} SimpleITK sets "
            f"(anat/t2w; {d.metric}, rot {_SITK_COARSE_STEP_DEG}°+fine) + "
            f"{len(_SITK_PARAM_GRIDS['func'])} (func; {f.metric}, bins {f.histogram_bins}, "
            f"lr {f.learning_rates})"
        )
    if "antsai" in methods_set:
        parts.append(f"{len(ANTS_AI_PARAM_GRID)} antsAI parameter sets")
    return " + ".join(parts) if parts else "no registration backends"


def refresh_combined_report(
    report_root: Path,
    modalities: tuple[str, ...] = ("anat", "func", "t2w"),
    auto_refresh_sec: int = 0,
    active_methods: list[str] | None = None,
) -> Path:
    """Rewrite OUTPUT_DIR/report.html from per-modality metrics.csv files."""
    rows = load_all_modality_rows(report_root, modalities)
    return generate_html_report(
        rows,
        report_root,
        all_modalities=modalities,
        auto_refresh_sec=auto_refresh_sec,
        active_methods=active_methods,
    )


def generate_html_report(
    rows: list[BenchmarkRow],
    output_dir: Path,
    all_modalities: tuple[str, ...] = ("anat", "func", "t2w"),
    auto_refresh_sec: int = 0,
    active_methods: list[str] | None = None,
) -> Path:
    """Write self-contained HTML report with metrics table and embedded QC images."""
    report_path = output_dir / "report.html"
    param_summaries = _summarize_by_param(rows)
    best_summary_idxs = _best_summary_indices(param_summaries)

    # Group summaries by modality preserving sorted order
    mod_to_summaries: dict[str, list[tuple[int, ParamSummary]]] = {}
    for idx, summary in enumerate(param_summaries):
        mod_to_summaries.setdefault(summary.modality, []).append((idx, summary))

    modalities = sorted({r.modality for r in rows})
    display_modalities = modalities if modalities else list(all_modalities)
    image_count = len({(r.modality, r.image) for r in rows})
    metrics_note = ", ".join(
        str(output_dir / m / "metrics.csv") for m in display_modalities
    )
    refresh_meta = (
        f'<meta http-equiv="refresh" content="{auto_refresh_sec}"/>'
        if auto_refresh_sec > 0
        else ""
    )
    refresh_note = (
        f" Page auto-reloads every {auto_refresh_sec}s while the benchmark runs."
        if auto_refresh_sec > 0
        else ""
    )
    methods_desc = _benchmark_methods_description(active_methods)
    metrics_target = (
        "skull-stripped conformed brain vs template"
        if any(m in all_modalities for m in ("anat", "func"))
        else "registered volume vs fixed reference"
    )
    if "t2w" in all_modalities and any(m in all_modalities for m in ("anat", "func")):
        metrics_target = (
            "skull-stripped conformed brain vs template (anat/func); "
            "registered T2w vs T1w fixed (t2w)"
        )

    # Build per-modality summary tables (one table per modality)
    modality_summary_tables: list[str] = []
    for mod in display_modalities:
        mod_list = mod_to_summaries.get(mod, [])
        if mod_list:
            mod_rows_html = [
                _html_summary_row(
                    summary, "best" if idx in best_summary_idxs else "", show_modality=False
                )
                for idx, summary in mod_list
            ]
        else:
            mod_rows_html = [
                '<tr><td colspan="7" class="pending">'
                "Benchmark in progress — rows appear after each parameter set completes."
                "</td></tr>"
            ]
        mod_param_count = len(mod_list)
        mod_result_count = sum(s.n for _, s in mod_list) if mod_list else 0
        mod_image_count = len({r.image for r in rows if r.modality == mod})
        mod_csv = html.escape(str(output_dir / mod / "metrics.csv"))
        mod_caption = (
            f"{mod_param_count} parameter set(s) · "
            f"{mod_result_count} result row(s) across {mod_image_count} image(s) · "
            f"metrics: {mod_csv}"
        )
        col_idx_attr = 'data-col-index=\'{"param_set":1,"method":2}\''
        modality_summary_tables.append(
            f'<div class="summary modality-summary">\n'
            f'<h3 class="summary-modality-title">{html.escape(mod.upper())}</h3>\n'
            f'<table id="summary-table-{mod}" class="sortable-metrics-table" '
            f'data-default-sort="nmi" data-default-asc="false" {col_idx_attr}>\n'
            f"<caption>{mod_caption}</caption>\n"
            f"<thead><tr>\n"
            f'  <th class="vis-inspec-th" title="Check to mark as failed by visual inspection — row moves to bottom">inspec_fail</th>\n'
            f'  <th class="sortable" data-sort="param_set">param_set</th>\n'
            f'  <th class="sortable" data-sort="method">method</th>\n'
            f'  <th class="sortable" data-sort="n">n</th>\n'
            f'  <th class="sortable" data-sort="nmi">NMI</th>\n'
            f'  <th class="sortable" data-sort="ncc">NCC</th>\n'
            f'  <th class="sortable" data-sort="reg_time_s">reg (s)</th>\n'
            f"</tr></thead>\n"
            f'<tbody>{"".join(mod_rows_html)}</tbody>\n'
            f"</table>\n</div>"
        )

    qc_sections: list[str] = []
    for modality in modalities:
        mod_rows = [r for r in rows if r.modality == modality]
        images = sorted({r.image for r in mod_rows})
        image_sections: list[str] = []
        for image in images:
            image_rows = [r for r in mod_rows if r.image == image]
            flirt_rows = [r for r in image_rows if r.method == "flirt"]
            sitk_rows = [r for r in image_rows if r.method == "sitk"]
            antsai_rows = [r for r in image_rows if r.method == "antsai"]
            ordered = flirt_rows + sitk_rows + antsai_rows
            best_row = _best_row_for_image(image_rows)
            flirt_row = flirt_rows[0] if flirt_rows else None

            summary_parts: list[str] = []
            if best_row:
                summary_parts.append(
                    f"Best: <strong>{html.escape(best_row.param_set)}</strong> "
                    f"(NMI={_fmt_float(best_row.nmi, 4)}, NCC={_fmt_float(best_row.ncc, 4)})"
                )
            if flirt_row:
                summary_parts.append(
                    f"FLIRT baseline: NMI={_fmt_float(flirt_row.nmi, 4)}, "
                    f"NCC={_fmt_float(flirt_row.ncc, 4)}"
                )
            summary_html = (
                f'<p class="image-summary">{" · ".join(summary_parts)}</p>'
                if summary_parts
                else ""
            )

            image_best_param = best_row.param_set if best_row else ""
            per_image_table_rows: list[str] = []
            for row in ordered:
                is_best = row.param_set == image_best_param and best_row is not None
                per_image_table_rows.append(
                    _html_metrics_row(row, "best" if is_best else "")
                )

            per_image_table = (
                '<div class="per-image-metrics">'
                '<table class="sortable-metrics-table image-metrics-table" '
                'data-default-sort="nmi" data-default-asc="false" '
                'data-col-index=\'{"param_set":0,"method":1}\'>'
                "<thead><tr>"
                '<th class="sortable" data-sort="param_set">param_set</th>'
                '<th class="sortable" data-sort="method">method</th>'
                '<th class="sortable" data-sort="nmi">NMI</th>'
                '<th class="sortable" data-sort="ncc">NCC</th>'
                '<th class="sortable" data-sort="reg_time_s">reg (s)</th>'
                "<th>QC</th>"
                "</tr></thead><tbody>"
                f'{"".join(per_image_table_rows)}'
                "</tbody></table></div>"
            )

            cards: list[str] = []
            for row in ordered:
                anchor_id = _qc_anchor_id(row)
                img_html = '<p class="missing">QC not available</p>'
                if row.qc_snapshot_path and Path(row.qc_snapshot_path).is_file():
                    src = _embed_image_base64(row.qc_snapshot_path)
                    if src:
                        img_html = (
                            f'<img src="{src}" alt="{html.escape(row.param_set)}"/>'
                        )

                is_best = best_row is not None and row.param_set == best_row.param_set
                badge = ' <span class="badge">best NMI</span>' if is_best else ""
                cards.append(
                    f'<div class="qc-card" id="{anchor_id}">'
                    f"<h4>{html.escape(row.param_set)}{badge}</h4>"
                    f"{_html_card_stats_table(row)}"
                    f"{img_html}"
                    f"</div>"
                )

            image_sections.append(
                f'<section class="image-section">'
                f"<h3>{html.escape(image)}</h3>"
                f"{summary_html}"
                f"{per_image_table}"
                f'<div class="qc-grid">{"".join(cards)}</div>'
                f"</section>"
            )

        qc_sections.append(
            f'<section class="modality-section">'
            f"<h2>{html.escape(modality)}</h2>"
            f'{"".join(image_sections)}'
            f"</section>"
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
{refresh_meta}
<title>Anatomical conformation benchmark</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a1e; color: #e8e8ec; margin: 0; padding: 1.5rem; }}
  h1, h2, h3 {{ color: #f0f0f5; }}
  h1 {{ margin-top: 0; }}
  .modality-section {{ margin-bottom: 3rem; border-top: 1px solid #444; padding-top: 1.5rem; }}
  .modality-section > h2 {{ text-transform: uppercase; letter-spacing: 0.05em; }}
  .summary {{ overflow-x: auto; margin-bottom: 0.5rem; }}
  .modality-summary {{ margin-bottom: 2rem; }}
  .summary-modality-title {{ text-transform: uppercase; letter-spacing: 0.05em; margin: 0.25rem 0 0.4rem; color: #ccc; font-size: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  th, td {{ border: 1px solid #444; padding: 0.4rem 0.6rem; text-align: left; }}
  th {{ background: #2a2a32; cursor: pointer; user-select: none; }}
  th.sortable:hover {{ background: #35353f; }}
  tr:nth-child(even) {{ background: #222228; }}
  tr.best {{ background: #1e3d2a !important; }}
  tr.best td {{ font-weight: 600; }}
  tr.vis-failed {{ background: #3d1f1f !important; opacity: 0.75; }}
  tr.vis-failed td {{ color: #999; }}
  .vis-inspec-cell {{ text-align: center; width: 5rem; }}
  .vis-inspec-th {{ text-align: center !important; cursor: default !important; font-weight: normal; font-size: 0.8rem; color: #aaa; }}
  .per-image-metrics {{ overflow-x: auto; margin: 0.75rem 0 1rem; }}
  .image-summary {{ font-size: 0.9rem; color: #bbb; margin: 0.25rem 0 0.5rem; }}
  .qc-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }}
  .qc-card {{ background: #25252c; border-radius: 6px; padding: 0.75rem; }}
  .qc-card h4 {{ margin: 0 0 0.35rem; font-size: 0.95rem; }}
  .stats-table {{ width: 100%; font-size: 0.75rem; margin: 0 0 0.5rem; border-collapse: collapse; }}
  .stats-table th {{ background: transparent; color: #888; font-weight: normal; width: 3.5rem; cursor: default; }}
  .stats-table td {{ color: #ddd; }}
  .qc-card img {{ width: 100%; height: auto; display: block; border-radius: 4px; }}
  .badge {{ background: #2d6a4f; color: #fff; font-size: 0.7rem; padding: 0.1rem 0.35rem; border-radius: 3px; }}
  .missing {{ color: #888; font-size: 0.8rem; }}
  .image-section {{ margin-bottom: 2.5rem; border-top: 1px solid #333; padding-top: 1.5rem; }}
  a {{ color: #6eb5ff; }}
  caption {{ caption-side: bottom; font-size: 0.8rem; color: #888; padding-top: 0.5rem; text-align: left; }}
  td.pending {{ color: #888; font-style: italic; text-align: center; }}
</style>
</head>
<body data-report-id="{html.escape(str(output_dir))}">
<h1>Anatomical conformation benchmark</h1>
<p>{html.escape(methods_desc)} per image per modality.
   NMI/NCC computed on {html.escape(metrics_target)}.
   Summary tables (one per modality): mean ± std across images (green = highest mean NMI per modality).
   Check <em>inspec_fail</em> to flag a parameter set as failed by visual inspection — it drops to the bottom of its table and is remembered across page reloads.
   Per-image tables: green = best NMI for that image. Click column headers to sort.{refresh_note}</p>

{"".join(modality_summary_tables)}

{"".join(qc_sections)}

<script>
{_SORTABLE_TABLE_JS}
</script>
</body>
</html>
"""

    report_path.write_text(html_doc, encoding="utf-8")
    logger.info("Wrote HTML report to %s (%d rows)", report_path, len(rows))
    return report_path


def _run_and_record_variant(
    *,
    stem: str,
    method: str,
    param_set: str,
    method_label: str,
    conformed_f: Path,
    qc_path: Path,
    preprocess: PreprocessResult,
    method_dir: Path,
    csv_path: Path,
    metrics_store: dict[tuple[str, str], BenchmarkRow],
    modality: str,
    resume: bool,
    run_registration: Callable[[], MethodResult],
    report_root: Path | None,
    report_modalities: tuple[str, ...],
    report_auto_refresh_sec: int,
    active_methods: list[str] | None = None,
) -> BenchmarkRow:
    """Run or resume one registration variant, record metrics, refresh report."""
    logger.info("--- Method: %s (%s) ---", method, method_label)
    conformed_brain_f: Path | None = None
    if resume and _is_valid_output(conformed_f):
        logger.info("%s: skip registration (exists) %s", method, conformed_f)
        prior = metrics_store.get((stem, param_set))
        reg_time_s = prior.reg_time_s if prior else float("nan")
        total_time_s = prior.total_time_s if prior else float("nan")
    else:
        result = run_registration()
        conformed_f = result.conformed_f
        conformed_brain_f = result.conformed_brain_f
        reg_time_s = result.reg_time_s
        total_time_s = result.total_time_s

    row = _benchmark_row_from_result(
        stem=stem,
        method=method,
        param_set=param_set,
        conformed_f=conformed_f,
        conformed_brain_f=conformed_brain_f,
        preprocess=preprocess,
        qc_path=qc_path,
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
        work_dir=method_dir,
        modality=modality,
        resume=resume,
    )
    upsert_metrics_row(csv_path, metrics_store, row)
    if report_root is not None:
        refresh_combined_report(
            report_root,
            report_modalities,
            auto_refresh_sec=report_auto_refresh_sec,
            active_methods=active_methods,
        )
    logger.info(
        "%s: NMI=%.4f NCC=%.4f reg_time=%.2fs total_time=%.2fs",
        param_set,
        row.nmi,
        row.ncc,
        row.reg_time_s,
        row.total_time_s,
    )
    return row


def run_benchmark_for_image(
    imagef: Path,
    template_file: Path,
    output_dir: Path,
    csv_path: Path,
    metrics_store: dict[tuple[str, str], BenchmarkRow],
    stem: str,
    modality: str = "anat",
    resume: bool = True,
    methods: list[str] | None = None,
    report_root: Path | None = None,
    report_modalities: tuple[str, ...] = ("anat", "func", "t2w"),
    report_auto_refresh_sec: int = 0,
) -> list[BenchmarkRow]:
    if methods is None:
        methods = ["flirt", "simpleitk", "antsai"]
    methods_set = set(methods)
    shared_dir = output_dir / stem / "shared"
    flirt_dir = output_dir / "flirt" / stem
    qc_dir = output_dir / "qc"

    logger.info("=== Image: %s (fixed: %s) ===", imagef.name, template_file.name)
    if modality == "t2w":
        preprocess = t2w_preprocess(imagef, template_file)
    elif resume and (cached := _try_load_preprocess_cache(shared_dir, imagef.resolve())):
        logger.info("Preprocess: skip (cached) %s", shared_dir)
        preprocess = cached
    else:
        preprocess = shared_preprocess(
            imagef, template_file, shared_dir, modality=modality
        )

    rows: list[BenchmarkRow] = []
    variant_kw = dict(
        stem=stem,
        preprocess=preprocess,
        csv_path=csv_path,
        metrics_store=metrics_store,
        modality=modality,
        resume=resume,
        report_root=report_root,
        report_modalities=report_modalities,
        report_auto_refresh_sec=report_auto_refresh_sec,
        active_methods=methods,
    )

    if "flirt" in methods_set:
        try:
            row = _run_and_record_variant(
                method="flirt",
                param_set="flirt_baseline",
                method_label="baseline",
                conformed_f=flirt_dir / "conformed_flirt.nii.gz",
                qc_path=qc_dir / f"qc_flirt_baseline_{stem}.png",
                method_dir=flirt_dir,
                run_registration=lambda: run_flirt(
                    preprocess, flirt_dir, modality=modality
                ),
                **variant_kw,
            )
            rows.append(row)
        except Exception:
            logger.exception("FLIRT failed on %s", stem)

    if "simpleitk" in methods_set:
        for param_cfg in sitk_param_grid_for_modality(modality):
            label = param_cfg["label"]
            param_dir = output_dir / "sitk" / stem / label
            try:
                row = _run_and_record_variant(
                    method="sitk",
                    param_set=label,
                    method_label=label,
                    conformed_f=param_dir / "conformed_sitk.nii.gz",
                    qc_path=qc_dir / f"qc_{label}_{stem}.png",
                    method_dir=param_dir,
                    run_registration=lambda cfg=param_cfg, d=param_dir: run_sitk(
                        preprocess, d, sitk_config=cfg, modality=modality
                    ),
                    **variant_kw,
                )
                rows.append(row)
            except Exception:
                logger.exception("SimpleITK failed for %s on %s", label, stem)

    if "antsai" in methods_set:
        for param_cfg in ANTS_AI_PARAM_GRID:
            label = param_cfg["label"]
            param_dir = output_dir / "antsai" / stem / label
            try:
                row = _run_and_record_variant(
                    method="antsai",
                    param_set=label,
                    method_label=label,
                    conformed_f=param_dir / "conformed_antsai.nii.gz",
                    qc_path=qc_dir / f"qc_{label}_{stem}.png",
                    method_dir=param_dir,
                    run_registration=lambda cfg=param_cfg, d=param_dir: run_antsai(
                        preprocess, d, antsai_config=cfg
                    ),
                    **variant_kw,
                )
                rows.append(row)
            except Exception:
                logger.exception("antsAI failed for %s on %s", label, stem)

    return rows


def run_modality_benchmark(
    modality: str,
    input_dir: Path,
    output_dir: Path,
    template: Path | None,
    resume: bool,
    methods: list[str],
    report_root: Path,
    report_modalities: tuple[str, ...] = ("anat", "func", "t2w"),
    report_auto_refresh_sec: int = 0,
) -> None:
    """Run benchmark for one modality; refresh combined report at report_root."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    default_fixed = template if template is not None else input_dir / "fixed.nii.gz"
    pairs = discover_moving_fixed_pairs(input_dir, default_fixed)
    if not pairs:
        raise FileNotFoundError(f"No moving_*.nii.gz files found in {input_dir}")

    needs_fallback = any(
        _find_matched_fixed(input_dir, p.stem) is None for p in pairs
    )
    if needs_fallback and not default_fixed.is_file():
        raise FileNotFoundError(
            f"Fallback fixed image required but not found: {default_fixed}"
        )

    logger.info(
        "=== Modality %s: %d pair(s) in %s ===", modality, len(pairs), input_dir
    )
    logger.info("Output: %s", output_dir)
    logger.info("Fallback fixed: %s", default_fixed)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "metrics.csv"
    metrics_store: dict[tuple[str, str], BenchmarkRow] = (
        load_metrics_store(csv_path) if resume else {}
    )
    if metrics_store:
        logger.info("Loaded %d existing row(s) from %s", len(metrics_store), csv_path)

    for pair in pairs:
        try:
            run_benchmark_for_image(
                pair.moving,
                pair.fixed,
                output_dir,
                csv_path=csv_path,
                metrics_store=metrics_store,
                stem=pair.stem,
                modality=modality,
                resume=resume,
                methods=methods,
                report_root=report_root,
                report_modalities=report_modalities,
                report_auto_refresh_sec=report_auto_refresh_sec,
            )
        except Exception:
            logger.exception(
                "Failed on %s image %s", modality, pair.moving.name
            )

    if not metrics_store:
        raise RuntimeError(f"No successful benchmark runs for modality {modality}.")


# %%  --- PARAMS (edit here) ---

OUTPUT_DIR = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/results_params_v4"
)
INPUT_DIRS = {
    "anat": Path(
        "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_T1w"
    ),
    "func": Path(
        "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_func"
    ),
    "t2w": Path(
        "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/input_T2w"
    ),
}
MODALITIES = ("anat", "func", "t2w")
TEMPLATE = None  # Path(...) to override per-image fixed; None = auto from input dir
RESUME = True  # skip steps whose outputs already exist
VERBOSE = False
# Browser auto-reload interval for report.html (0 = manual refresh only)
REPORT_AUTO_REFRESH_SEC = 15

# Subset of backends to run — remove entries to skip them
METHODS = ["flirt", "simpleitk"]

# Func inputs should be 3D (e.g. tmean); 4D volumes may fail skullstripping.
_VALID_METHODS = frozenset({"flirt", "simpleitk", "antsai"})


# %%
if __name__ == "__main__":
    setup_logging(verbose=VERBOSE)

    unknown_methods = set(METHODS) - _VALID_METHODS
    if unknown_methods:
        raise ValueError(
            f"Unknown METHODS entries: {sorted(unknown_methods)}; "
            f"valid: {sorted(_VALID_METHODS)}"
        )
    if not METHODS:
        raise ValueError("METHODS must contain at least one backend")

    for modality in MODALITIES:
        if modality not in INPUT_DIRS:
            raise ValueError(f"Missing INPUT_DIRS entry for modality: {modality}")

    logger.info("Modalities: %s", ", ".join(MODALITIES))
    logger.info("Report root: %s", OUTPUT_DIR)
    logger.info("Methods: %s", ", ".join(METHODS))
    if "simpleitk" in METHODS:
        logger.info(
            "SimpleITK grid: %d sets (anat/t2w, %s, fine_step %s), %d sets "
            "(func, %s, bins %s, lr %s)",
            len(_SITK_PARAM_GRIDS["default"]),
            _SITK_PROFILE_DEFAULT.metric,
            _SITK_PROFILE_DEFAULT.fine_step_deg_options,
            len(_SITK_PARAM_GRIDS["func"]),
            _SITK_PROFILE_FUNC.metric,
            _SITK_PROFILE_FUNC.histogram_bins,
            _SITK_PROFILE_FUNC.learning_rates,
        )
    if "antsai" in METHODS:
        logger.info("antsAI grid: %d parameter sets", len(ANTS_AI_PARAM_GRID))
    if RESUME:
        logger.info("Resume enabled: skipping existing preprocess/registration outputs")
    else:
        logger.info("Resume disabled: re-running all steps")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = refresh_combined_report(
        OUTPUT_DIR,
        MODALITIES,
        auto_refresh_sec=REPORT_AUTO_REFRESH_SEC,
        active_methods=METHODS,
    )
    logger.info("Live report: %s", report_path)

    for modality in MODALITIES:
        run_modality_benchmark(
            modality=modality,
            input_dir=INPUT_DIRS[modality],
            output_dir=OUTPUT_DIR / modality,
            template=TEMPLATE,
            resume=RESUME,
            methods=METHODS,
            report_root=OUTPUT_DIR,
            report_modalities=MODALITIES,
            report_auto_refresh_sec=REPORT_AUTO_REFRESH_SEC,
        )

    all_rows = load_all_modality_rows(OUTPUT_DIR, MODALITIES)
    if not all_rows:
        raise RuntimeError("No successful benchmark runs.")

    report_path = refresh_combined_report(
        OUTPUT_DIR,
        MODALITIES,
        auto_refresh_sec=0,
        active_methods=METHODS,
    )
    print()
    print(f"\nHTML report: {report_path}")
