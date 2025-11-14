# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
FreeSurfer subject preparation for FastSurfer.

Prepares subjects for FreeSurfer surface reconstruction by:
- Conforming input images to FreeSurfer space
- Running CNN-based brain segmentation
- Creating FreeSurfer-compatible output files (aseg, masks, etc.)
- Optionally applying V1 white matter correction
"""

import argparse
import copy
import sys
from pathlib import Path
from typing import Any, Literal

# Add parent directory to path for module imports
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent))

import nibabel as nib
import numpy as np

import FastSurferCNN.postprocessing.fix_v1_wm as fix_v1_wm
import FastSurferCNN.postprocessing.reduce_to_aseg as rta
from FastSurferCNN.postprocessing.postseg_utils import create_mask, create_hemisphere_masks
from FastSurferCNN.data_loader.conform import conform, is_conform
from FastSurferCNN.inference.predict import (
    RunModelOnData,
    MASK_DILATION_SIZE,
    MASK_EROSION_SIZE,
    setup_atlas_from_checkpoints,
    validate_checkpoints,
)
from FastSurferCNN.seg_statistics.quick_qc import check_volume
from FastSurferCNN.utils import PLANES, Plane, logging, parser_defaults
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.checkpoint import get_checkpoints, load_checkpoint_config_defaults
from FastSurferCNN.utils.common import find_device, handle_cuda_memory_exception
from FastSurferCNN.utils.logging import setup_logging

from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"


def _save_orig_mgz(
    output_dir: Path,
    predictor: "RunModelOnData",
) -> None:
    """Save orig.mgz from the conformed image stored by get_prediction().
    
    Note: orig.mgz should remain in conformed space (not resampled to native).
    """
    mri_dir = output_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    conf_file = mri_dir / "orig.mgz"
    predictor.save_img(conf_file, np.asanyarray(predictor._conformed_img.dataobj), dtype=np.uint8, resample_to_native=False)
    LOGGER.info(f"Saved: {conf_file.name}")


def _create_and_save_masks(
    pred_data: np.ndarray,
    output_dir: Path,
    predictor: "RunModelOnData",
) -> None:
    """Create and save brain mask and hemisphere mask."""
    LOGGER.info("Creating brain and hemisphere masks...")
    try:
        brain_mask = create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        hemi_mask = create_hemisphere_masks(brain_mask, pred_data, lut_path=predictor.lut_path)
        
        mask_path = output_dir / "mri" / "mask.mgz"
        predictor.save_img(mask_path, brain_mask, dtype=np.uint8, resample_to_native=False)
        LOGGER.info(f"  Saved: {mask_path.name}")
        
        hemi_mask_path = output_dir / "mri" / "mask_hemi.mgz"
        predictor.save_img(hemi_mask_path, hemi_mask, dtype=np.uint8, resample_to_native=False)
        LOGGER.info(f"  Saved: {hemi_mask_path.name}")
    except Exception as e:
        LOGGER.warning(f"Could not create masks: {e}")


def process_image_freesurfer_pipeline(
    output_dir: Path,
    predictor: "RunModelOnData",
    orig_img: nib.analyze.SpatialImage,
    orig_name: str | Path,
    pred_name: str = "mri/aparc+aseg.deep.mgz",
) -> tuple[np.ndarray, nib.analyze.SpatialImage]:
    """
    Process image through FreeSurfer pipeline: conform, predict, save masks.
    
    Parameters
    ----------
    output_dir : Path
        Subject directory for FreeSurfer structure (output_dir/mri/...)
    predictor : RunModelOnData
        Model runner with loaded checkpoints
    orig_img : nib.analyze.SpatialImage
        Original input image in native space
    orig_name : str | Path
        Original image path for logging
    pred_name : str
        Relative path for prediction file (e.g., "mri/aparc.ARM2atlas+aseg.deep.mgz")
    
    Returns
    -------
    tuple[np.ndarray, nib.analyze.SpatialImage]
        (prediction_data_in_conformed_space, conformed_image)
    """
    # Run prediction (automatically conforms and sets up context)
    LOGGER.info("Running prediction...")
    pred_data = predictor.get_prediction(str(orig_name), orig_img)
    
    # Save orig.mgz from conformed image
    _save_orig_mgz(output_dir, predictor)
    
    # Save prediction (uses context set by get_prediction)
    pred_file = output_dir / pred_name
    pred_file.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving prediction: {pred_file.name}")
    predictor.save_img(pred_file, pred_data, dtype=np.int16, resample_to_native=False)
    
    # Create and save masks
    _create_and_save_masks(pred_data, output_dir, predictor)
    
    return pred_data, predictor._conformed_img


def apply_v1_wm_fixing(
    pred_data: np.ndarray,
    output_dir: Path,
    predictor: "RunModelOnData",
    tpl_t1w: str,
    tpl_wm: str,
) -> np.ndarray:
    """
    Apply V1 white matter fixing using template registration.
    
    Parameters
    ----------
    pred_data : np.ndarray
        Current segmentation data
    output_dir : Path
        Subject directory
    predictor : RunModelOnData
        Model runner object
    tpl_t1w : str
        Path to template T1w image
    tpl_wm : str
        Path to template WM probability map
    
    Returns
    -------
    np.ndarray
        Corrected segmentation data
    """
    LOGGER.info("Applying V1 white matter correction...")
    
    try:
        # File paths
        seg_file = output_dir / "mri" / "aparc+aseg.deep.mgz"
        t1w_file = output_dir / "mri" / "orig.mgz"
        mask_file = output_dir / "mri" / "mask.mgz"
        hemi_mask_file = output_dir / "mri" / "mask_hemi.mgz"
        
        # Ensure masks exist
        if not mask_file.exists():
            brain_mask = create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
            predictor.save_img(mask_file, brain_mask, dtype=np.uint8, resample_to_native=False)
        
        if not hemi_mask_file.exists():
            brain_mask = nib.load(mask_file).get_fdata().astype(np.int16)
            hemi_mask = create_hemisphere_masks(brain_mask, pred_data, lut_path=predictor.lut_path)
            predictor.save_img(hemi_mask_file, hemi_mask, dtype=np.uint8, resample_to_native=False)
        
        # Run V1 WM fixing
        fix_v1_wm(
            seg_f=str(seg_file),
            t1w_f=str(t1w_file),
            mask_f=str(mask_file),
            hemi_mask_f=str(hemi_mask_file),
            lut_path=str(predictor.lut_path),
            tpl_t1w_f=tpl_t1w,
            tpl_wm_f=tpl_wm,
            roi_name='V1',
            wm_thr=0.5,
            backup_original=True,
            verbose=True
        )
        
        # Reload corrected segmentation
        pred_img = nib.load(seg_file)
        pred_data = np.asarray(pred_img.dataobj).astype(np.int16)
        
        LOGGER.info("  ✓ V1 WM correction completed")
        return pred_data
        
    except Exception as e:
        LOGGER.error(f"  ✗ V1 WM correction failed: {e}")
        LOGGER.warning("  Continuing with uncorrected segmentation")
        return pred_data


def create_aseg(
    pred_data: np.ndarray,
    output_dir: Path,
    predictor: "RunModelOnData",
) -> None:
    """
    Create and save aseg file from segmentation prediction.
    
    Converts the detailed segmentation to FreeSurfer aseg format and applies brain mask.
    
    Parameters
    ----------
    pred_data : np.ndarray
        Segmentation prediction data
    output_dir : Path
        Subject directory
    predictor : RunModelOnData
        Model runner object
    """
    LOGGER.info("Creating aseg (converting to FreeSurfer label conventions)...")
    
    # Load brain mask
    mask_path = output_dir / "mri" / "mask.mgz"
    if not mask_path.exists():
        LOGGER.warning(f"Brain mask not found at {mask_path}, creating it...")
        brain_mask = create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        predictor.save_img(mask_path, brain_mask, dtype=np.uint8, resample_to_native=False)
    else:
        brain_mask = nib.load(mask_path).get_fdata().astype(np.uint8)
    
    # Convert to aseg format
    aseg = rta.reduce_to_aseg(pred_data, lut_path=predictor.lut_path, verbose=True)
    aseg[brain_mask == 0] = 0
    
    # Save aseg
    aseg_path = output_dir / "mri" / "aseg.auto_noCC.mgz"
    aseg_dtype = np.int16 if np.any(aseg < 0) else np.uint8
    LOGGER.info(f"Saving aseg: {aseg_path.name}")
    predictor.save_img(aseg_path, aseg, dtype=aseg_dtype, resample_to_native=False)


def _validate_v1_templates(tpl_t1w: str, tpl_wm: str) -> None:
    """Validate that V1 template files exist."""
    missing_files = []
    if not Path(tpl_t1w).exists():
        missing_files.append(f"Template T1w: {tpl_t1w}")
    if not Path(tpl_wm).exists():
        missing_files.append(f"Template WM: {tpl_wm}")
    
    if missing_files:
        raise FileNotFoundError(
            "--fixv1 requires the following template files:\n  " + "\n  ".join(missing_files)
        )


def _build_predictor_kwargs(
    atlas_name: str,
    atlas_metadata: dict[str, Any],
    ckpt_ax: Path | None,
    ckpt_sag: Path | None,
    ckpt_cor: Path | None,
    device: str,
    viewagg_device: str,
    threads: int,
    batch_size: int,
    async_io: bool,
    plane_weight_coronal: float | None,
    plane_weight_axial: float | None,
    plane_weight_sagittal: float | None,
    skip_wm_correction: bool,
    vox_size: VoxSizeOption,
    orientation: OrientationType,
    image_size: bool,
    conform_to_1mm_threshold: float,
) -> dict[str, Any]:
    """Build kwargs for RunModelOnData, only including non-default preprocessing params."""
    kwargs = {
        'atlas_name': atlas_name,
        'atlas_metadata': atlas_metadata,
        'ckpt_ax': ckpt_ax,
        'ckpt_sag': ckpt_sag,
        'ckpt_cor': ckpt_cor,
        'device': device,
        'viewagg_device': viewagg_device,
        'threads': threads,
        'batch_size': batch_size,
        'async_io': async_io,
        'plane_weight_coronal': plane_weight_coronal,
        'plane_weight_axial': plane_weight_axial,
        'plane_weight_sagittal': plane_weight_sagittal,
        'fix_wm_islands': not skip_wm_correction,
    }
    
    # Only add preprocessing parameters if explicitly provided (not using defaults)
    if vox_size != "min":
        kwargs['vox_size'] = vox_size
    if orientation != "lia":
        kwargs['orientation'] = orientation
    if image_size is not True:
        kwargs['image_size'] = image_size
    if conform_to_1mm_threshold != 0.95:
        kwargs['conform_to_1mm_threshold'] = conform_to_1mm_threshold
    
    return kwargs


def prepare_freesurfer_subject(
        *,
        orig_name: Path | str,
        output_dir: Path,
        pred_name: str = "mri/aparc+aseg.deep.mgz",
        ckpt_ax: Path | None,
        ckpt_sag: Path | None,
        ckpt_cor: Path | None,
        qc_log: str = "",
        vox_size: VoxSizeOption = "min",
        device: str = "auto",
        viewagg_device: str = "auto",
        batch_size: int = 1,
        orientation: OrientationType = "lia",
        image_size: bool = True,
        async_io: bool = True,
        threads: int = -1,
        conform_to_1mm_threshold: float = 0.95,
        plane_weight_coronal: float | None = None,
        plane_weight_axial: float | None = None,
        plane_weight_sagittal: float | None = None,
        skip_wm_correction: bool = False,
        fixv1: bool = False,
        tpl_t1w: str | None = None,
        tpl_wm: str | None = None,
        **kwargs,
) -> Literal[0] | str:
    """
    Prepare a subject for FreeSurfer surface reconstruction.
    
    Runs the complete pipeline:
    1. Conforms input image
    2. Runs segmentation prediction
    3. Optionally applies V1 WM fixing
    4. Creates aseg and brain mask files
    
    Parameters
    ----------
    orig_name : Path | str
        Path to input T1 image
    output_dir : Path
        Output subject directory (FreeSurfer structure)
    pred_name : str
        Relative path for prediction file
    ckpt_ax, ckpt_sag, ckpt_cor : Path | None
        Checkpoint paths for each plane
    fixv1 : bool
        Apply V1 white matter correction
    skip_wm_correction : bool
        Skip WM island correction during prediction
    
    Returns
    -------
    Literal[0] | str
        0 on success, error message on failure
    """
    if kwargs:
        LOGGER.warning(f"Unknown arguments: {list(kwargs.keys())}")

    # Validate inputs
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    if fixv1:
        _validate_v1_templates(tpl_t1w, tpl_wm)
    
    # Log plane configuration
    provided_planes = [p for ckpt, p in [(ckpt_ax, "axial"), (ckpt_cor, "coronal"), (ckpt_sag, "sagittal")] if ckpt]
    LOGGER.info(f"Running inference with {len(provided_planes)} plane(s): {', '.join(provided_planes)}")

    # Set up QC logging
    qc_file_handle = None
    if qc_log:
        try:
            qc_file_handle = open(qc_log, "w")
        except (NotADirectoryError, FileNotFoundError):
            LOGGER.warning("QC log directory does not exist. QC log will not be saved.")

    try:
        # Download checkpoints if needed
        LOGGER.info("Checking or downloading checkpoints...")
        urls = load_checkpoint_config_defaults("url", filename=CHECKPOINT_PATHS_FILE)
        get_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag, urls=urls)
        
        # Extract atlas information from checkpoints
        atlas_name, atlas_metadata = setup_atlas_from_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)

        # Update pred_name to include atlas name
        if pred_name == "mri/aparc+aseg.deep.mgz":
            pred_name = f"mri/aparc.{atlas_name}atlas+aseg.deep.mgz"
            LOGGER.info(f"Updated output filename to: {pred_name}")

        # Prepare subject directory
        subject_dir = Path(output_dir).resolve()
        subject_dir.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Subject directory: {subject_dir}")

        # Build predictor
        predictor_kwargs = _build_predictor_kwargs(
            atlas_name, atlas_metadata, ckpt_ax, ckpt_sag, ckpt_cor,
            device, viewagg_device, threads, batch_size, async_io,
            plane_weight_coronal, plane_weight_axial, plane_weight_sagittal,
            skip_wm_correction, vox_size, orientation, image_size, conform_to_1mm_threshold
        )
        predictor = RunModelOnData(**predictor_kwargs)

        # Load and process image
        orig_img = nib.load(orig_name)
        pred_data, conformed_img = process_image_freesurfer_pipeline(
            output_dir=subject_dir,
            predictor=predictor,
            orig_img=orig_img,
            orig_name=orig_name,
            pred_name=pred_name
        )
        LOGGER.info(f"Prediction saved: {pred_name}")
        
        # Apply V1 WM fixing if requested
        if fixv1:
            pred_data = apply_v1_wm_fixing(
                pred_data, subject_dir, predictor, tpl_t1w, tpl_wm
            )

        # Create aseg
        create_aseg(pred_data, subject_dir, predictor)

        # Run QC statistics
        LOGGER.info("Computing segmentation volume statistics...")
        seg_voxvol = np.prod(conformed_img.header.get_zooms())
        check_volume(pred_data, seg_voxvol)
            
    except RuntimeError as e:
        if not handle_cuda_memory_exception(e):
            return e.args[0]
    finally:
        if qc_file_handle is not None:
            qc_file_handle.close()

    return 0


def make_parser():
    """Create argument parser for FreeSurfer preparation."""
    parser = argparse.ArgumentParser(
        description="FastSurfer FreeSurfer preparation - conform, segment, and prepare for surface reconstruction"
    )

    # Input/output
    parser = parser_defaults.add_arguments(parser, ["t1"])
    parser.add_argument(
        "--output_dir",
        type=Path,
        required=True,
        help="Output subject directory (FreeSurfer structure)"
    )
    parser = parser_defaults.add_arguments(
        parser,
        ["conformed_name", "aseg_name", "seg_log", "qc_log"],
    )

    # Checkpoints (optional - user can specify 1, 2, or 3 planes)
    files: dict[Plane, str | Path | None] = {k: None for k in PLANES}
    parser = parser_defaults.add_plane_flags(parser, "checkpoint", files, CHECKPOINT_PATHS_FILE)

    # Technical parameters
    parser = parser_defaults.add_arguments(
        parser,
        ["vox_size", "conform_to_1mm_threshold", "orientation", "image_size",
         "device", "viewagg_device", "batch_size", "async_io", "threads"]
    )
    
    # Multi-view prediction weights
    parser.add_argument(
        "--plane_weight_coronal",
        type=float,
        default=None,
        help="Weight for coronal plane in multi-view prediction (default: 0.4)",
    )
    parser.add_argument(
        "--plane_weight_axial",
        type=float,
        default=None,
        help="Weight for axial plane in multi-view prediction (default: 0.4)",
    )
    parser.add_argument(
        "--plane_weight_sagittal",
        type=float,
        default=None,
        help="Weight for sagittal plane in multi-view prediction (default: 0.2)",
    )
    
    # Post-processing
    parser.add_argument(
        "--no_wm_island_correction",
        dest="skip_wm_correction",
        action="store_true",
        help="Skip WM island correction during segmentation. By default, WM island "
             "correction is enabled to fix occasional CNN mislabeling.",
    )
    
    # V1 WM fixing
    parser.add_argument(
        "--fixv1",
        action="store_true",
        help="Fix missing thin WM in V1 using template registration",
    )
    parser.add_argument(
        "--tpl_t1w",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/tpl-NMT2Sym_res-05_T1w_brain_V1.nii.gz"),
        help="Path to template T1w image for V1 fixing",
    )
    parser.add_argument(
        "--tpl_wm",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/atlas-ARM_level-2_space-NMT2Sym_res-05_calcarine_WM.nii.gz"),
        help="Path to template WM probability map for V1 fixing",
    )
    
    return parser


def main(**kwargs) -> Literal[0] | str:
    """
    Main entry point for FreeSurfer preparation.
    
    Resolves output directory path and delegates to prepare_freesurfer_subject.
    """
    # Resolve output directory
    output_dir = Path(kwargs['output_dir']).resolve()
    kwargs['output_dir'] = output_dir
    
    LOGGER.info("=" * 80)
    LOGGER.info("FastSurfer FreeSurfer Preparation")
    LOGGER.info(f"Output directory: {output_dir}")
    LOGGER.info("=" * 80)
    
    return prepare_freesurfer_subject(**kwargs)


if __name__ == "__main__":
    parser = make_parser()
    _args = parser.parse_args()

    # Set up logging
    setup_logging(_args.log_name)

    # Remove log_name from args before passing to main (it's only used for logging setup)
    main_args = vars(_args)
    main_args.pop("log_name", None)

    sys.exit(main(**main_args))

