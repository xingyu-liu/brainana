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
FreeSurfer subfolder preparation for FastSurferCNN.

This module provides functions to prepare segmentation results for FreeSurfer
surface reconstruction pipeline, including conforming, prediction, post-processing,
and creating FreeSurfer-compatible output files.
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


def process_image_freesurfer_pipeline(
    output_dir: Path,
    predictor: "RunModelOnData",
    orig_img_native: nib.analyze.SpatialImage | None = None,
    conform_to_1mm_threshold: float | None = None,
    vox_size: VoxSizeOption | None = None,
    orientation: OrientationType | None = None,
    image_size: bool | None = None,
    orig_name: str | Path | None = None,
    pred_name: str = "mri/aparc+aseg.deep.mgz",
) -> tuple[np.ndarray, nib.analyze.SpatialImage]:
    """
    Process a single image through the FreeSurfer pipeline (conform, predict).
    
    This function implements the core processing logic for FreeSurfer mode.
    Always uses FreeSurfer directory structure (output_dir/mri/...).
    Returns results in conformed space.
    
    Parameters
    ----------
    output_dir : Path
        Output directory (equivalent to subject directory). 
        For FreeSurfer mode: sub_dir/sub_id
    predictor : RunModelOnData
        Model runner object (required)
    orig_img_native : nib.analyze.SpatialImage, optional
        Original input image in native space. If None, loads from output_dir/mri/orig.mgz
    conform_to_1mm_threshold : float, optional
        Threshold for conforming to 1mm (required if orig_img_native is provided)
    vox_size : VoxSizeOption, optional
        Voxel size option (required if orig_img_native is provided)
    orientation : OrientationType, optional
        Target orientation (required if orig_img_native is provided)
    image_size : bool, optional
        Whether to preserve image size (required if orig_img_native is provided)
    orig_name : str | Path, optional
        Original image filename/path for logging
    pred_name : str, default="mri/aparc+aseg.deep.mgz"
        Relative path for saving prediction (FreeSurfer structure)
    
    Returns
    -------
    tuple[np.ndarray, nib.analyze.SpatialImage]
        (prediction_data_in_conformed_space, conformed_image)
    """
    # Determine conformed image
    if orig_img_native is not None:
        # Need to conform
        if conform_to_1mm_threshold is None or vox_size is None or orientation is None or image_size is None:
            raise ValueError("conform_to_1mm_threshold, vox_size, orientation, and image_size are required when orig_img_native is provided")
        
        LOGGER.info("Conforming image...")
        if not is_conform(orig_img_native, 
                         threshold_1mm=conform_to_1mm_threshold,
                         vox_size=vox_size,
                         orientation=orientation,
                         img_size=image_size,
                         verbose=True):
            conformed_img = conform(orig_img_native,
                                threshold_1mm=conform_to_1mm_threshold,
                                vox_size=vox_size,
                                orientation=orientation,
                                img_size=image_size)
        else:
            conformed_img = orig_img_native
        
        # Save conformed image to FreeSurfer structure
        mri_dir = output_dir / "mri"
        mri_dir.mkdir(parents=True, exist_ok=True)
        conf_file = mri_dir / "orig.mgz"
        predictor.save_img(conf_file, np.asanyarray(conformed_img.dataobj), conformed_img, dtype=np.uint8)
        orig_name_for_pred = str(orig_img_native) if orig_name is None else str(orig_name)
    else:
        # FreeSurfer mode: load conformed image from output_dir/mri/orig.mgz
        conf_file = output_dir / "mri" / "orig.mgz"
        if not conf_file.exists():
            raise FileNotFoundError(f"Conformed image not found at {conf_file}. Expected for FreeSurfer mode.")
        LOGGER.info(f"Loading conformed image from {conf_file}")
        conformed_img = nib.load(conf_file)
        orig_name_for_pred = str(orig_name) if orig_name is not None else str(conf_file)
    
    # Run prediction in conformed space
    LOGGER.info("Running prediction...")
    pred_data_conformed = predictor.get_prediction(orig_name_for_pred, conformed_img)
    
    # Save prediction to FreeSurfer structure
    pred_file = output_dir / pred_name
    pred_file.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving prediction: {pred_file.name}")
    predictor.save_img(pred_file, pred_data_conformed, conformed_img, dtype=np.int16)
    
    # Create and save brain mask and hemisphere mask in mri/
    LOGGER.info("Creating brain and hemisphere masks...")
    try:
        brain_mask = create_mask(copy.deepcopy(pred_data_conformed), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        hemi_mask = create_hemisphere_masks(brain_mask, pred_data_conformed, lut_path=predictor.lut_path)
        
        mask_path = output_dir / "mri" / "mask.mgz"
        predictor.save_img(mask_path, brain_mask, conformed_img, dtype=np.uint8)
        LOGGER.info(f"  Saved: {mask_path.name}")
        
        hemi_mask_path = output_dir / "mri" / "mask_hemi.mgz"
        predictor.save_img(hemi_mask_path, hemi_mask, conformed_img, dtype=np.uint8)
        LOGGER.info(f"  Saved: {hemi_mask_path.name}")
    except Exception as e:
        LOGGER.warning(f"Could not create masks: {e}")
    
    return pred_data_conformed, conformed_img


def apply_v1_wm_fixing(
    pred_data: np.ndarray,
    output_dir: Path,
    orig_img: nib.analyze.SpatialImage,
    predictor: "RunModelOnData",
    tpl_t1w: str,
    tpl_wm: str,
    pred_name: str,
    conf_name: str,
    brainmask_name: str,
) -> np.ndarray:
    """
    Apply V1 white matter fixing using template registration.
    
    Parameters
    ----------
    pred_data : np.ndarray
        Current segmentation data.
    output_dir : Path
        Output directory (subject directory).
    orig_img : nib.analyze.SpatialImage
        Original image.
    predictor : RunModelOnData
        Model runner object.
    tpl_t1w : str
        Path to template T1w image.
    tpl_wm : str
        Path to template WM probability map.
    pred_name : str
        Relative path to prediction file (e.g., "mri/aparc+aseg.deep.mgz").
    conf_name : str
        Relative path to conformed image (e.g., "mri/orig.mgz").
    brainmask_name : str
        Relative path to brain mask (e.g., "mri/mask.mgz").
    
    Returns
    -------
    np.ndarray
        Corrected segmentation data.
    """
    LOGGER.info("Applying V1 white matter correction...")
    
    try:
        # Get file paths (FreeSurfer structure)
        segfile = output_dir / pred_name
        conf_file = output_dir / conf_name
        mask_file = output_dir / brainmask_name
        
        # Create masks if they don't exist
        if not Path(mask_file).exists():
            LOGGER.info("  Creating brain mask...")
            temp_mask = create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
            predictor.save_img(mask_file, temp_mask, orig_img, dtype=np.uint8)
        
        # Create hemisphere mask if it doesn't exist
        hemi_mask_file = mask_file.parent / (mask_file.stem + "_hemi" + mask_file.suffix)
        if not hemi_mask_file.exists():
            LOGGER.info("  Creating hemisphere mask...")
            temp_mask = nib.load(mask_file).get_fdata().astype(np.int16)
            hemi_mask = create_hemisphere_masks(temp_mask, pred_data, lut_path=predictor.lut_path)
            predictor.save_img(hemi_mask_file, hemi_mask, orig_img, dtype=np.uint8)
        
        # Run V1 WM fixing
        fix_v1_wm(
            seg_f=str(segfile),
            t1w_f=str(conf_file),
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
        LOGGER.info("  Reloading corrected segmentation...")
        pred_img = nib.load(segfile)
        pred_data = np.asarray(pred_img.dataobj).astype(np.int16)
        
        LOGGER.info("  ✓ V1 WM correction completed")
        return pred_data
        
    except Exception as e:
        LOGGER.error(f"  ✗ V1 WM correction failed: {e}")
        LOGGER.warning("  Continuing with uncorrected segmentation")
        return pred_data


def create_aseg_and_brainmask(
    pred_data: np.ndarray,
    output_dir: Path,
    orig_img: nib.analyze.SpatialImage,
    predictor: "RunModelOnData",
    brainmask_name: str,
    aseg_name: str,
    skip_wm_correction: bool = False,
    debug_wm_correction: bool = False,
) -> None:
    """
    Create aseg and brainmask files.
    
    Note: WM island correction is applied during segmentation (in get_prediction),
    not here. The skip_wm_correction parameter is passed to RunModelOnData to control
    whether WM island fixing is applied during prediction.
    
    Saves files synchronously (no async).
    
    Parameters
    ----------
    pred_data : np.ndarray
        Prediction data (already has WM island correction applied if enabled).
    output_dir : Path
        Output directory (subject directory).
    orig_img : nib.analyze.SpatialImage
        Original image.
    predictor : RunModelOnData
        Model runner object.
    brainmask_name : str
        Relative path to brain mask file (e.g., "mri/mask.mgz").
    aseg_name : str
        Relative path to aseg file (e.g., "mri/aseg.auto_noCC.mgz").
    skip_wm_correction : bool
        Whether WM island correction was skipped during prediction (for logging).
    debug_wm_correction : bool
        Unused (kept for backward compatibility).
    """
    # Note: Brain mask and hemisphere mask are already saved in process_image_freesurfer_pipeline
    # This function only creates aseg
    
    # Load brain mask (already saved)
    mask_path = output_dir / brainmask_name
    if not mask_path.exists():
        LOGGER.warning(f"Brain mask not found at {mask_path}, creating it...")
        brain_mask = create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        predictor.save_img(mask_path, brain_mask, orig_img, dtype=np.uint8)
    else:
        brain_mask = nib.load(mask_path).get_fdata().astype(np.uint8)
    
    # Create and save aseg
    # Note: WM island correction is already applied during segmentation (in get_prediction)
    LOGGER.info("Creating aseg (converting to FreeSurfer label conventions)...")
    aseg = rta.reduce_to_aseg(pred_data, lut_path=predictor.lut_path, verbose=True)
    aseg[brain_mask == 0] = 0
    
    # Save final aseg
    aseg_path = output_dir / aseg_name
    aseg_dtype = np.int16 if np.any(aseg < 0) else np.uint8
    LOGGER.info(f"Saving aseg: {aseg_path.name}")
    predictor.save_img(aseg_path, aseg, orig_img, dtype=aseg_dtype)


def prepare_freesurfer_subject(
        *,
        orig_name: Path | str,
        output_dir: Path,
        pred_name: str,
        ckpt_ax: Path | None,
        ckpt_sag: Path | None,
        ckpt_cor: Path | None,
        qc_log: str = "",
        conf_name: str = "mri/orig.mgz",
        brainmask_name: str = "mri/mask.mgz",
        aseg_name: str = "mri/aseg.auto_noCC.mgz",
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
        debug_wm_correction: bool = False,
        fixv1: bool = False,
        tpl_t1w: str | None = None,
        tpl_wm: str | None = None,
        **kwargs,
) -> Literal[0] | str:
    """
    Prepare a subject for FreeSurfer surface reconstruction.
    
    This function runs the complete pipeline:
    1. Conforms the input image
    2. Runs segmentation prediction
    3. Optionally applies V1 WM fixing
    4. Creates aseg and brain mask files
    
    All outputs are saved in FreeSurfer directory structure (output_dir/mri/...).
    
    Parameters
    ----------
    orig_name : Path, str
        Path to input T1 image
    output_dir : Path
        Output directory (subject directory)
    pred_name : str
        Relative path for prediction file (e.g., "mri/aparc.ARM2atlas+aseg.deep.mgz")
    (other parameters same as RunModelOnData and post-processing functions)
    
    Returns
    -------
    int or str
        0 on success, error message on failure
    """
    if len(kwargs) > 0:
        LOGGER.warning(f"Unknown arguments {list(kwargs.keys())} in FreeSurfer mode.")

    # Validate that at least one checkpoint is provided
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    
    # Validate V1 fixing parameters and template files
    if fixv1:
        missing_files = []
        if not Path(tpl_t1w).exists():
            missing_files.append(f"Template T1w not found: {tpl_t1w}")
        if not Path(tpl_wm).exists():
            missing_files.append(f"Template WM not found: {tpl_wm}")
        
        if missing_files:
            raise FileNotFoundError(
                f"--fixv1 requires template files:\n  " + "\n  ".join(missing_files)
            )
    
    provided_planes = []
    if ckpt_ax is not None:
        provided_planes.append("axial")
    if ckpt_cor is not None:
        provided_planes.append("coronal")
    if ckpt_sag is not None:
        provided_planes.append("sagittal")
    
    LOGGER.info(f"Running inference with {len(provided_planes)} plane(s): {', '.join(provided_planes)}")

    qc_file_handle = None
    if qc_log != "":
        try:
            qc_file_handle = open(qc_log, "w")
        except NotADirectoryError:
            LOGGER.warning(
                "The directory in the provided QC log file path does not exist!"
            )
            LOGGER.warning("The QC log file will not be saved.")

    # Download checkpoints if they do not exist (only for planes that are being used)
    # see utils/checkpoint.py for default paths
    if any(ckpt is not None for ckpt in [ckpt_ax, ckpt_cor, ckpt_sag]):
        LOGGER.info("Checking or downloading checkpoints for specified planes...")
        
        urls = load_checkpoint_config_defaults("url", filename=CHECKPOINT_PATHS_FILE)

        # Only pass non-None checkpoints to get_checkpoints
        get_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag, urls=urls)
    
    # Extract and validate atlas information from checkpoints
    atlas_name, atlas_metadata = setup_atlas_from_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)

    # Update pred_name to use the atlas name if it's using the generic default
    # This ensures the output filename matches the atlas (e.g., aparc.ARM2atlas+aseg.deep.mgz for ARM2)
    default_pred_name = "mri/aparc+aseg.deep.mgz"
    if pred_name == default_pred_name:
        pred_name = f"mri/aparc.{atlas_name}atlas+aseg.deep.mgz"
        LOGGER.info(f"Updated output filename to: {pred_name}")

    # Use output_dir directly as the subject directory
    subject_dir = Path(output_dir).resolve()
    subject_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Subject directory: {subject_dir}")

    try:
        # Set up model with atlas information from checkpoint
        # Config is loaded from checkpoint automatically - no separate config files needed!
        # Preprocessing parameters (vox_size, orientation, image_size, conform_to_1mm_threshold)
        # are loaded from checkpoint by RunModelOnData. Only pass them if explicitly provided.
        predictor_kwargs = {
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
        # Check against the default values to see if they were explicitly set
        if vox_size != "min":  # Default is "min"
            predictor_kwargs['vox_size'] = vox_size
        if orientation != "lia":  # Default is "lia"
            predictor_kwargs['orientation'] = orientation
        if image_size is not True:  # Default is True
            predictor_kwargs['image_size'] = image_size
        if conform_to_1mm_threshold != 0.95:  # Default is 0.95
            predictor_kwargs['conform_to_1mm_threshold'] = conform_to_1mm_threshold
        
        predictor = RunModelOnData(**predictor_kwargs)
    except RuntimeError as e:
        return e.args[0]

    try:
        # Load original image
        orig_img_native = nib.load(orig_name)
        
        # Get preprocessing parameters from predictor (loaded from checkpoint)
        # These are the actual values that will be used (from checkpoint or overrides)
        actual_vox_size = predictor.vox_size
        actual_orientation = predictor.orientation
        actual_image_size = predictor.image_size
        actual_conform_to_1mm_threshold = predictor.conform_to_1mm_threshold
        
        # Run FreeSurfer pipeline (conform, predict)
        # Results saved to subject_dir/mri/... (FreeSurfer structure)
        pred_data, orig_img = process_image_freesurfer_pipeline(
            output_dir=subject_dir,
            predictor=predictor,
            orig_img_native=orig_img_native,
            conform_to_1mm_threshold=actual_conform_to_1mm_threshold,
            vox_size=actual_vox_size,
            orientation=actual_orientation,
            image_size=actual_image_size,
            orig_name=orig_name,
            pred_name=pred_name
        )
        
        LOGGER.info(f"Prediction saved: {pred_name}")
        
        # Apply V1 WM fixing if requested
        if fixv1:
            pred_data = apply_v1_wm_fixing(
                pred_data=pred_data,
                output_dir=subject_dir,
                orig_img=orig_img,
                predictor=predictor,
                tpl_t1w=tpl_t1w,
                tpl_wm=tpl_wm,
                pred_name=pred_name,
                conf_name=conf_name,
                brainmask_name=brainmask_name
            )

        # Create aseg files (optional, uses FreeSurfer conventions)
        # Note: Brain mask and hemisphere mask are already saved by process_image_freesurfer_pipeline
        create_aseg_and_brainmask(
            pred_data=pred_data,
            output_dir=subject_dir,
            orig_img=orig_img,
            predictor=predictor,
            brainmask_name=brainmask_name,
            aseg_name=aseg_name,
            skip_wm_correction=skip_wm_correction,
            debug_wm_correction=debug_wm_correction
        )

        # Run QC stats (informational only)
        LOGGER.info("Computing segmentation volume statistics...")
        seg_voxvol = np.prod(orig_img.header.get_zooms())
        check_volume(pred_data, seg_voxvol)
            
    except RuntimeError as e:
        if not handle_cuda_memory_exception(e):
            return e.args[0]

    if qc_file_handle is not None:
        qc_file_handle.close()

    return 0


def make_parser():
    """
    Create the argparse object for FreeSurfer preparation.

    Returns
    -------
    argparse.ArgumentParser
        The parser object.
    """
    parser = argparse.ArgumentParser(description="FastSurfer FreeSurfer preparation")

    # 1. Input options
    parser = parser_defaults.add_arguments(
        parser,
        ["t1"],
    )
    
    # 2. FreeSurfer mode input/output options
    parser.add_argument(
        "--output_dir",
        type=Path,
        required=True,
        help="Output directory (subject directory)"
    )
    parser = parser_defaults.add_arguments(
        parser,
        ["conformed_name", "brainmask_name", "aseg_name", "seg_log", "qc_log"],
    )

    # 3. Checkpoint to load (contains full config - no separate config files needed!)
    # Make checkpoints optional - user can specify 1, 2, or 3 planes
    files: dict[Plane, str | Path | None] = {k: None for k in PLANES}
    parser = parser_defaults.add_plane_flags(parser, "checkpoint", files, CHECKPOINT_PATHS_FILE)

    # 4. technical parameters
    image_flags = ["vox_size", "conform_to_1mm_threshold", "orientation", "image_size", "device"]
    tech_flags = ["viewagg_device", "batch_size", "async_io", "threads"]
    parser = parser_defaults.add_arguments(parser, image_flags + tech_flags)
    
    # 5. Multi-view prediction plane weights
    parser.add_argument(
        "--plane_weight_coronal",
        dest="plane_weight_coronal",
        type=float,
        help="Weight for coronal plane in multi-view prediction (default: 0.4)",
        default=None,
    )
    parser.add_argument(
        "--plane_weight_axial",
        dest="plane_weight_axial", 
        type=float,
        help="Weight for axial plane in multi-view prediction (default: 0.4)",
        default=None,
    )
    parser.add_argument(
        "--plane_weight_sagittal",
        dest="plane_weight_sagittal",
        type=float,
        help="Weight for sagittal plane in multi-view prediction (default: 0.2)",
        default=None,
    )
    
    # 6. Post-processing options
    parser.add_argument(
        "--no_wm_island_correction",
        dest="skip_wm_correction",
        action="store_true",
        help="Skip WM island correction during segmentation (flipping mislabeled disconnected WM regions to correct hemisphere). "
             "By default, WM island correction is enabled during prediction to fix occasional CNN mislabeling and improve downstream processing (e.g., mri_cc performance).",
        default=False,
    )
    parser.add_argument(
        "--debug_wm_correction",
        dest="debug_wm_correction",
        action="store_true",
        help="[DEPRECATED] Debug flag for WM island correction. WM island correction is now applied during segmentation, "
             "so debug files are no longer generated. This flag is kept for backward compatibility but has no effect.",
        default=False,
    )
    
    # 7. V1 WM fixing options
    parser.add_argument(
        "--fixv1",
        dest="fixv1",
        action="store_true",
        help="Fix missing thin WM in V1 using template registration (requires additional template files).",
        default=False,
    )
    parser.add_argument(
        "--tpl_t1w",
        dest="tpl_t1w",
        help="Path to template T1w image cropped to V1 ROI (default: atlas/template/tpl-NMT2Sym_res-05_T1w_brain_V1.nii.gz).",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/tpl-NMT2Sym_res-05_T1w_brain_V1.nii.gz"),
    )
    parser.add_argument(
        "--tpl_wm",
        dest="tpl_wm",
        help="Path to template V1 WM probability map (default: atlas/template/atlas-ARM_level-2_space-NMT2Sym_res-05_calcarine_WM.nii.gz).",
        default=str(FASTSURFER_ROOT / "FastSurferCNN/atlas/template/atlas-ARM_level-2_space-NMT2Sym_res-05_calcarine_WM.nii.gz"),
    )
    
    return parser


def main(
        *,
        orig_name: Path | str,
        output_dir: Path,
        pred_name: str = "mri/aparc+aseg.deep.mgz",
        ckpt_ax: Path | None,
        ckpt_sag: Path | None,
        ckpt_cor: Path | None,
        qc_log: str = "",
        conf_name: str = "mri/orig.mgz",
        brainmask_name: str = "mri/mask.mgz",
        aseg_name: str = "mri/aseg.auto_noCC.mgz",
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
        debug_wm_correction: bool = False,
        fixv1: bool = False,
        tpl_t1w: str | None = None,
        tpl_wm: str | None = None,
        **kwargs,
) -> Literal[0] | str:
    """
    Main entry point for FreeSurfer preparation.
    
    Parameters
    ----------
    orig_name : Path, str
        Path to input T1 image
    output_dir : Path
        Output directory (subject directory)
    (other parameters documented in prepare_freesurfer_subject)
    """
    
    if len(kwargs) > 0:
        LOGGER.warning(f"Unknown arguments {list(kwargs.keys())} in {__file__}:main.")
    
    # Convert to Path and ensure it's absolute
    output_dir_path = Path(output_dir)
    if not output_dir_path.is_absolute():
        # If relative, resolve relative to current working directory
        freesurfer_output_dir = output_dir_path.resolve()
    else:
        # If absolute, use as-is (don't resolve as it may not exist yet)
        freesurfer_output_dir = output_dir_path
    
    LOGGER.info("=" * 80)
    LOGGER.info("Running in FREESURFER mode")
    LOGGER.info(f"Output directory (raw): {output_dir}")
    LOGGER.info(f"Output directory (resolved): {freesurfer_output_dir}")
    LOGGER.info("=" * 80)
    
    # Call FreeSurfer preparation function
    return prepare_freesurfer_subject(
        orig_name=orig_name,
        output_dir=freesurfer_output_dir,
        pred_name=pred_name,
        ckpt_ax=ckpt_ax,
        ckpt_sag=ckpt_sag,
        ckpt_cor=ckpt_cor,
        qc_log=qc_log,
        conf_name=conf_name,
        brainmask_name=brainmask_name,
        aseg_name=aseg_name,
        vox_size=vox_size,
        device=device,
        viewagg_device=viewagg_device,
        batch_size=batch_size,
        orientation=orientation,
        image_size=image_size,
        async_io=async_io,
        threads=threads,
        conform_to_1mm_threshold=conform_to_1mm_threshold,
        plane_weight_coronal=plane_weight_coronal,
        plane_weight_axial=plane_weight_axial,
        plane_weight_sagittal=plane_weight_sagittal,
        skip_wm_correction=skip_wm_correction,
        debug_wm_correction=debug_wm_correction,
        fixv1=fixv1,
        tpl_t1w=tpl_t1w,
        tpl_wm=tpl_wm,
        **kwargs,
    )


if __name__ == "__main__":
    parser = make_parser()
    _args = parser.parse_args()

    # Set up logging
    setup_logging(_args.log_name)

    # Remove log_name from args before passing to main (it's only used for logging setup)
    main_args = vars(_args)
    main_args.pop("log_name", None)

    sys.exit(main(**main_args))

