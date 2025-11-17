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
import shutil
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
from FastSurferCNN.data_loader import data_utils as data_ultils
from FastSurferCNN.data_loader.conform import conform, is_conform
from FastSurferCNN.inference.predict import (
    run_segmentation,
    setup_atlas_from_checkpoints,
    validate_checkpoints,
)
from FastSurferCNN.inference.skullstripping import skullstripping
from FastSurferCNN.seg_statistics.quick_qc import check_volume
from FastSurferCNN.utils import PLANES, Plane, logging, parser_defaults
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.checkpoint import get_checkpoints, get_paths_from_yaml
from FastSurferCNN.utils.common import find_device, handle_cuda_memory_exception
from FastSurferCNN.utils.logging import setup_logging

from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"


def _conform_and_save_orig_mgz(
    input_image: Path | str,
    output_dir: Path,
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
    image_size: bool = True,
    conform_to_1mm_threshold: float = 0.95,
) -> Path:
    """
    Conform input image to FreeSurfer standard space and save as orig.mgz.
    
    Parameters
    ----------
    input_image : Path | str
        Path to input image
    output_dir : Path
        Output directory (FreeSurfer subject directory)
    vox_size : VoxSizeOption
        Voxel size option
    orientation : OrientationType
        Target orientation
    image_size : bool
        Whether to enforce standard image size
    conform_to_1mm_threshold : float
        Threshold for conforming to 1mm resolution
    
    Returns
    -------
    Path
        Path to saved orig.mgz file
    """
    from FastSurferCNN.utils.arg_types import vox_size as _vox_size
    
    input_image = Path(input_image)
    mri_dir = output_dir / "mri"
    mri_dir.mkdir(parents=True, exist_ok=True)
    orig_mgz = mri_dir / "orig.mgz"
    
    LOGGER.info(f"Loading and conforming input image: {input_image}")
    orig_img = nib.load(input_image)
    
    # Check if conforming is needed
    conform_kwargs = {
        "threshold_1mm": conform_to_1mm_threshold,
        "vox_size": _vox_size(vox_size) if isinstance(vox_size, str) else vox_size,
        "orientation": orientation,
        "img_size": image_size,
    }
    
    if not is_conform(orig_img, **conform_kwargs, verbose=True):
        LOGGER.info("Conforming image to FreeSurfer standard space...")
        conformed_img = conform(orig_img, **conform_kwargs)
    else:
        LOGGER.info("Image is already conformed")
        conformed_img = orig_img
    
    # Save conformed image as orig.mgz (in conformed space, not resampled to native)
    conformed_data = np.asanyarray(conformed_img.dataobj)
    data_ultils.save_image(
        conformed_img.header.copy(),
        conformed_img.affine,
        conformed_data,
        orig_mgz,
        dtype=np.uint8
    )
    LOGGER.info(f"Saved conformed image: {orig_mgz}")
    
    return orig_mgz


def apply_v1_wm_fixing(
    seg_file: Path,
    output_dir: Path,
    lut_path: Path,
    tpl_t1w: str,
    tpl_wm: str,
) -> None:
    """
    Apply V1 white matter fixing using template registration.
    
    Parameters
    ----------
    seg_file : Path
        Path to segmentation file
    output_dir : Path
        Subject directory
    lut_path : Path
        Path to LUT file
    tpl_t1w : str
        Path to template T1w image
    tpl_wm : str
        Path to template WM probability map
    """
    LOGGER.info("Applying V1 white matter correction...")
    
    try:
        # File paths
        t1w_file = output_dir / "mri" / "orig.mgz"
        mask_file = output_dir / "mri" / "mask.mgz"
        hemi_mask_file = output_dir / "mri" / "mask_hemi.mgz"
        
        # Ensure required files exist
        if not all(f.exists() for f in [seg_file, t1w_file, mask_file, hemi_mask_file]):
            raise FileNotFoundError(
                f"Required files missing for V1 fixing. "
                f"Need: {seg_file}, {t1w_file}, {mask_file}, {hemi_mask_file}"
            )
        
        # Run V1 WM fixing
        fix_v1_wm(
            seg_f=str(seg_file),
            t1w_f=str(t1w_file),
            mask_f=str(mask_file),
            hemi_mask_f=str(hemi_mask_file),
            lut_path=str(lut_path),
            tpl_t1w_f=tpl_t1w,
            tpl_wm_f=tpl_wm,
            roi_name='V1',
            wm_thr=0.5,
            backup_original=True,
            verbose=True
        )
        
        LOGGER.info("  ✓ V1 WM correction completed")
        
    except Exception as e:
        LOGGER.error(f"  ✗ V1 WM correction failed: {e}")
        raise


def create_aseg(
    seg_file: Path,
    output_dir: Path,
    lut_path: Path,
) -> None:
    """
    Create and save aseg file from segmentation prediction.
    
    Converts the detailed segmentation to FreeSurfer aseg format and applies brain mask.
    
    Parameters
    ----------
    seg_file : Path
        Path to segmentation file
    output_dir : Path
        Subject directory
    lut_path : Path
        Path to LUT file
    """
    LOGGER.info("Creating aseg (converting to FreeSurfer label conventions)...")
    
    # Load segmentation and mask
    pred_img = nib.load(seg_file)
    pred_data = np.asarray(pred_img.dataobj).astype(np.int16)
    
    mask_path = output_dir / "mri" / "mask.mgz"
    if not mask_path.exists():
        raise FileNotFoundError(f"Brain mask not found at {mask_path}")
    brain_mask = nib.load(mask_path).get_fdata().astype(np.uint8)
    
    # Convert to aseg format
    aseg = rta.reduce_to_aseg(pred_data, lut_path=lut_path, verbose=True)
    aseg[brain_mask == 0] = 0
    
    # Save aseg
    aseg_path = output_dir / "mri" / "aseg.auto_noCC.mgz"
    aseg_dtype = np.int16 if np.any(aseg < 0) else np.uint8
    
    # Use the same header/affine as the segmentation
    data_ultils.save_image(
        pred_img.header.copy(),
        pred_img.affine,
        aseg,
        aseg_path,
        dtype=aseg_dtype
    )
    LOGGER.info(f"Saving aseg: {aseg_path.name}")


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
        urls = get_paths_from_yaml("url", filename=CHECKPOINT_PATHS_FILE)
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

        # Step 1: Conform and save orig.mgz
        LOGGER.info("=" * 80)
        LOGGER.info("Step 1: Conforming input image to FreeSurfer standard space")
        LOGGER.info("=" * 80)
        orig_mgz = _conform_and_save_orig_mgz(
            input_image=orig_name,
            output_dir=subject_dir,
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
        )

        # Step 2: Run skullstripping on conformed image
        LOGGER.info("=" * 80)
        LOGGER.info("Step 2: Running skullstripping on conformed image")
        LOGGER.info("=" * 80)
        mask_path = subject_dir / "mri" / "mask.mgz"
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert device to device_id format for skullstripping
        if device == "auto":
            device_id = "auto"
        elif device == "cpu":
            device_id = -1
        else:
            # Extract GPU index from "cuda:0" format
            device_id = int(device.split(":")[-1]) if ":" in device else 0
        
        skullstripping_config = {
            'atlas': atlas_name,
            'batch_size': batch_size,
            'threads': threads if threads > 0 else 1,
        }
        # Only add preprocessing params if not defaults
        if vox_size != "min":
            skullstripping_config['vox_size'] = vox_size
        if orientation != "lia":
            skullstripping_config['orientation'] = orientation
        if image_size is not True:
            skullstripping_config['image_size'] = image_size
        if conform_to_1mm_threshold != 0.95:
            skullstripping_config['conform_to_1mm_threshold'] = conform_to_1mm_threshold
        
        skullstripping(
            input_image=str(orig_mgz),
            modal="anat",  # Always anat for T1w
            output_path=str(mask_path),
            device_id=device_id,
            logger=LOGGER,
            config=skullstripping_config
        )
        LOGGER.info(f"Brain mask saved: {mask_path}")

        # Step 3: Run segmentation on conformed image
        LOGGER.info("=" * 80)
        LOGGER.info("Step 3: Running segmentation on conformed image")
        LOGGER.info("=" * 80)
        
        # Create temporary directory for segmentation outputs
        import tempfile
        temp_seg_dir = Path(tempfile.mkdtemp(prefix="fastsurfer_seg_"))
        
        try:
            # Run segmentation (will create seg, mask, hemimask)
            seg_results = run_segmentation(
                input_image=str(orig_mgz),
                output_dir=temp_seg_dir,
                atlas_name=atlas_name,
                atlas_metadata=atlas_metadata,
                ckpt_ax=ckpt_ax,
                ckpt_cor=ckpt_cor,
                ckpt_sag=ckpt_sag,
                device=device,
                viewagg_device=viewagg_device,
                threads=threads if threads > 0 else 1,
                batch_size=batch_size,
                plane_weight_coronal=plane_weight_coronal,
                plane_weight_axial=plane_weight_axial,
                plane_weight_sagittal=plane_weight_sagittal,
                fix_wm_islands=not skip_wm_correction,
                resample_to_native=False,  # Keep in conformed space for FS
            )
            
            # Step 4: Reorganize outputs to FS structure
            LOGGER.info("=" * 80)
            LOGGER.info("Step 4: Reorganizing outputs to FreeSurfer structure")
            LOGGER.info("=" * 80)
            
            mri_dir = subject_dir / "mri"
            mri_dir.mkdir(parents=True, exist_ok=True)
            
            # Move segmentation to FS structure
            seg_file = mri_dir / pred_name
            seg_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seg_results['segmentation'], seg_file)
            LOGGER.info(f"Segmentation saved: {seg_file}")
            
            # Copy mask (overwrite the one from skullstripping with the one from segmentation)
            shutil.copy2(seg_results['mask'], mask_path)
            LOGGER.info(f"Brain mask saved: {mask_path}")
            
            # Copy hemisphere mask if available
            if 'hemimask' in seg_results:
                hemi_mask_path = mri_dir / "mask_hemi.mgz"
                shutil.copy2(seg_results['hemimask'], hemi_mask_path)
                LOGGER.info(f"Hemisphere mask saved: {hemi_mask_path}")
            
            # Get LUT path for aseg creation
            fastsurfercnn_dir = Path(__file__).resolve().parent.parent
            atlas_dir = fastsurfercnn_dir / f"atlas/atlas-{atlas_name}"
            lut_path = atlas_dir / f"{atlas_name}_ColorLUT.tsv"
            
            # Apply V1 WM fixing if requested
            if fixv1:
                LOGGER.info("=" * 80)
                LOGGER.info("Step 5: Applying V1 white matter correction")
                LOGGER.info("=" * 80)
                apply_v1_wm_fixing(
                    seg_file=seg_file,
                    output_dir=subject_dir,
                    lut_path=lut_path,
                    tpl_t1w=tpl_t1w,
                    tpl_wm=tpl_wm,
                )

            # Create aseg
            LOGGER.info("=" * 80)
            LOGGER.info("Step 6: Creating aseg file")
            LOGGER.info("=" * 80)
            create_aseg(
                seg_file=seg_file,
                output_dir=subject_dir,
                lut_path=lut_path,
            )

            # Run QC statistics
            LOGGER.info("Computing segmentation volume statistics...")
            conformed_img = nib.load(orig_mgz)
            pred_img = nib.load(seg_file)
            pred_data = np.asarray(pred_img.dataobj)
            seg_voxvol = np.prod(conformed_img.header.get_zooms())
            check_volume(pred_data, seg_voxvol)
            
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_seg_dir)
                LOGGER.debug(f"Cleaned up temporary directory: {temp_seg_dir}")
            except Exception as e:
                LOGGER.warning(f"Could not clean up temporary directory {temp_seg_dir}: {e}")
            
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

