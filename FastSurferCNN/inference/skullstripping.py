# Copyright 2024 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
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
Skullstripping interface for FastSurferCNN.

This module provides a simple interface for brain mask generation using FastSurferCNN,
compatible with the macacaMRINN skullstripping API.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Union, Any, Literal

from FastSurferCNN.inference.api import run_segmentation
from FastSurferCNN.inference.predictor_utils import setup_atlas_from_checkpoints

logger = logging.getLogger(__name__)


def _find_checkpoints(
    base_dir: Path,
    modality: str,
    atlas: Optional[str] = None,
    model_type: str = "seg"
) -> Dict[str, Optional[Path]]:
    """
    Find checkpoint files for a given modality.
    
    Supports naming conventions:
    - For segmentation models: {modality}_seg-{atlas}_{plane}.pkl (e.g., T1w_seg-ARM2_axial.pkl)
    - For brain mask models: {modality}_brainmask_{plane}.pkl (e.g., T1w_brainmask_axial.pkl)
    
    If atlas is not provided, tries to find any matching checkpoints.
    
    Parameters
    ----------
    base_dir : Path
        Base directory containing pretrained_model folder
    modality : str
        Modality name ('T1w' for anat, 'EPI' for func)
    atlas : str, optional
        Atlas name (e.g., 'ARM2', 'ARM3'). If None, tries to find any matching checkpoints.
    model_type : str
        Type of model: 'seg' for segmentation models, 'brainmask' for brain mask models (default: 'seg')
        
    Returns
    -------
    dict
        Dictionary with keys 'axial', 'coronal', 'sagittal' and Path values (or None if not found)
    """
    pretrained_dir = base_dir / "pretrained_model"
    
    if not pretrained_dir.exists():
        return {"axial": None, "coronal": None, "sagittal": None}
    
    checkpoints = {"axial": None, "coronal": None, "sagittal": None}
    
    if model_type == "seg":
        # Segmentation model format: {modality}_seg-{atlas}_{plane}.pkl
        if atlas:
            for plane in ["axial", "coronal", "sagittal"]:
                ckpt_name = f"{modality}_seg-{atlas}_{plane}.pkl"
                ckpt_path = pretrained_dir / ckpt_name
                if ckpt_path.exists():
                    checkpoints[plane] = ckpt_path
                    logger.debug(f"Found checkpoint: {ckpt_name}")
        
        # If not all found with atlas, try without atlas (wildcard search)
        if not all(checkpoints.values()):
            for plane in ["axial", "coronal", "sagittal"]:
                if checkpoints[plane] is None:
                    pattern = f"{modality}_seg-*_{plane}.pkl"
                    matches = list(pretrained_dir.glob(pattern))
                    if matches:
                        checkpoints[plane] = matches[0]  # Use first match
                        logger.debug(f"Found checkpoint (auto-detected): {matches[0].name}")
    
    elif model_type == "brainmask":
        # Brain mask model format: {modality}_brainmask_{plane}.pkl
        for plane in ["axial", "coronal", "sagittal"]:
            ckpt_name = f"{modality}_brainmask_{plane}.pkl"
            ckpt_path = pretrained_dir / ckpt_name
            if ckpt_path.exists():
                checkpoints[plane] = ckpt_path
                logger.debug(f"Found checkpoint: {ckpt_name}")
    
    return checkpoints


def _extract_atlas_from_checkpoint(ckpt_path: Path) -> Optional[str]:
    """
    Extract atlas name from a checkpoint file.
    
    Parameters
    ----------
    ckpt_path : Path
        Path to checkpoint file
        
    Returns
    -------
    str, None
        Atlas name if found, None otherwise
    """
    try:
        from FastSurferCNN.utils.checkpoint import extract_atlas_metadata
        metadata = extract_atlas_metadata(ckpt_path)
        if metadata:
            return metadata.get("atlas_name")
    except Exception as e:
        logger.debug(f"Could not extract atlas from checkpoint {ckpt_path}: {e}")
    return None


def skullstripping(
    input_image: Union[str, Path],
    modal: str,
    output_dir: Union[str, Path],
    device_id: Union[int, str] = 'auto',
    logger: Optional[logging.Logger] = None,
    config: Optional[Dict[str, Any]] = None,
    output_data_format: Literal["mgz", "nifti"] = "nifti",
    enable_crop_2round: bool = False,
) -> Dict[str, str]:
    """
    Perform skullstripping using FastSurferCNN segmentation model.
    
    This function provides the same interface as the macacaMRINN skullstripping API
    but uses FastSurferCNN internally for brain mask generation.
    
    The function implements an efficient "input space → model space → input space" workflow:
    1. Runs FastSurferCNN segmentation on the input image (in model space)
    2. Resamples segmentation back to native input space (in-memory, single operation)
    3. Creates brain mask and hemisphere mask from the resampled segmentation
    4. Saves all outputs to the output directory (all in native input space)
    
    All outputs are automatically in the same space as the input image, providing
    a seamless user experience without manual resampling.
    
    Args:
        input_image: Path to the input image (T1w, EPI, etc.)
        modal: 'anat' or 'func' (modality)
        output_dir: Directory to save all output files (segmentation, mask, hemimask)
        device_id: GPU device to use ('auto', -1 for CPU, or specific GPU index)
        logger: Logger instance (optional)
        config: Model configuration (optional)
            - 'atlas': Atlas name (e.g., 'ARM2', 'ARM3'). If not provided, auto-detected from checkpoints
            - 'batch_size': Batch size for inference (default: 1)
            - 'threads': Number of threads for CPU operations (default: 1)
            - 'base_dir': Base directory for pretrained_model (default: FastSurferCNN root)
        output_data_format: {"mgz", "nifti"}, default="nifti"
            Output file format. "mgz" saves as .mgz (MGH format), "nifti" saves as .nii.gz (NIfTI format).
        enable_crop_2round: bool, default=False
            If True, enable two-pass refinement: after first pass, if brain occupies < 20% of FOV
            and image dimension > model height, crop image to brain region and run second pass.
            First-pass outputs are moved to output_dir/pass_1/, and cropped input is saved as
            output_dir/input_cropped.{ext}. Final outputs are in cropped image's native space.
            
        Note: Preprocessing parameters (vox_size, orientation, image_size)
        are automatically read from checkpoint metadata (required), ensuring consistency
        with the training configuration.
        
    Returns:
        Dictionary with output file paths:
        - 'brain_mask': Path to the generated brain mask (binary, values 0 or 1)
        - 'segmentation': Path to the segmentation file (optional)
        - 'hemimask': Path to the hemisphere mask file (optional)
        - 'input_image': Path to the input image
        
    Raises:
        FileNotFoundError: If input image doesn't exist
        RuntimeError: If skullstripping fails
        ValueError: If modality is invalid or no checkpoints found
    """
    
    # Setup logger if not provided
    if logger is None:
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    
    logger.info(f"Starting skullstripping for {modal} modality using FastSurferCNN")
    
    # Validate inputs
    input_image = Path(input_image)
    if not input_image.exists():
        logger.error(f"Input image not found: {input_image}")
        raise FileNotFoundError(f"Input image not found: {input_image}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if modal not in ['anat', 'func']:
        logger.error(f"Invalid modality: {modal}. Must be 'anat' or 'func'")
        raise ValueError(f"Invalid modality: {modal}. Must be 'anat' or 'func'")

    # Map modality to checkpoint naming
    modality_map = {
        'anat': 'T1w',
        'func': 'EPI'
    }
    modality_name = modality_map[modal]
    
    # Get configuration
    if config is None:
        config = {}
    
    # Determine base directory for checkpoints
    from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT
    base_dir = config.get('base_dir', FASTSURFER_ROOT)
    base_dir = Path(base_dir)
    
    # Get atlas name from config or try to auto-detect
    atlas_name = config.get('atlas')
    
    # Find checkpoints (using segmentation models for skullstripping)
    logger.info(f"Looking for checkpoints in {base_dir / 'pretrained_model'}")
    checkpoints = _find_checkpoints(base_dir, modality_name, atlas_name, model_type="seg")
    
    # If no checkpoints found with atlas, try to find any and extract atlas
    if not any(checkpoints.values()):
        # Try without atlas constraint
        checkpoints = _find_checkpoints(base_dir, modality_name, None, model_type="seg")
        
        # Try to extract atlas from found checkpoints
        # Check all found checkpoints to ensure they're from the same atlas
        extracted_atlases = set()
        for ckpt_path in checkpoints.values():
            if ckpt_path is not None:
                extracted_atlas = _extract_atlas_from_checkpoint(ckpt_path)
                if extracted_atlas:
                    extracted_atlases.add(extracted_atlas)
        
        if extracted_atlases:
            if len(extracted_atlases) > 1:
                logger.warning(
                    f"Found checkpoints from multiple atlases: {extracted_atlases}. "
                    f"Using first atlas: {sorted(extracted_atlases)[0]}"
                )
            atlas_name = sorted(extracted_atlases)[0]
            logger.info(f"Auto-detected atlas: {atlas_name}")
            # Re-find checkpoints with known atlas
            checkpoints = _find_checkpoints(
                base_dir, modality_name, atlas_name, model_type="seg"
            )
        else:
            # If we can't extract atlas but found checkpoints, proceed with what we have
            logger.warning(
                "Could not extract atlas from checkpoints. "
                "Proceeding with found checkpoints (atlas may be inconsistent)."
            )
    
    # Validate that at least one checkpoint is found
    found_planes = [plane for plane, ckpt in checkpoints.items() if ckpt is not None]
    if not found_planes:
        raise ValueError(
            f"No checkpoints found for {modality_name} modality. "
            f"Expected files like: {modality_name}_seg-*_{{axial,coronal,sagittal}}.pkl "
            f"in {base_dir / 'pretrained_model'}"
        )
    
    logger.info(f"Found checkpoints for planes: {', '.join(found_planes)}")
    
    # Extract atlas metadata from checkpoints
    try:
        atlas_name, atlas_metadata = setup_atlas_from_checkpoints(
            ckpt_ax=checkpoints.get('axial'),
            ckpt_cor=checkpoints.get('coronal'),
            ckpt_sag=checkpoints.get('sagittal')
        )
        logger.info(f"Using atlas: {atlas_name}")
    except Exception as e:
        logger.warning(f"Could not extract atlas metadata: {e}")
        # Fallback: use first checkpoint to get atlas
        first_ckpt = next(ckpt for ckpt in checkpoints.values() if ckpt is not None)
        atlas_name = _extract_atlas_from_checkpoint(first_ckpt) or "ARM2"
        atlas_metadata = None
        logger.warning(f"Using fallback atlas: {atlas_name}")
    
    # Convert device_id to device string
    if device_id == 'auto':
        device_str = 'auto'
    elif device_id == -1:
        device_str = 'cpu'
    else:
        device_str = f'cuda:{device_id}' if isinstance(device_id, int) else str(device_id)
    
    try:
        # Run segmentation using the high-level API
        # This will create segmentation, mask, and hemimask
        logger.info(f"Running segmentation on {input_image}")
        seg_results = run_segmentation(
            input_image=input_image,
            output_dir=output_dir,
            atlas_name=atlas_name,
            atlas_metadata=atlas_metadata,
            ckpt_ax=checkpoints.get('axial'),
            ckpt_cor=checkpoints.get('coronal'),
            ckpt_sag=checkpoints.get('sagittal'),
            device=device_str,
            viewagg_device=device_str,
            threads=config.get('threads', 1),
            batch_size=config.get('batch_size', 1),
            fix_wm_islands=False,  # Not needed for skullstripping
            output_data_format=output_data_format,
            enable_crop_2round=enable_crop_2round,
        )
        
        logger.info("Skullstripping completed successfully")
        logger.info(f"Output files saved to: {output_dir}")
        logger.info(f"  - Segmentation: {seg_results.get('segmentation')}")
        logger.info(f"  - Brain mask: {seg_results.get('mask')}")
        if 'hemimask' in seg_results:
            logger.info(f"  - Hemisphere mask: {seg_results.get('hemimask')}")
        
        # Return all output file paths
        result = {
            'brain_mask': str(seg_results['mask']),
            'input_image': str(input_image)
        }
        if 'segmentation' in seg_results:
            result['segmentation'] = str(seg_results['segmentation'])
        if 'hemimask' in seg_results:
            result['hemimask'] = str(seg_results['hemimask'])
        
        return result
        
    except Exception as e:
        logger.error(f"Skullstripping failed: {str(e)}")
        raise RuntimeError(f"Skullstripping failed: {str(e)}") from e

