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
from FastSurferCNN.utils.checkpoint import extract_atlas_metadata, is_binary_checkpoint
from FastSurferCNN.utils.constants import FASTSURFER_ROOT

logger = logging.getLogger(__name__)


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
        metadata = extract_atlas_metadata(ckpt_path)
        if metadata:
            return metadata.get("atlas_name")
    except Exception as e:
        logger.debug(f"Could not extract atlas from checkpoint {ckpt_path}: {e}")
    return None


def skullstrip_fastsurfercnn(
    input_image: Union[str, Path],
    modal: str,
    output_dir: Union[str, Path],
    device_id: Union[int, str] = 'auto',
    logger: Optional[logging.Logger] = None,
    config: Optional[Dict[str, Any]] = None,
    output_data_format: Literal["mgz", "nifti"] = "nifti",
    enable_crop_2round: bool = False,
    plane_weight_coronal: Optional[float] = None,
    plane_weight_axial: Optional[float] = None,
    plane_weight_sagittal: Optional[float] = None,
    use_mixed_model: bool = False,
) -> Dict[str, str]:
    """
    Perform skullstripping using FastSurferCNN segmentation model.
    
    This function uses FastSurferCNN internally for brain mask generation.
    
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
        plane_weight_coronal: float, optional
            Weight for coronal plane in multi-view prediction. If None, uses default from config.
            Can also be specified in config dict as 'plane_weight_coronal'.
        plane_weight_axial: float, optional
            Weight for axial plane in multi-view prediction. If None, uses default from config.
            Can also be specified in config dict as 'plane_weight_axial'.
        plane_weight_sagittal: float, optional
            Weight for sagittal plane in multi-view prediction. If None, uses default from config.
            Can also be specified in config dict as 'plane_weight_sagittal'.
        use_mixed_model: bool, default=False
            If True, use a single mixed-plane model checkpoint for all 3 planes instead of
            separate plane-specific checkpoints. The mixed checkpoint should be named
            {modal}_seg-{atlas}_mixed.pkl (e.g., EPI_seg-brainmask_mixed.pkl).
            When using mixed model, the same checkpoint is used for all 3 planes, and
            each plane is evaluated separately with the specified plane weights.
            
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
    
    logger.info(f"Skullstripping (FastSurferCNN): starting for {modal} modality")
    
    # Validate inputs
    input_image = Path(input_image)
    if not input_image.exists():
        logger.error(f"Skullstripping (FastSurferCNN): input image not found: {input_image}")
        raise FileNotFoundError(f"Input image not found: {input_image}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if modal not in ['anat', 'func']:
        logger.error(f"Skullstripping (FastSurferCNN): invalid modality={modal}, must be 'anat' or 'func'")
        raise ValueError(f"Invalid modality: {modal}. Must be 'anat' or 'func'")
    
    # Get configuration
    if config is None:
        config = {}
    
    # Get plane weights from direct parameters or config (direct parameters take precedence)
    plane_weight_coronal = plane_weight_coronal if plane_weight_coronal is not None else config.get('plane_weight_coronal')
    plane_weight_axial = plane_weight_axial if plane_weight_axial is not None else config.get('plane_weight_axial')
    plane_weight_sagittal = plane_weight_sagittal if plane_weight_sagittal is not None else config.get('plane_weight_sagittal')
        
    # Determine base directory for checkpoints
    base_dir = config.get('base_dir', FASTSURFER_ROOT / "FastSurferCNN")
    base_dir = Path(base_dir)
    pretrained_dir = base_dir / "pretrained_model"

    # Get checkpoint template for this modality
    # Hardcoded checkpoint mapping: {modality}_seg-{atlas}_planexxx.pkl
    # Replace 'planexxx' with actual plane name (axial, coronal, sagittal) or 'mixed'
    checkpoint_map = {
        'anat': 'T1w_seg-ARM2_planexxx.pkl',
        'func': 'EPI_seg-brainmask_planexxx.pkl'
    }
    ckpt_template = checkpoint_map[modal]

    if use_mixed_model:
        # Mixed-plane model: look for single mixed checkpoint
        ckpt_name = ckpt_template.replace('planexxx', 'mixed')
        mixed_ckpt_path = pretrained_dir / ckpt_name
        
        if not mixed_ckpt_path.exists():
            raise ValueError(
                f"Mixed-plane checkpoint not found for {modal} modality. "
                f"Expected file: {ckpt_name} in {pretrained_dir}"
            )
        
        logger.info(f"Checkpoint: using mixed-plane model {ckpt_name}")
        # Use the same mixed checkpoint for all 3 planes
        checkpoints = {
            'axial': mixed_ckpt_path,
            'coronal': mixed_ckpt_path,
            'sagittal': mixed_ckpt_path,
        }
    else:
        # Separate plane models: look for individual plane checkpoints
        # Resolve checkpoint paths by replacing 'planexxx' with actual plane names
        checkpoints = {}
        for plane in ["axial", "coronal", "sagittal"]:
            ckpt_name = ckpt_template.replace('planexxx', plane)
            ckpt_path = pretrained_dir / ckpt_name
            if ckpt_path.exists():
                checkpoints[plane] = ckpt_path
                logger.debug(f"Checkpoint: found {ckpt_name}")
            else:
                checkpoints[plane] = None
                logger.warning(f"Checkpoint: not found {ckpt_path}")
        
        # Validate that at least one checkpoint is found
        found_planes = [plane for plane, ckpt in checkpoints.items() if ckpt is not None]
        if not found_planes:
            raise ValueError(
                f"No checkpoints found for {modal} modality. "
                f"Expected files like: {ckpt_template.replace('planexxx', '{plane}')} "
                f"in {pretrained_dir}"
            )
        
        logger.info(f"Checkpoint: found for planes={', '.join(found_planes)}")
    
    # Extract atlas metadata from checkpoints
    try:
        atlas_name, atlas_metadata = setup_atlas_from_checkpoints(
            ckpt_ax=checkpoints.get('axial'),
            ckpt_cor=checkpoints.get('coronal'),
            ckpt_sag=checkpoints.get('sagittal')
        )
        # Check if this is a binary model
        is_binary = atlas_metadata.get("is_binary_task", False)
        if is_binary:
            logger.info(f"Model: binary brain mask task detected (atlas_name={atlas_name}, num_classes={atlas_metadata.get('num_classes', 2)})")
        else:
            logger.info(f"Atlas: using {atlas_name} (num_classes={atlas_metadata.get('num_classes', 'unknown')})")
    except Exception as e:
        logger.warning(f"Atlas: could not extract metadata: {e}")
        # Fallback: determine binary from checkpoint
        first_ckpt = next(ckpt for ckpt in checkpoints.values() if ckpt is not None)
        
        is_binary, num_classes = is_binary_checkpoint(first_ckpt)
        
        if is_binary is True:
            # Binary model - doesn't need an atlas
            num_classes = num_classes or 2
            atlas_name = None
            atlas_metadata = {
                "is_binary_task": True,
                "atlas_name": None,  # Binary models don't need atlas
                "num_classes": num_classes,
                "plane": "",  # Not specific to a single plane (multi-plane model)
            }
            logger.info(f"Model: detected binary model (num_classes={num_classes}, no atlas required)")
        else:
            # Multi-class model or cannot determine - try to extract or use default
            atlas_name = _extract_atlas_from_checkpoint(first_ckpt)
            atlas_metadata = None
            logger.warning(f"Atlas: using fallback {atlas_name} (metadata will be auto-detected)")
    
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
        logger.info(f"Segmentation: running on {input_image}")
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
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
            output_data_format=output_data_format,
            enable_crop_2round=enable_crop_2round,
        )
        
        logger.info("Skullstripping (FastSurferCNN): completed successfully")
        logger.info(f"Output: files saved to {output_dir}")
        logger.info(f"Output: segmentation={seg_results.get('segmentation')}")
        logger.info(f"Output: brain_mask={seg_results.get('mask')}")
        if 'hemimask' in seg_results:
            logger.info(f"Output: hemisphere_mask={seg_results.get('hemimask')}")
        if 'input_cropped' in seg_results:
            logger.info(f"Output: input_cropped={seg_results.get('input_cropped')}")
        
        # Return all output file paths
        result = {
            'brain_mask': str(seg_results['mask']),
            'input_image': str(input_image)
        }
        if 'segmentation' in seg_results:
            result['segmentation'] = str(seg_results['segmentation'])
        if 'hemimask' in seg_results:
            result['hemimask'] = str(seg_results['hemimask'])
        if 'input_cropped' in seg_results:
            result['input_cropped'] = str(seg_results['input_cropped'])
        
        return result
        
    except Exception as e:
        logger.error(f"Skullstripping (FastSurferCNN): failed: {str(e)}")
        raise RuntimeError(f"Skullstripping (FastSurferCNN) failed: {str(e)}") from e

