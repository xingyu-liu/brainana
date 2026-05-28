#!/usr/bin/env python3
"""
Benchmark FLIRT vs antsAI for anatomical conformation (rigid alignment to template).

Runs identical preprocessing (skullstrip, template pad/downsample, template resample),
then compares registration backends on quality metrics (NMI, NCC) and timing.
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from sklearn.metrics import normalized_mutual_info_score

# Add src/ to path for nhp_mri_prep imports (scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.operations.preprocessing import (  # noqa: E402
    DEFAULT_CONFORM_PADDING_PERCENTAGE,
    DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD,
    apply_skullstripping,
)
from nhp_mri_prep.operations.registration import (  # noqa: E402
    flirt_apply_transforms,
    flirt_register,
)
from nhp_mri_prep.operations.validation import (  # noqa: E402
    ensure_working_directory,
    validate_input_file,
    validate_output_file,
)
from nhp_mri_prep.utils import run_command  # noqa: E402
from nhp_mri_prep.utils.mri import pad_image  # noqa: E402

# %%
DEFAULT_TEST_DIR = Path(
    "/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/anat_conformation"
)
DEFAULT_INPUT_DIR = DEFAULT_TEST_DIR / "input"
DEFAULT_OUTPUT_DIR = DEFAULT_TEST_DIR / "results"
DEFAULT_TEMPLATE_F = DEFAULT_TEST_DIR / "tpl-NMT2Sym_res-05_T1w_brain.nii.gz"

# %%
FLIRT_CONFIG = {
    "registration": {
        "flirt": {
            "cost": "corratio",
            "searchcost": "corratio",
            "coarsesearch": 40,
            "finesearch": 15,
        }
    }
}

ANTS_AI_CONFIG = {
    "registration": {
        "antsai": {
            "metric": "Mattes",
            "number_of_bins": 32,
            "sampling_strategy": "Random",
            "sampling_percentage": 0.25,
            "transform": "Rigid",
            "gradient_step": 0.1,
            "align_principal_axes": 1,
            "search_factor": 20,
            "arc_fraction": 0.12,
            "convergence_iterations": 10,
            "dimensionality": 3,
            "verbose": 1,
            "random_seed": 42,
        }
    }
}

logger = logging.getLogger("test_anat_conformation")


def _antsai_options(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config if config is not None else ANTS_AI_CONFIG
    return cfg["registration"]["antsai"]


def _antsai_metric_string(fixed: str, moving: str, config: dict[str, Any] | None = None) -> str:
    ai = _antsai_options(config)
    return (
        f"{ai['metric']}[{fixed},{moving},{ai['number_of_bins']},"
        f"{ai['sampling_strategy']},{ai['sampling_percentage']}]"
    )


def _antsai_transform_string(config: dict[str, Any] | None = None) -> str:
    ai = _antsai_options(config)
    return f"{ai['transform']}[{ai['gradient_step']}]"


def _antsai_search_string(config: dict[str, Any] | None = None) -> str:
    ai = _antsai_options(config)
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
    reg_time_s: float
    total_time_s: float


@dataclass
class BenchmarkRow:
    image: str
    method: str
    nmi: float
    ncc: float
    reg_time_s: float
    total_time_s: float


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
) -> PreprocessResult:
    """Steps 1, 2, and 4 of conform_to_template (skullstrip + template prep)."""
    image_path = validate_input_file(imagef, logger)
    template_path = validate_input_file(template_file, logger)
    work_dir = ensure_working_directory(work_dir, logger)

    logger.info("Preprocess: skullstripping %s", image_path.name)
    brain_f = work_dir / "brain_for_conform.nii.gz"
    skull_result = apply_skullstripping(
        imagef=str(image_path),
        modal="anat",
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
    pad_image(str(source_for_padding), str(template_f_padded), pad_amounts, logger=logger)
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
            downsample_voxel_sizes = np.full((3,), DEFAULT_DOWNSAMPLE_VOXEL_SIZE_THRESHOLD)

    if should_downsample:
        template_f_downsampled = (
            Path(str(template_f_padded).split(".nii.gz")[0] + "_downsampled.nii.gz")
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


def run_flirt(
    preprocess: PreprocessResult,
    work_dir: Path,
    output_name: str = "conformed_flirt.nii.gz",
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
        config=FLIRT_CONFIG,
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
    total_time_s = time.perf_counter() - t_total_start
    conformed_f = Path(apply_result["imagef_registered"])

    return MethodResult(
        conformed_f=conformed_f,
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
    )


def run_antsai(
    preprocess: PreprocessResult,
    work_dir: Path,
    output_name: str = "conformed_antsai.nii.gz",
) -> MethodResult:
    """antsAI rigid registration + antsApplyTransforms (timed)."""
    work_dir = ensure_working_directory(work_dir, logger)
    xfm_path = work_dir / "antsAI_conform.mat"
    conformed_f = work_dir / output_name

    fixed = str(preprocess.template_for_reg)
    moving = str(preprocess.brain_f)
    ai = _antsai_options()

    cmd_reg = [
        "antsAI",
        "-d",
        str(ai["dimensionality"]),
        "-m",
        _antsai_metric_string(fixed, moving),
        "-t",
        _antsai_transform_string(),
        "-p",
        str(ai["align_principal_axes"]),
        "-s",
        _antsai_search_string(),
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

    cmd_apply = [
        "antsApplyTransforms",
        "-d",
        "3",
        "-i",
        str(preprocess.full_head),
        "-r",
        str(preprocess.template_for_xfm),
        "-o",
        str(conformed_f),
        "-t",
        str(xfm_path),
        "-n",
        "Linear",
    ]
    returncode, _, stderr = run_command(cmd_apply, step_logger=logger)
    if returncode != 0:
        raise RuntimeError(f"antsApplyTransforms failed (exit {returncode}): {stderr}")
    validate_output_file(conformed_f, logger)
    total_time_s = time.perf_counter() - t_total_start

    return MethodResult(
        conformed_f=conformed_f,
        reg_time_s=reg_time_s,
        total_time_s=total_time_s,
    )


def _brain_mask(fixed: np.ndarray, moving: np.ndarray, percentile: float = 10.0) -> np.ndarray:
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


def compute_metrics(conformed_f: Path, template_f: Path, n_bins: int = 64) -> dict[str, float]:
    """NMI and NCC between conformed image and template (same grid after apply)."""
    fixed_data = np.ascontiguousarray(nib.load(template_f).get_fdata(), dtype=np.float64)
    moving_data = np.ascontiguousarray(nib.load(conformed_f).get_fdata(), dtype=np.float64)
    if fixed_data.shape != moving_data.shape:
        raise ValueError(
            f"Shape mismatch for metrics: template {fixed_data.shape} vs conformed {moving_data.shape}"
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


def discover_input_images(input_dir: Path) -> list[Path]:
    patterns = ("*.nii.gz", "*.nii")
    images: list[Path] = []
    for pattern in patterns:
        images.extend(sorted(input_dir.glob(pattern)))
    # Drop sidecar-like names if any
    return [p for p in images if p.is_file()]


def _print_summary_table(rows: list[BenchmarkRow]) -> None:
    if not rows:
        print("No results.")
        return
    headers = ["image", "method", "nmi", "ncc", "reg_time_s", "total_time_s"]
    col_widths = [max(len(h), max(len(str(getattr(r, h))) for r in rows)) for h in headers]
    fmt = "  ".join(f"{{:{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("-" * (sum(col_widths) + 2 * (len(headers) - 1)))
    for row in rows:
        print(
            fmt.format(
                row.image,
                row.method,
                f"{row.nmi:.4f}",
                f"{row.ncc:.4f}",
                f"{row.reg_time_s:.2f}",
                f"{row.total_time_s:.2f}",
            )
        )


def save_metrics_csv(rows: list[BenchmarkRow], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["image", "method", "nmi", "ncc", "reg_time_s", "total_time_s"]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    logger.info("Wrote metrics to %s", csv_path)


def run_benchmark_for_image(
    imagef: Path,
    template_file: Path,
    output_dir: Path,
) -> list[BenchmarkRow]:
    stem = imagef.name.replace(".nii.gz", "").replace(".nii", "")
    shared_dir = output_dir / stem / "shared"
    flirt_dir = output_dir / "flirt" / stem
    antsai_dir = output_dir / "antsai" / stem

    logger.info("=== Image: %s ===", imagef.name)
    preprocess = shared_preprocess(imagef, template_file, shared_dir)

    rows: list[BenchmarkRow] = []
    for method_name, runner, method_dir in (
        ("flirt", run_flirt, flirt_dir),
        ("antsai", run_antsai, antsai_dir),
    ):
        logger.info("--- Method: %s ---", method_name)
        method_result = runner(preprocess, method_dir)
        metrics = compute_metrics(method_result.conformed_f, preprocess.template_for_xfm)
        rows.append(
            BenchmarkRow(
                image=stem,
                method=method_name,
                nmi=metrics["nmi"],
                ncc=metrics["ncc"],
                reg_time_s=method_result.reg_time_s,
                total_time_s=method_result.total_time_s,
            )
        )
        logger.info(
            "%s: NMI=%.4f NCC=%.4f reg_time=%.2fs total_time=%.2fs",
            method_name,
            metrics["nmi"],
            metrics["ncc"],
            method_result.reg_time_s,
            method_result.total_time_s,
        )
    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark FLIRT vs antsAI for anatomical conformation.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory with test anatomical NIfTI files (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for work dirs and metrics CSV (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE_F,
        help=f"Template NIfTI for conform (default: {DEFAULT_TEMPLATE_F})",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)

    input_dir = args.input_dir
    if not input_dir.is_dir():
        logger.error("Input directory not found: %s", input_dir)
        return 1

    template_path = args.template
    if not template_path.is_file():
        logger.error("Template file not found: %s", template_path)
        return 1
    logger.info("Template: %s", template_path)

    images = discover_input_images(input_dir)
    if not images:
        logger.error("No NIfTI images found in %s", input_dir)
        return 1

    logger.info("Found %d image(s) in %s", len(images), input_dir)
    all_rows: list[BenchmarkRow] = []
    for imagef in images:
        try:
            all_rows.extend(
                run_benchmark_for_image(imagef, template_path, args.output_dir)
            )
        except Exception:
            logger.exception("Failed on image %s", imagef.name)

    if not all_rows:
        logger.error("No successful benchmark runs.")
        return 1

    csv_path = args.output_dir / "metrics.csv"
    save_metrics_csv(all_rows, csv_path)
    print()
    _print_summary_table(all_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
