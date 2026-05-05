"""
Temporal SNR (tSNR) maps for functional QC: per-run volume, session average, optional surface projection.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import nibabel as nib
import numpy as np

from .types import StepOutput
from ..utils.nextflow import ensure_stderr_logging_if_unconfigured

# %%
logger = logging.getLogger(__name__)

_HEMI_MAP = {"L": "lh", "R": "rh"}
_STAT_SUFFIX = "_stat-tsnr_boldmap"

# %%
def compute_tsnr_run(
    bold_file: Union[str, Path],
    out_f: Union[str, Path],
    mask_file: Optional[Union[str, Path]] = None,
    min_n_tp: int = 10,
    *,
    bold_space: Optional[str] = None,
) -> StepOutput:
    """
    Compute per-run tSNR (|mean|/std over time) for a 4D BOLD NIfTI and save as 3D float32.

    Skips (no output file) when not 4D, too few timepoints, or on load errors.
    Optional mask: uses the single path provided by the workflow. Spatial layout
    must match the BOLD grid: ``mask.shape[:3] == bold.shape[:3]``; if the mask
    has a trailing dimension (e.g. 4D ``(..., 1)``), the first 3D slab is used.
    """
    ensure_stderr_logging_if_unconfigured()

    bold_path = Path(bold_file)
    out_path = Path(out_f)
    meta: Dict[str, Any] = {"step": "compute_tsnr_run", "bold_file": str(bold_path)}
    if bold_space is not None:
        meta["bold_space"] = bold_space

    # 1. Load 4D BOLD; bail out on I/O errors or unusable dimensionality / length.
    try:
        bold_img = nib.load(str(bold_path))
        bold_4d = bold_img.get_fdata()
    except Exception as exc:
        logger.warning(f"tSNR: failed to load BOLD {bold_path}: {exc}")
        meta["skipped"] = True
        meta["error"] = str(exc)
        return StepOutput(output_file=out_path, metadata=meta)

    if bold_4d.ndim != 4:
        logger.info(f"tSNR: skip {bold_path.name} — not 4D (ndim={bold_4d.ndim})")
        meta["skipped"] = True
        meta["reason"] = "not_4d"
        return StepOutput(output_file=out_path, metadata=meta)

    if bold_4d.shape[-1] < min_n_tp:
        logger.info(
            f"tSNR: skip {bold_path.name} — only {bold_4d.shape[-1]} timepoints (< {min_n_tp})",
        )
        meta["skipped"] = True
        meta["reason"] = "too_few_timepoints"
        return StepOutput(output_file=out_path, metadata=meta)

    bold_dim_3d = bold_4d.shape[:3]
    mask_name = Path(mask_file).name if mask_file else None
    logger.info(
        f"tSNR bold_space={bold_space} bold={bold_path.name} "
        f"bold_shape={bold_4d.shape} mask={mask_name}",
    )

    # 2. Optional brain mask: same path Nextflow staged; require I,J,K to match BOLD.
    mask: Optional[np.ndarray] = None
    mask_path = Path(mask_file) if mask_file is not None else None
    if (
        mask_path is not None
        and mask_path.exists()
        and ".dummy" not in str(mask_path).lower()
        and mask_path.stat().st_size > 0
    ):
        try:
            mask_nifti = nib.load(str(mask_path))
            mask_voxels = np.asarray(mask_nifti.get_fdata())
            mask_dim_3d = mask_voxels.shape[:3]
            # Compare spatial dims from nibabel (do not use ``utils.mri.get_image_shape``:
            # that shells out to AFNI ``3dinfo`` and is unnecessary here).
            if mask_dim_3d == bold_dim_3d:
                mask_3d = mask_voxels[..., 0] if mask_voxels.ndim > 3 else mask_voxels
                mask = mask_3d > 0
                meta["mask_file_used"] = str(mask_path)
            else:
                logger.warning(
                    f"tSNR: mask shape mismatch for {bold_path.name} "
                    f"(mask.shape[:3]={mask_dim_3d} vs BOLD.shape[:3]={bold_dim_3d}); ignoring mask",
                )
        except Exception as exc:
            logger.warning(f"tSNR: could not load mask {mask_path}: {exc}")

    # 3. Per-voxel tSNR = |mean| / std over time; zero outside mask when a valid mask is present.
    with np.errstate(divide="ignore", invalid="ignore"):
        tsnr = np.abs(np.nanmean(bold_4d, axis=-1) / np.nanstd(bold_4d, axis=-1))
    tsnr[~np.isfinite(tsnr)] = 0.0
    if mask is not None:
        tsnr[~mask] = 0.0

    # 4. Write 3D float map reusing BOLD affine/header grid.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_img = nib.Nifti1Image(tsnr.astype(np.float32), bold_img.affine, bold_img.header)
    nib.save(out_img, str(out_path))

    meta["output_file"] = str(out_path)
    return StepOutput(output_file=out_path, metadata=meta)


def compute_tsnr_session_avg(
    run_tsnr_paths_json: str,
    out_f: Union[str, Path],
) -> StepOutput:
    """
    Average multiple run-level tSNR volumes (nanmean along a new axis).

    ``run_tsnr_paths_json`` is a JSON list of string paths; non-existent paths are ignored.
    """
    out_path = Path(out_f)
    meta: Dict[str, Any] = {"step": "compute_tsnr_session_avg"}

    # 1. Decode JSON list of run-level tSNR paths (strings from Nextflow).
    try:
        paths_json_decoded = json.loads(run_tsnr_paths_json)
    except json.JSONDecodeError as exc:
        meta["error"] = f"invalid_json: {exc}"
        raise ValueError(f"Invalid JSON for run tSNR paths: {exc}") from exc

    if not isinstance(paths_json_decoded, list):
        paths_json_decoded = [paths_json_decoded]

    # 2. Resolve to existing files only (missing paths are skipped with a warning).
    run_tsnr_paths_existing: List[Path] = []
    for path_token in paths_json_decoded:
        if not path_token:
            continue
        resolved_run_path = Path(str(path_token).strip().strip('"').strip("'"))
        if resolved_run_path.exists():
            run_tsnr_paths_existing.append(resolved_run_path)
        else:
            logger.warning(f"tSNR session avg: missing file, skipping: {resolved_run_path}")

    if not run_tsnr_paths_existing:
        meta["error"] = "no_valid_run_tsnr_files"
        raise ValueError("No valid run-level tSNR NIfTI files for session average.")

    # 3. Nan-mean across runs; use first volume for affine/header reference.
    vol_stack = np.stack(
        [nib.load(str(run_path)).get_fdata() for run_path in run_tsnr_paths_existing],
        axis=-1,
    )
    session_tsnr = np.nanmean(vol_stack, axis=-1)
    reference_nifti = nib.load(str(run_tsnr_paths_existing[0]))

    # 4. Persist session-average map.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_img = nib.Nifti1Image(
        session_tsnr.astype(np.float32), reference_nifti.affine, reference_nifti.header
    )
    nib.save(out_img, str(out_path))

    meta["output_file"] = str(out_path)
    meta["n_runs_averaged"] = len(run_tsnr_paths_existing)
    return StepOutput(output_file=out_path, metadata=meta)


def project_tsnr_to_surface(
    tsnr_nifti_f: Union[str, Path],
    fs_subject_dir: Union[str, Path],
    out_dir: Union[str, Path],
) -> Dict[str, Any]:
    """
    Project a tSNR volume to left/right surface GII via ``mri_vol2surf``.

    ``fs_subject_dir`` is the FastSurfer subject folder (``SUBJECTS_DIR`` is its parent;
    FreeSurfer subject id is ``fs_subject_dir.name``).

    On missing tool, missing directory, or failure: returns dict with ``lh_gii``/``rh_gii``
    set to None and ``skipped`` True.
    """
    tsnr_volume_path = Path(tsnr_nifti_f)
    fs_subject_directory = Path(fs_subject_dir)
    surf_output_directory = Path(out_dir)
    surf_output_directory.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "lh_gii": None,
        "rh_gii": None,
        "skipped": False,
    }

    # 1. Require input volume and FastSurfer subject tree.
    if not tsnr_volume_path.exists():
        logger.warning(f"tSNR surf: volume missing: {tsnr_volume_path}")
        result["skipped"] = True
        result["reason"] = "missing_volume"
        return result

    if not fs_subject_directory.is_dir():
        logger.warning(f"tSNR surf: FastSurfer subject dir missing: {fs_subject_directory}")
        result["skipped"] = True
        result["reason"] = "missing_fs_subject_dir"
        return result

    fs_subjects_dir = fs_subject_directory.parent
    freesurfer_subject_id = fs_subject_directory.name
    tsnr_basename = tsnr_volume_path.name
    if tsnr_basename.endswith(".nii.gz"):
        volume_stem = tsnr_basename[: -len(".nii.gz")]
    elif tsnr_basename.endswith(".nii"):
        volume_stem = tsnr_basename[: -len(".nii")]
    else:
        volume_stem = tsnr_volume_path.stem

    hemisphere_to_gii_path: Dict[str, Path] = {}
    env = os.environ.copy()
    env["SUBJECTS_DIR"] = str(fs_subjects_dir)

    # 2. For each hemisphere, run FreeSurfer mri_vol2surf into a GIFTI next to the workdir.
    for hemi_code in ("L", "R"):
        if volume_stem.endswith(_STAT_SUFFIX):
            stem_without_stat = volume_stem[: -len(_STAT_SUFFIX)]
            surf_gii_filename = f"{stem_without_stat}_hemi-{hemi_code}{_STAT_SUFFIX}.surf.gii"
        else:
            surf_gii_filename = f"{volume_stem}_hemi-{hemi_code}{_STAT_SUFFIX}.surf.gii"
        surf_gii_output_path = surf_output_directory / surf_gii_filename
        cmd = [
            "mri_vol2surf",
            "--mov",
            str(tsnr_volume_path),
            "--regheader",
            freesurfer_subject_id,
            "--hemi",
            _HEMI_MAP[hemi_code],
            "--projfrac",
            "0.5",
            "--surf-fwhm",
            "2",
            "--out_type",
            "gii",
            "--o",
            str(surf_gii_output_path),
        ]
        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
            hemisphere_to_gii_path[hemi_code] = surf_gii_output_path
        except FileNotFoundError:
            logger.warning("tSNR surf: mri_vol2surf not found; skip surface projection.")
            result["skipped"] = True
            result["reason"] = "mri_vol2surf_not_found"
            return result
        except subprocess.CalledProcessError as exc:
            logger.warning(
                f"tSNR surf: projection failed for {surf_gii_output_path.name}: {exc.stderr}",
            )
            result["skipped"] = True
            result["reason"] = "projection_failed"
            if surf_gii_output_path.exists():
                surf_gii_output_path.unlink(missing_ok=True)
            return result

    result["lh_gii"] = hemisphere_to_gii_path.get("L")
    result["rh_gii"] = hemisphere_to_gii_path.get("R")
    return result
