#!/usr/bin/env python3
"""
Benchmark FLIRT vs SimpleITK for anatomical conformation (rigid alignment).

Runs identical preprocessing (skullstrip, template pad/downsample, template resample),
then compares registration backends in order: FLIRT baseline, SimpleITK parameter
grid (FLIRT-faithful search + schedule + param grid), with QC snapshots and an
HTML report that links to those images.
"""

from __future__ import annotations

import csv
import html
import logging
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, Literal

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from sklearn.metrics import normalized_mutual_info_score

# Add src/ to path for nhp_mri_prep imports (scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from sitk_flirt_search import (
    SITK_PIPELINE_REV,
    _sitk_fixed_geometric_center,
    sitk_flirt_register,
)

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

_METHOD_ORDER = {"flirt": 0, "sitk": 1}


# %% SimpleITK: modality profiles + parameter grid
@dataclass(frozen=True)
class SitkModalityProfile:
    """FLIRT-like search + schedule knobs and optional grid sweeps."""

    pyramid_target_mm: tuple[float, ...]
    metric: str
    search_metric: str = "Correlation"
    schedule_metric: str | None = None
    histogram_bins: tuple[int, ...] = ()
    learning_rates: tuple[float, ...] = (1.0,)
    coarse_step_deg_options: tuple[int, ...] = (40,)
    fine_step_deg_options: tuple[int, ...] = (15,)
    cost_thresh_fraction_options: tuple[float, ...] = (0.2,)
    search_tx_iters_options: tuple[int, ...] = (50,)
    schedule_iters_options: tuple[int, ...] = (40,)
    search_sampling_pct: float = 0.2
    coarse_tx_iters: int | None = None
    # "CorrelationRatio" selects the FLIRT-faithful corratio + Powell + find_cost_minima
    # search/refine path (anat); None keeps the correlation/MattesMI gradient-descent path.
    search_rank_metric: str | None = None


_SITK_SEARCH_RANGE_DEG = (-180.0, 180.0)
_SITK_FINE_STEP_DEG_DEFAULT = 15

_SITK_PROFILE_DEFAULT = SitkModalityProfile(
    pyramid_target_mm=(8.0, 4.0, 2.0),
    metric="Correlation",
    search_metric="Correlation",
    search_rank_metric="CorrelationRatio",
    histogram_bins=(32,),
    coarse_step_deg_options=(40,),
    fine_step_deg_options=(15,),
    cost_thresh_fraction_options=(0.1,),
    search_tx_iters_options=(30,),
    schedule_iters_options=(50,),
)
_SITK_PROFILE_FUNC = SitkModalityProfile(
    pyramid_target_mm=(8.0, 4.0, 2.0),
    metric="MattesMI",
    search_metric="MattesMI",
    schedule_metric="MattesMI",
    histogram_bins=(32,),
    learning_rates=(1.0,),
    coarse_step_deg_options=(30,),
    fine_step_deg_options=(10,),
    cost_thresh_fraction_options=(0.1,),
    search_tx_iters_options=(30,),
    schedule_iters_options=(50,),
)


def sitk_profile_for_modality(modality: str) -> SitkModalityProfile:
    """Return SimpleITK grid profile; func uses FLIRT func conform search steps."""
    return _SITK_PROFILE_FUNC if modality == "func" else _SITK_PROFILE_DEFAULT


def _sitk_lr_tag(learning_rate: float) -> str:
    return f"lr{learning_rate:.1f}".replace(".", "p")


def _sitk_cost_thresh_tag(fraction: float) -> str:
    return f"ct{int(round(fraction * 100))}"


def _sitk_param_label(
    *,
    coarse_step_deg: int,
    fine_step_deg: int,
    cost_thresh_fraction: float,
    search_tx_iters: int,
    schedule_iters: int,
    histogram_bins: int | None = None,
    learning_rate: float = 1.0,
    include_coarse: bool = False,
    include_bins: bool = False,
    include_learning_rate: bool = False,
) -> str:
    coarse_part = f"cs{coarse_step_deg:02d}_" if include_coarse else ""
    bins_part = f"_b{histogram_bins}" if include_bins and histogram_bins is not None else ""
    lr_part = f"_{_sitk_lr_tag(learning_rate)}" if include_learning_rate else ""
    ct = _sitk_cost_thresh_tag(cost_thresh_fraction)
    return (
        f"sitk_flirt_{coarse_part}fs{fine_step_deg:02d}_{ct}_ti{search_tx_iters}_si{schedule_iters}"
        f"{bins_part}{lr_part}"
    )


def _build_sitk_param_grid(profile: SitkModalityProfile) -> list[dict[str, Any]]:
    """FLIRT-faithful search + schedule; sweep coarse/fine step, threshold, tx/schedule iters."""
    include_lr = len(profile.learning_rates) > 1
    include_bins = profile.metric == "MattesMI" and len(profile.histogram_bins) > 0
    include_coarse = len(profile.coarse_step_deg_options) > 1
    grid: list[dict[str, Any]] = []
    bin_values: tuple[int | None, ...] = (
        profile.histogram_bins if include_bins else (None,)
    )
    lr_values = profile.learning_rates if include_lr else (1.0,)
    for histogram_bin in bin_values:
        for learning_rate in lr_values:
            for coarse_step_deg in profile.coarse_step_deg_options:
                for fine_step_deg in profile.fine_step_deg_options:
                    for cost_thresh in profile.cost_thresh_fraction_options:
                        for search_tx_iters in profile.search_tx_iters_options:
                            for schedule_iters in profile.schedule_iters_options:
                                label = _sitk_param_label(
                                    coarse_step_deg=coarse_step_deg,
                                    fine_step_deg=fine_step_deg,
                                    cost_thresh_fraction=cost_thresh,
                                    search_tx_iters=search_tx_iters,
                                    schedule_iters=schedule_iters,
                                    histogram_bins=histogram_bin,
                                    learning_rate=learning_rate,
                                    include_coarse=include_coarse,
                                    include_bins=include_bins,
                                    include_learning_rate=include_lr,
                                )
                                schedule_metric = (
                                    profile.schedule_metric
                                    if profile.schedule_metric is not None
                                    else profile.metric
                                )
                                entry: dict[str, Any] = {
                                    "metric": profile.metric,
                                    "search_metric": profile.search_metric,
                                    "schedule_metric": schedule_metric,
                                    "search_range_deg": _SITK_SEARCH_RANGE_DEG,
                                    "coarse_step_deg": coarse_step_deg,
                                    "fine_step_deg": fine_step_deg,
                                    "cost_thresh_fraction": cost_thresh,
                                    "search_tx_iters": search_tx_iters,
                                    "schedule_iters": schedule_iters,
                                    "search_sampling_pct": profile.search_sampling_pct,
                                    "learning_rate": learning_rate,
                                    "label": label,
                                }
                                if histogram_bin is not None:
                                    entry["number_of_histogram_bins"] = histogram_bin
                                if profile.coarse_tx_iters is not None:
                                    entry["coarse_tx_iters"] = profile.coarse_tx_iters
                                if profile.search_rank_metric is not None:
                                    entry["search_rank_metric"] = profile.search_rank_metric
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


def _is_valid_nifti(path: Path) -> bool:
    """Non-empty file that nibabel can open with a 3-D (or 4-D) volume shape."""
    if not _is_valid_output(path):
        return False
    try:
        img = nib.load(str(path), mmap=True)
        shape = img.shape
        return len(shape) >= 3 and all(int(s) > 0 for s in shape[:3])
    except Exception:
        return False


def _variant_transform_paths(
    method: str, work_dir: Path, param_set: str
) -> tuple[Path, ...]:
    """Registration transform artifact(s) required before apply-only resume."""
    if method == "flirt":
        return (work_dir / "conform_scanner2native.mat",)
    if method == "sitk":
        return (work_dir / f"conform_scanner2native_sitk_{param_set}.mat",)
    raise ValueError(f"Unknown method for transform paths: {method}")


def _transform_artifacts_valid(
    method: str, work_dir: Path, param_set: str
) -> bool:
    return all(_is_valid_output(p) for p in _variant_transform_paths(method, work_dir, param_set))


def _sitk_pipeline_rev_path(variant_dir: Path) -> Path:
    return variant_dir / ".sitk_pipeline_rev"


def _sitk_pipeline_rev_ok(variant_dir: Path) -> bool:
    rev_path = _sitk_pipeline_rev_path(variant_dir)
    return rev_path.is_file() and rev_path.read_text().strip() == SITK_PIPELINE_REV


def _variant_completion_state(
    method: str,
    work_dir: Path,
    param_set: str,
    conformed_f: Path,
) -> Literal["done", "apply_only", "run"]:
    """Whether a benchmark variant can be skipped, apply-only resumed, or must re-register."""
    brain_f = conformed_brain_path(conformed_f)
    has_xfm = _transform_artifacts_valid(method, work_dir, param_set)
    has_conformed = _is_valid_nifti(conformed_f)
    has_brain = _is_valid_nifti(brain_f)
    if has_xfm and has_conformed and has_brain:
        if method == "sitk" and not _sitk_pipeline_rev_ok(work_dir / param_set):
            return "run"
        return "done"
    if has_xfm and (not has_conformed or not has_brain):
        return "apply_only"
    return "run"


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
        format="%(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%H:%M:%S",
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

    # The skullstrip NN expects a 3D volume; collapse any 4D input to its temporal
    # mean (tmean) first, mirroring the 4D-template handling below. Fixes 4D
    # mp2rage inputs (e.g. 032188) that otherwise crash skullstripping → no output.
    image_for_strip = image_path
    input_img = nib.load(image_path)
    if input_img.ndim == 4:
        logger.warning("4D input image detected; averaging time dimension (tmean) before skullstrip.")
        mean_input = np.mean(input_img.get_fdata(), axis=-1)
        image_for_strip = work_dir / "_input_3d.nii.gz"
        nib.save(
            nib.Nifti1Image(
                mean_input.astype(input_img.get_data_dtype()),
                input_img.affine,
                input_img.header,
            ),
            str(image_for_strip),
        )

    logger.info("Preprocess: skullstripping %s", Path(image_for_strip).name)
    brain_f = work_dir / "brain_for_conform.nii.gz"
    skull_result = apply_skullstripping(
        imagef=str(image_for_strip),
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
    *,
    skip_registration: bool = False,
) -> MethodResult:
    """FLIRT rigid registration + apply (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)

    t_total_start = time.perf_counter()
    xfm_forward_f = work_dir / "conform_scanner2native.mat"
    if skip_registration:
        if not _is_valid_output(xfm_forward_f):
            raise FileNotFoundError(
                f"FLIRT apply-only resume: transform missing {xfm_forward_f}"
            )
        logger.info("FLIRT: apply-only resume (skip registration)")
        reg_time_s = 0.0
    else:
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


def _sitk_tx_to_matrix(tx: sitk.Euler3DTransform) -> np.ndarray:
    """Convert centered Euler3DTransform to 4x4 affine (world-space, SimpleITK LPS)."""
    matrix = np.eye(4, dtype=np.float64)
    rotation = np.array(tx.GetMatrix(), dtype=np.float64).reshape(3, 3)
    center = np.array(tx.GetCenter(), dtype=np.float64)
    translation = np.array(tx.GetTranslation(), dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation + center - rotation @ center
    return matrix


def _sitk_affine_lps(img: sitk.Image) -> np.ndarray:
    """Voxel-index -> physical (SimpleITK LPS world) 4x4 affine for an image."""
    direction = np.array(img.GetDirection(), dtype=np.float64).reshape(3, 3)
    spacing = np.array(img.GetSpacing(), dtype=np.float64)
    origin = np.array(img.GetOrigin(), dtype=np.float64)
    affine = np.eye(4, dtype=np.float64)
    affine[:3, :3] = direction @ np.diag(spacing)
    affine[:3, 3] = origin
    return affine


def _sitk_fsl_scale(img: sitk.Image) -> np.ndarray:
    """Voxel-index -> FSL-mm scaling for an image (diag(pixdim), x-flipped if the
    stored orientation is radiological, i.e. positive affine determinant — matching how
    FSL/FLIRT build their internal mm coordinates)."""
    spacing = np.array(img.GetSpacing(), dtype=np.float64)
    size = img.GetSize()
    scale = np.diag([spacing[0], spacing[1], spacing[2], 1.0])
    if np.linalg.det(_sitk_affine_lps(img)[:3, :3]) > 0:
        scale[0, 0] = -spacing[0]
        scale[0, 3] = (size[0] - 1) * spacing[0]
    return scale


def _sitk_tx_to_fsl_matrix(
    tx: sitk.Euler3DTransform, fixed: sitk.Image, moving: sitk.Image
) -> np.ndarray:
    """Convert the sitk world transform to an FSL FLIRT matrix.

    Produces a drop-in for FLIRT's ``conform_scanner2native.mat`` — usable with
    ``flirt -in <brain> -ref <template> -applyxfm -init``. The sitk transform maps
    fixed(template)->moving(brain) in LPS world; FLIRT's matrix maps in->ref in FSL-mm,
    so we go world -> voxel-to-voxel -> FSL-mm and invert the direction. Verified by
    applying via FSL applyxfm: reproduces the registration (NCC matches FLIRT).
    """
    world = _sitk_tx_to_matrix(tx)  # template-world -> brain-world (LPS)
    a_fixed = _sitk_affine_lps(fixed)
    a_moving = _sitk_affine_lps(moving)
    vox2vox = np.linalg.inv(a_moving) @ world @ a_fixed  # template-vox -> brain-vox
    s_fixed = _sitk_fsl_scale(fixed)
    s_moving = _sitk_fsl_scale(moving)
    return np.linalg.inv(s_moving @ vox2vox @ np.linalg.inv(s_fixed))


def _sitk_world_mat_path(mat_path: Path) -> Path:
    """Sidecar path holding the world-space affine (for sitk resume reconstruction)."""
    return mat_path.with_suffix(".world.mat")


def _sitk_load_world_for_resume(mat_path: Path) -> np.ndarray:
    """Load the world-space affine for resume: the `.world.mat` sidecar (new FSL-primary
    layout) if present, else the primary `.mat` (legacy runs that stored world there)."""
    world = _sitk_world_mat_path(mat_path)
    return np.loadtxt(world if world.is_file() else mat_path)


def _sitk_save_transform_artifacts(
    tx: sitk.Euler3DTransform,
    mat_path: Path,
    fixed: sitk.Image,
    moving: sitk.Image,
    *,
    param_set: str | None = None,
) -> None:
    """Save the transform as a FLIRT-compatible FSL matrix (primary .mat) plus its inverse
    (`_inverse.mat`), mirroring FLIRT's conform_scanner2native[/_inverse].mat outputs, and
    the world-space affine as a `.world.mat` sidecar used to rebuild the tx on resume.
    """
    forward_fsl = _sitk_tx_to_fsl_matrix(tx, fixed, moving)
    np.savetxt(mat_path, forward_fsl)
    inverse_path = mat_path.with_name(f"{mat_path.stem}_inverse{mat_path.suffix}")
    np.savetxt(inverse_path, np.linalg.inv(forward_fsl))
    np.savetxt(_sitk_world_mat_path(mat_path), _sitk_tx_to_matrix(tx))
    if param_set is not None:
        _sitk_pipeline_rev_path(mat_path.parent).write_text(
            SITK_PIPELINE_REV + "\n", encoding="utf-8"
        )


def _sitk_copy_euler(tx: sitk.Euler3DTransform) -> sitk.Euler3DTransform:
    """Deep-copy a centered Euler3DTransform."""
    out = sitk.Euler3DTransform()
    out.SetFixedParameters(tx.GetFixedParameters())
    out.SetParameters(tx.GetParameters())
    return out



def _sitk_transform_from_mat(
    mat: np.ndarray, registration_fixedf: Path
) -> sitk.Euler3DTransform:
    """Rebuild centered Euler3DTransform from saved 4x4 affine + registration fixed image."""
    fixed = _sitk_ensure_3d(
        sitk.ReadImage(str(validate_input_file(registration_fixedf, logger)), sitk.sitkFloat32)
    )
    center = _sitk_fixed_geometric_center(fixed)
    rotation = mat[:3, :3].astype(np.float64)
    t_full = mat[:3, 3].astype(np.float64)
    c = np.array(center, dtype=np.float64)
    t_param = t_full - c + rotation @ c
    tx = sitk.Euler3DTransform()
    tx.SetCenter(center)
    tx.SetMatrix(rotation.reshape(-1).tolist())
    tx.SetTranslation(t_param.tolist())
    return tx


def _sitk_register(
    fixedf: Path,
    movingf: Path,
    work_dir: Path,
    output_prefix: str,
    sitk_config: dict[str, Any],
    modality: str = "anat",
) -> dict[str, Any]:
    """Rigid registration: FLIRT search_cost + defaultschedule (sitk_flirt_search)."""
    fixed_path = validate_input_file(fixedf, logger)
    moving_path = validate_input_file(movingf, logger)
    work_dir = ensure_working_directory(work_dir, logger)

    fixed = _sitk_ensure_3d(sitk.ReadImage(str(fixed_path), sitk.sitkFloat32))
    moving = _sitk_ensure_3d(sitk.ReadImage(str(moving_path), sitk.sitkFloat32))

    label = sitk_config.get("label", "default")
    prof = sitk_profile_for_modality(modality)
    logger.info(
        "SimpleITK FLIRT register (%s): coarse=%s° fine=%s° ct=%.2f "
        "ti=%s si=%s search=%s schedule=%s (rev=%s)",
        label,
        sitk_config.get("coarse_step_deg", prof.coarse_step_deg_options[0]),
        sitk_config.get("fine_step_deg", _SITK_FINE_STEP_DEG_DEFAULT),
        sitk_config.get("cost_thresh_fraction", 0.2),
        sitk_config.get("search_tx_iters", 50),
        sitk_config.get("schedule_iters", 40),
        sitk_config.get("search_metric", prof.search_metric),
        sitk_config.get(
            "schedule_metric",
            prof.schedule_metric if prof.schedule_metric else prof.metric,
        ),
        SITK_PIPELINE_REV,
    )
    t0 = time.perf_counter()
    final_tx = sitk_flirt_register(fixed, moving, sitk_config, modality)
    logger.info(
        "SimpleITK FLIRT pipeline finished in %.1f s (label=%s)",
        time.perf_counter() - t0,
        label,
    )

    forward_transform = work_dir / f"{output_prefix}.mat"
    _sitk_save_transform_artifacts(
        final_tx, forward_transform, fixed, moving, param_set=label
    )
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
    *,
    skip_registration: bool = False,
) -> MethodResult:
    """SimpleITK rigid registration + apply (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)
    label = sitk_config["label"]

    t_total_start = time.perf_counter()
    mat_path = work_dir / f"conform_scanner2native_sitk_{label}.mat"
    if skip_registration:
        if not _transform_artifacts_valid("sitk", work_dir, label):
            raise FileNotFoundError(
                f"SimpleITK apply-only resume: transform missing under {work_dir}"
            )
        logger.info("SimpleITK (%s): apply-only resume (skip registration)", label)
        transform_obj = _sitk_transform_from_mat(
            _sitk_load_world_for_resume(mat_path), preprocess.template_for_reg
        )
        reg_time_s = 0.0
    else:
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
        transform_obj = _sitk_transform_from_mat(
            _sitk_load_world_for_resume(xfm), preprocess.template_for_reg
        )
        _sitk_apply_transforms(
            movingf=preprocess.brain_f,
            outputf_name=brain_out.name,
            reff=preprocess.template_for_xfm,
            work_dir=work_dir,
            transform_obj=transform_obj,
        )
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


def _fmt_float(val: float, decimals: int = 4) -> str:
    if val != val:
        return "—"
    return f"{val:.{decimals}f}"


def _fmt_float_attr(val: float) -> str:
    """Numeric string for HTML data-* sort attributes (empty if NaN)."""
    if val != val:
        return ""
    return str(val)


def _report_image_src(image_path: str, report_path: Path) -> str:
    """Relative URL from report.html to a QC PNG on disk."""
    path = Path(image_path)
    if not path.is_file():
        return ""
    try:
        rel = path.resolve().relative_to(report_path.parent.resolve())
    except ValueError:
        return ""
    return html.escape(rel.as_posix())


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


def _html_param_naming_legend(modality: str) -> str:
    """Compact legend for param_set name tokens (e.g. sitk_flirt_fs15_ct15_ti30_si50)."""
    profile = sitk_profile_for_modality(modality)
    common = (
        "<dt><code>flirt_baseline</code></dt>"
        "<dd>FSL FLIRT baseline (single run per image).</dd>"
        "<dt><code>sitk_flirt</code></dt>"
        "<dd>SimpleITK FLIRT-style coarse rotation search + fine schedule.</dd>"
        f"<dt><code>cs##</code></dt>"
        "<dd>Coarse rotation search step (degrees); e.g. <code>cs40</code> = 40° "
        "(omitted when only one coarse step is used).</dd>"
        f"<dt><code>fs##</code></dt>"
        "<dd>Fine rotation search step (degrees); e.g. <code>fs15</code> = 15°.</dd>"
        "<dt><code>ct##</code></dt>"
        "<dd>Cost threshold (% of best coarse cost, ×0.01); e.g. <code>ct15</code> = 0.15.</dd>"
        "<dt><code>ti##</code></dt>"
        "<dd>Fine-survivor translation-refinement iterations (coarse uses 20 iters by default).</dd>"
        "<dt><code>si##</code></dt>"
        "<dd>Gradient-descent schedule iterations at fine pyramid levels.</dd>"
    )
    func_extra = (
        "<dt><code>b##</code></dt>"
        "<dd>Mattes MI histogram bins (func grid only).</dd>"
        "<dt><code>lr#p#</code></dt>"
        "<dd>Optimizer learning-rate scale; e.g. <code>lr0p5</code> = 0.5×.</dd>"
    )
    coarse_vals = ", ".join(f"{d}°" for d in profile.coarse_step_deg_options)
    fine_vals = ", ".join(f"{d}°" for d in profile.fine_step_deg_options)
    sched_m = profile.schedule_metric or profile.metric
    metric_note = (
        f"Search metric: <strong>{html.escape(profile.search_metric)}</strong>; "
        f"schedule metric: <strong>{html.escape(sched_m)}</strong>; "
        f"coarse step(s) swept: <strong>{coarse_vals}</strong> "
        f"(FLIRT <code>coarsesearch</code>); "
        f"fine step(s) swept: <strong>{fine_vals}</strong>; "
        f"pipeline <strong>{html.escape(SITK_PIPELINE_REV)}</strong>."
    )
    extra = func_extra if modality == "func" else ""
    example = (
        "sitk_flirt_cs40_fs15_ct10_ti30_si50"
        if modality != "func"
        else "sitk_flirt_fs15_ct15_ti30_si30_b32"
    )
    return (
        '<div class="param-naming-legend">'
        '<p class="param-naming-example">'
        f"Example: <code>{html.escape(example)}</code></p>"
        f'<dl class="param-naming-dl">{common}{extra}</dl>'
        f'<p class="param-naming-metric">{metric_note}</p>'
        "</div>"
    )


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
    """Write HTML report with metrics table and linked QC images."""
    report_path = output_dir / "report.html"
    param_summaries = _summarize_by_param(rows)
    best_summary_idxs = _best_summary_indices(param_summaries)

    # Group summaries by modality preserving sorted order
    mod_to_summaries: dict[str, list[tuple[int, ParamSummary]]] = {}
    for idx, summary in enumerate(param_summaries):
        mod_to_summaries.setdefault(summary.modality, []).append((idx, summary))

    modalities = sorted({r.modality for r in rows})
    display_modalities = modalities if modalities else list(all_modalities)
    refresh_meta = (
        f'<meta http-equiv="refresh" content="{auto_refresh_sec}"/>'
        if auto_refresh_sec > 0
        else ""
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
            f"{_html_param_naming_legend(mod)}\n"
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
            ordered = flirt_rows + sitk_rows
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
                    src = _report_image_src(row.qc_snapshot_path, report_path)
                    if src:
                        img_html = (
                            f'<img src="{src}" alt="{html.escape(row.param_set)}" '
                            f'loading="lazy"/>'
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
            f"<h2>{html.escape(modality.upper())}</h2>"
            f"{_html_param_naming_legend(modality)}"
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
  .param-naming-legend {{ font-size: 0.82rem; color: #aaa; margin: 0 0 1.25rem; max-width: 52rem; }}
  .param-naming-example {{ margin: 0 0 0.5rem; color: #bbb; }}
  .param-naming-dl {{ margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 0.15rem 0.75rem; }}
  .param-naming-dl dt {{ color: #ccc; margin: 0; }}
  .param-naming-dl dd {{ margin: 0; color: #999; }}
  .param-naming-metric {{ margin: 0.5rem 0 0; color: #888; font-size: 0.8rem; }}
  a {{ color: #6eb5ff; }}
  caption {{ caption-side: bottom; font-size: 0.8rem; color: #888; padding-top: 0.5rem; text-align: left; }}
  td.pending {{ color: #888; font-style: italic; text-align: center; }}
</style>
</head>
<body data-report-id="{html.escape(str(output_dir))}">
<h1>Anatomical conformation benchmark</h1>

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
    run_registration: Callable[..., MethodResult],
    report_root: Path | None,
    report_modalities: tuple[str, ...],
    report_auto_refresh_sec: int,
    active_methods: list[str] | None = None,
) -> BenchmarkRow:
    """Run or resume one registration variant, record metrics, refresh report."""
    logger.info("--- Method: %s (%s) ---", method, method_label)
    conformed_brain_f: Path | None = None
    prior = metrics_store.get((stem, param_set))
    completion = (
        _variant_completion_state(method, method_dir, param_set, conformed_f)
        if resume
        else "run"
    )
    if completion == "done":
        logger.info(
            "%s: skip (complete) %s",
            method,
            conformed_f.parent.name,
        )
        reg_time_s = prior.reg_time_s if prior else float("nan")
        total_time_s = prior.total_time_s if prior else float("nan")
    elif completion == "apply_only":
        logger.info(
            "%s: apply-only resume (transform cached, outputs incomplete)",
            method,
        )
        result = run_registration(skip_registration=True)
        conformed_f = result.conformed_f
        conformed_brain_f = result.conformed_brain_f
        reg_time_s = (
            prior.reg_time_s
            if prior is not None and prior.reg_time_s == prior.reg_time_s
            else result.reg_time_s
        )
        total_time_s = result.total_time_s
    else:
        if (
            resume
            and method == "sitk"
            and _transform_artifacts_valid(method, method_dir, param_set)
        ):
            logger.info(
                "%s: re-register (stale pipeline, need rev %s)",
                method,
                SITK_PIPELINE_REV,
            )
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
        methods = ["flirt", "simpleitk"]
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
                run_registration=lambda *, skip_registration=False: run_flirt(
                    preprocess,
                    flirt_dir,
                    modality=modality,
                    skip_registration=skip_registration,
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
                    run_registration=lambda cfg=param_cfg, d=param_dir, *, skip_registration=False: run_sitk(
                        preprocess,
                        d,
                        sitk_config=cfg,
                        modality=modality,
                        skip_registration=skip_registration,
                    ),
                    **variant_kw,
                )
                rows.append(row)
            except Exception:
                logger.exception("SimpleITK failed for %s on %s", label, stem)

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
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation/results_params_anat_v4"
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
MODALITIES = ("anat", "func")  # ("anat", "func", "t2w",)
TEMPLATE = None  # Path(...) to override per-image fixed; None = auto from input dir
RESUME = True  # skip complete variants; apply-only if transform exists without conformed outputs
VERBOSE = False
# Browser auto-reload interval for report.html (0 = manual refresh only)
REPORT_AUTO_REFRESH_SEC = 15

# Subset of backends to run — remove entries to skip them
METHODS = ["flirt", "simpleitk"]

# Func inputs should be 3D (e.g. tmean); 4D volumes may fail skullstripping.
_VALID_METHODS = frozenset({"flirt", "simpleitk"})


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
            "SimpleITK FLIRT grid: %d anat/t2w sets (cs %s°, fs %s, ct %s, ti %s, si %s), "
            "%d func sets (cs %s°, fs %s, bins %s, lr %s)",
            len(_SITK_PARAM_GRIDS["default"]),
            _SITK_PROFILE_DEFAULT.coarse_step_deg_options,
            _SITK_PROFILE_DEFAULT.fine_step_deg_options,
            _SITK_PROFILE_DEFAULT.cost_thresh_fraction_options,
            _SITK_PROFILE_DEFAULT.search_tx_iters_options,
            _SITK_PROFILE_DEFAULT.schedule_iters_options,
            len(_SITK_PARAM_GRIDS["func"]),
            _SITK_PROFILE_FUNC.coarse_step_deg_options,
            _SITK_PROFILE_FUNC.fine_step_deg_options,
            _SITK_PROFILE_FUNC.histogram_bins,
            _SITK_PROFILE_FUNC.learning_rates,
        )
        logger.info(
            "SimpleITK pipeline rev=%s (GitHub search/schedule baseline)",
            SITK_PIPELINE_REV,
        )
    if RESUME:
        logger.info(
            "Resume enabled: skip complete variants; apply-only when .mat exists "
            "without conformed outputs; set RESUME=False to force full rerun"
        )
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
