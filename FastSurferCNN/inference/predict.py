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
This is the FastSurfer/predict.py script, the backbone for whole brain segmentation.

"""

# Standard library imports
import copy
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any, Literal

# Add parent directory to path for module imports
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent))

# Third-party imports
import nibabel as nib
import numpy as np
import torch
import yacs.config
from scipy import ndimage

# Local imports
from FastSurferCNN.atlas.atlas_manager import AtlasManager
from FastSurferCNN.data_loader import data_utils
from FastSurferCNN.data_loader.conform import (
    conform,
    is_conform,
    map_image,
    orientation_to_ornts,
    to_target_orientation,
)
from FastSurferCNN.inference.inference import Inference
from FastSurferCNN.postprocessing.postseg_utils import (
    create_hemisphere_masks,
    create_mask,
    flip_wm_islands_auto,
)
from FastSurferCNN.utils import Plane, logging
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.arg_types import vox_size as _vox_size
from FastSurferCNN.utils.checkpoint import (
    extract_atlas_metadata,
    extract_training_config,
    read_checkpoint_file,
)
from FastSurferCNN.utils.common import find_device
from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

# ============================================================================
# Module-level constants and variables
# ============================================================================

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"

# Brain mask creation parameters
MASK_DILATION_SIZE = 5  # Dilation kernel size for mask creation
MASK_EROSION_SIZE = 4   # Erosion kernel size for mask creation

# Two-pass refinement parameters
TWO_PASS_BRAIN_RATIO_THRESHOLD = 0.20  # Trigger refinement if brain occupies < 20% of FOV
TWO_PASS_CROP_MARGIN = 0.08  # 8% margin around brain bounding box

# ============================================================================
# Validation helpers
# ============================================================================

def validate_checkpoints(
    ckpt_ax: Path | None,
    ckpt_cor: Path | None,
    ckpt_sag: Path | None,
) -> None:
    """
    Validate that at least one checkpoint is provided.

    Parameters
    ----------
    ckpt_ax : Path, optional
        Checkpoint path for axial plane.
    ckpt_cor : Path, optional
        Checkpoint path for coronal plane.
    ckpt_sag : Path, optional
        Checkpoint path for sagittal plane.

    Raises
    ------
    ValueError
        If no checkpoints are provided.
    """
    if all(ckpt is None for ckpt in [ckpt_ax, ckpt_cor, ckpt_sag]):
        raise ValueError(
            "At least one checkpoint must be provided. "
            "Please specify --ckpt_ax, --ckpt_cor, and/or --ckpt_sag."
        )

# ============================================================================
# Processing functions
# ============================================================================

def setup_atlas_from_checkpoints(
    ckpt_ax: Path | None,
    ckpt_cor: Path | None,
    ckpt_sag: Path | None,
) -> tuple[str, dict]:
    """
    Extract and validate atlas metadata from checkpoint files.

    Parameters
    ----------
    ckpt_ax : Path, optional
        Path to checkpoint file for axial plane.
    ckpt_cor : Path, optional
        Path to checkpoint file for coronal plane.
    ckpt_sag : Path, optional
        Path to checkpoint file for sagittal plane.

    Returns
    -------
    tuple[str, dict]
        Atlas name and full atlas metadata dictionary.

    Raises
    ------
    RuntimeError
        If no atlas metadata found or checkpoints use different atlases.
    """
    LOGGER.info("Extracting atlas information from checkpoints...")

    # Try to extract atlas from each checkpoint (they should all be the same atlas)
    atlas_metadatas = {}
    plane_checkpoints = [
        ("axial", ckpt_ax),
        ("coronal", ckpt_cor),
        ("sagittal", ckpt_sag),
    ]

    for plane, ckpt_path in plane_checkpoints:
        if ckpt_path is not None:
            metadata = extract_atlas_metadata(ckpt_path)
            if metadata:
                atlas_metadatas[plane] = metadata
                LOGGER.info(
                    f"  {plane.capitalize():9s}: {metadata['atlas_name']} "
                    f"({metadata['num_classes']} classes)"
                )

    if not atlas_metadatas:
        raise RuntimeError(
            "Could not extract atlas metadata from any checkpoint. "
            "Please verify your checkpoint files are valid and contain atlas information."
        )

    # Validate that all checkpoints use the same atlas
    atlas_names = {meta["atlas_name"] for meta in atlas_metadatas.values()}
    if len(atlas_names) > 1:
        raise RuntimeError(
            f"Checkpoint atlas mismatch: {atlas_names}. "
            "All checkpoints must be trained on the same atlas."
        )

    # Use the atlas from any checkpoint (they're all the same)
    atlas_name = list(atlas_metadatas.values())[0]["atlas_name"]
    atlas_metadata = list(atlas_metadatas.values())[0]

    LOGGER.info(f"✓ Validated atlas: {atlas_name}")

    return atlas_name, atlas_metadata


def load_multiplane_configs(
    ckpt_ax: Path | None = None,
    ckpt_cor: Path | None = None,
    ckpt_sag: Path | None = None,
    batch_size: int = 1,
) -> tuple[
    yacs.config.CfgNode,
    yacs.config.CfgNode,
    yacs.config.CfgNode,
    yacs.config.CfgNode,
]:
    """
    Load training configurations from multiple plane checkpoints.

    This function loads the training configuration from up to 3 checkpoint
    files (one for each plane: axial, coronal, sagittal) for multi-view inference.

    Checkpoints contain the full training config, eliminating the need for
    separate config files during inference.

    Parameters
    ----------
    ckpt_ax : Path, optional
        The path to the axial checkpoint.
    ckpt_cor : Path, optional
        The path to the coronal checkpoint.
    ckpt_sag : Path, optional
        The path to the sagittal checkpoint.
    batch_size : int, default=1
        The batch size for the network.

    Returns
    -------
    tuple[yacs.config.CfgNode, ...]
        Configurations: (cfg_fin, cfg_cor, cfg_sag, cfg_ax)

    Raises
    ------
    RuntimeError
        If no valid configuration is found.
    """
    # Load all configs from checkpoints
    plane_configs = [
        ("coronal", ckpt_cor),
        ("sagittal", ckpt_sag),
        ("axial", ckpt_ax),
    ]

    cfgs = {}
    for plane_name, ckpt in plane_configs:
        if ckpt is not None:
            LOGGER.info(f"Loading {plane_name} config from checkpoint")
            cfgs[plane_name] = extract_training_config(ckpt, batch_size)
        else:
            cfgs[plane_name] = None

    cfg_cor = cfgs["coronal"]
    cfg_sag = cfgs["sagittal"]
    cfg_ax = cfgs["axial"]

    # Return the first non-None cfg as cfg_fin
    cfg_fin = next(
        (cfg for cfg in (cfg_cor, cfg_sag, cfg_ax) if cfg is not None),
        None,
    )
    if cfg_fin is None:
        raise RuntimeError(
            "No valid configuration passed! At least one checkpoint must be provided."
        )

    return (cfg_fin, cfg_cor, cfg_sag, cfg_ax)


def crop_image_to_brain_mask(
    image_path: Path | str,
    brain_mask_path: Path | str,
    margin: float = 0.1,
    save_path: Path | str | None = None,
) -> nib.analyze.SpatialImage:
    """
    Crop image to brain mask region with margin.
    
    Parameters
    ----------
    image_path : Path, str
        Path to input image to crop
    brain_mask_path : Path, str
        Path to brain mask image (binary mask, same shape as input image)
    margin : float, default=0.1
        Margin to add as percentage of brain bounding box size
    save_path : Path, str, optional
        If provided, save the cropped image as NIfTI to this path
        
    Returns
    -------
    nib.analyze.SpatialImage
        Cropped image with updated affine matrix
    """
    # Load image and mask from paths
    img = nib.load(image_path)
    img_data = np.asanyarray(img.dataobj)
    brain_mask_img = nib.load(brain_mask_path)
    brain_mask = np.asanyarray(brain_mask_img.dataobj)
    
    # Validate dimensions match
    if img_data.shape != brain_mask.shape:
        raise ValueError(
            f"Image shape {img_data.shape} does not match brain mask shape {brain_mask.shape}"
        )
    
    # Check if brain mask has any non-zero values
    if np.all(brain_mask == 0):
        raise ValueError("Brain mask is empty (all zeros). Cannot determine crop region.")
    
    # Find bounding box of brain area
    brain_area = np.where(brain_mask != 0)
    if len(brain_area) == 0 or len(brain_area[0]) == 0:
        raise ValueError("Brain mask has no non-zero voxels. Cannot determine crop region.")
    
    # Get number of dimensions from np.where result (should match mask dimensions)
    n_dims = len(brain_area)
    mask_ndims = len(brain_mask.shape)
    
    if n_dims != mask_ndims:
        raise ValueError(
            f"Mismatch: np.where returned {n_dims} dimensions but mask has {mask_ndims} dimensions. "
            f"Mask shape: {brain_mask.shape}, brain_area length: {len(brain_area)}"
        )
    
    if n_dims < 2 or n_dims > 3:
        raise ValueError(f"Expected 2D or 3D brain mask, got {n_dims}D mask with shape {brain_mask.shape}")
    
    # Calculate bounding box for each dimension [min, max]
    # dim_range shape: (n_dims, 2) where dim_range[i, 0] = min, dim_range[i, 1] = max for dimension i
    dim_range = np.array([[np.min(brain_area[i]), np.max(brain_area[i])] for i in range(n_dims)])
    dim_length = dim_range[:, 1] - dim_range[:, 0] + 1  # +1 because range is inclusive
    
    # Add margin to the brain area
    margin_pixels = (margin * dim_length).astype(int)
    dim_range[:, 0] = dim_range[:, 0] - margin_pixels
    dim_range[:, 1] = dim_range[:, 1] + margin_pixels
    
    # Clamp to image boundaries
    for i in range(n_dims):
        if dim_range[i, 0] < 0:
            dim_range[i, 0] = 0
        if dim_range[i, 1] >= img_data.shape[i]:
            dim_range[i, 1] = img_data.shape[i] - 1
    
    # Create slices based on number of dimensions
    if n_dims == 3:
        xmin, xmax = int(dim_range[0, 0]), int(dim_range[0, 1]) + 1
        ymin, ymax = int(dim_range[1, 0]), int(dim_range[1, 1]) + 1
        zmin, zmax = int(dim_range[2, 0]), int(dim_range[2, 1]) + 1
        crop_slices = (slice(xmin, xmax), slice(ymin, ymax), slice(zmin, zmax))
    elif n_dims == 2:
        xmin, xmax = int(dim_range[0, 0]), int(dim_range[0, 1]) + 1
        ymin, ymax = int(dim_range[1, 0]), int(dim_range[1, 1]) + 1
        crop_slices = (slice(xmin, xmax), slice(ymin, ymax))
    else:
        raise ValueError(f"Unsupported number of dimensions: {n_dims}")
    
    # Crop the image data
    cropped_data = img_data[crop_slices]
    
    # Update affine to account for cropping (translate origin)
    cropped_affine = img.affine.copy()
    # Calculate translation in world coordinates
    if n_dims == 3:
        origin_voxel = np.array([xmin, ymin, zmin, 1.0])
    else:
        origin_voxel = np.array([xmin, ymin, 0, 1.0])
    origin_world = img.affine @ origin_voxel
    cropped_affine[:3, 3] = origin_world[:3]
    
    # Create new image with cropped data and updated affine
    cropped_img = nib.MGHImage(cropped_data, cropped_affine, img.header.copy())
    
    # Save as NIfTI if save_path is provided
    if save_path is not None:
        save_path = Path(save_path)
        # Ensure output directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use the dtype from the input image
        save_dtype = img_data.dtype
        cropped_data_save = cropped_data.astype(save_dtype)
        
        # Create NIfTI image with cropped affine and header
        cropped_nii = nib.Nifti1Image(cropped_data_save, cropped_affine, img.header.copy())
        # Update header data type
        cropped_nii.header.set_data_dtype(save_dtype)
        
        # Save the NIfTI file
        nib.save(cropped_nii, save_path)
    
    return cropped_img


def _should_apply_refinement(
    brain_mask: np.ndarray,
    orig_img: nib.analyze.SpatialImage,
    model_height: int,
) -> tuple[bool, float, int]:
    """
    Determine if two-pass refinement should be applied.
    
    Parameters
    ----------
    brain_mask : np.ndarray
        Binary brain mask
    orig_img : nib.analyze.SpatialImage
        Original image
    model_height : int
        Model height from checkpoint config
        
    Returns
    -------
    tuple[bool, float, int]
        (should_refine, brain_ratio, max_orig_dim)
        should_refine: True if refinement should be applied
        brain_ratio: Ratio of brain volume to total volume
        max_orig_dim: Maximum dimension of original image
    """
    brain_volume = np.sum(brain_mask > 0)
    total_volume = np.prod(brain_mask.shape)
    brain_ratio = brain_volume / total_volume
    
    orig_shape = orig_img.shape
    max_orig_dim = max(orig_shape)
    
    should_refine = (
        brain_ratio < TWO_PASS_BRAIN_RATIO_THRESHOLD
        and max_orig_dim > model_height
    )
    
    return should_refine, brain_ratio, max_orig_dim


# ============================================================================
# Main prediction class
# ============================================================================

class RunModelOnData:
    """
    Generic predictor for running multi-view segmentation on brain images.
    
    This class provides a generic interface for brain segmentation that works with
    any image format, not tied to FreeSurfer directory structures.
    
    **Key Feature: Automatic Input Space → Model Space → Input Space Workflow**
    
    The predictor automatically handles space transformations:
    1. Input images are conformed to model space for inference
    2. Predictions are computed in model space
    3. Outputs are automatically resampled back to match the original input space
    
    This provides a seamless UX: users feed images and get outputs in the same
    space as their inputs, without manual resampling.

    Attributes
    ----------
    vox_size : float, 'min'
        Voxel size for conforming images.
    current_plane : str
        Current plane being processed.
    models : Dict[str, Inference]
        Inference models for each plane.
    view_ops : Dict[str, Dict[str, Any]]
        View-specific operations and configurations.
    orientation : OrientationType
        Target orientation for conforming.
    conform_to_1mm_threshold : float, optional
        Threshold until which the image will be conformed to 1mm resolution.
    fix_wm_islands : bool
        Whether to apply white matter island correction.

    Methods
    -------
    __init__()
        Construct predictor object.
    get_prediction(image_f, img)
        Run inference and return prediction array (in model space).
    save_img(output_f, data, dtype, resample_to_native, interpolation)
        Save image with automatic native space resampling (pure Python).
    set_model(plane)
        Set the current model plane.
    get_num_classes()
        Get number of segmentation classes.
    """

    vox_size: float | Literal["min"]
    current_plane: Plane
    models: dict[Plane, Inference]
    view_ops: dict[Plane, dict[str, Any]]
    conform_to_1mm_threshold: float | None
    device: torch.device
    viewagg_device: torch.device
    orientation: OrientationType

    def __init__(
        self,
        atlas_name: str,
        atlas_metadata: dict | None = None,
        ckpt_ax: Path | None = None,
        ckpt_sag: Path | None = None,
        ckpt_cor: Path | None = None,
        device: str = "auto",
        viewagg_device: str = "auto",
        threads: int = 1,
        batch_size: int = 1,
        plane_weight_coronal: float | None = None,
        plane_weight_axial: float | None = None,
        plane_weight_sagittal: float | None = None,
        fix_wm_islands: bool = True,
    ):
        """
        Construct RunModelOnData object.

        Configs are automatically loaded from checkpoints - no separate config files needed!

        Parameters
        ----------
        atlas_name : str
            Name of the atlas (e.g., "ARM2", "ARM3"). This determines which LUT
            and label mappings to use.
        atlas_metadata : dict, optional
            Atlas metadata extracted from checkpoint. If provided, uses the
            dense_to_sparse mapping from the checkpoint (guarantees exact match
            with training). If None, derives mapping from atlas_name.
        ckpt_ax : Path, optional
            Path to checkpoint file for axial plane.
        ckpt_sag : Path, optional
            Path to checkpoint file for sagittal plane.
        ckpt_cor : Path, optional
            Path to checkpoint file for coronal plane.
        device : str, default="auto"
            Device to run inference on. Can be "auto", "cuda", or "cpu".
        viewagg_device : str, default="auto"
            Device to run view aggregation on. Can be "auto", "cuda", or "cpu".
        threads : int, default=1
            Number of threads for CPU operations.
        batch_size : int, default=1
            Batch size for inference.
        plane_weight_coronal : float, optional
            Weight for coronal plane in multi-view prediction.
        plane_weight_axial : float, optional
            Weight for axial plane in multi-view prediction.
        plane_weight_sagittal : float, optional
            Weight for sagittal plane in multi-view prediction.
        fix_wm_islands : bool, default=True
            Whether to apply WM island correction after segmentation. This fixes
            mislabeled disconnected WM regions by flipping them to the correct hemisphere.
            Enabled by default as it improves downstream processing (e.g., mri_cc performance).
        """
        self._threads = threads
        torch.set_num_threads(self._threads)
        self.fix_wm_islands = fix_wm_islands

        # Context for native space resampling
        self._input_master_path: Path | None = None
        self._input_native_img: nib.analyze.SpatialImage | None = None
        self._conformed_img: nib.analyze.SpatialImage | None = None
        self._conform_kwargs: dict = {}

        self.device = find_device(device)

        # Store plane weights for multi-view prediction
        self.plane_weights = {
            "coronal": plane_weight_coronal,
            "axial": plane_weight_axial,
            "sagittal": plane_weight_sagittal,
        }

        if self.device.type == "cpu" and viewagg_device in ("auto", "cpu"):
            self.viewagg_device = self.device
        else:
            # Check if GPU is big enough to run view aggregation on it
            # (this currently takes the memory of the passed device)
            self.viewagg_device = find_device(
                viewagg_device,
                flag_name="viewagg_device",
                min_memory=4 * (2**30),
                default_cuda_device=self.device,
            )

        LOGGER.info(f"Running view aggregation on {self.viewagg_device}")

        # Initialize atlas and LUT
        LOGGER.info(f"Initializing with atlas: {atlas_name}")

        fastsurfercnn_dir = Path(__file__).resolve().parent.parent
        atlas_dir = fastsurfercnn_dir / f"atlas/atlas-{atlas_name}"
        lut_path = atlas_dir / f"{atlas_name}_ColorLUT.tsv"

        if not lut_path.exists():
            raise ValueError(
                f"ColorLUT not found for atlas '{atlas_name}' at {lut_path}. "
                "Please verify the atlas is installed correctly."
            )

        self.lut_path = lut_path
        self.lut = data_utils.read_classes_from_lut(lut_path)
        LOGGER.info(f"  Loaded LUT: {lut_path.name}")

        # Use the EXACT same dense-to-sparse mapping as training
        if (
            atlas_metadata
            and atlas_metadata.get("dense_to_sparse_mapping") is not None
        ):
            # Use the exact mapping from checkpoint (gold standard)
            self.labels = atlas_metadata["dense_to_sparse_mapping"]
            self.torch_labels = torch.from_numpy(self.labels)
            LOGGER.info(
                f"  Label mapping: from checkpoint ({len(self.labels)} classes)"
            )
        else:
            # Fallback: derive from AtlasManager
            try:
                atlas_manager = AtlasManager(atlas_name, atlas_dir=atlas_dir)
                self.labels = atlas_manager.get_dense_to_sparse_mapping()
                self.torch_labels = torch.from_numpy(self.labels)
                LOGGER.info(
                    f"  Label mapping: from AtlasManager ({len(self.labels)} classes)"
                )
                LOGGER.warning(
                    "  Checkpoint metadata not available - using AtlasManager fallback"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialize label mapping for atlas '{atlas_name}': {e}. "
                    "Please verify your atlas installation is complete."
                ) from e
        
        self.cfg_fin, cfg_cor, cfg_sag, cfg_ax = load_multiplane_configs(
            ckpt_ax=ckpt_ax,
            ckpt_cor=ckpt_cor,
            ckpt_sag=ckpt_sag,
            batch_size=batch_size,
        )

        # The order in this dictionary dictates the order in the view aggregation
        self.view_ops = {
            "coronal": {"cfg": cfg_cor, "ckpt": ckpt_cor},
            "sagittal": {"cfg": cfg_sag, "ckpt": ckpt_sag},
            "axial": {"cfg": cfg_ax, "ckpt": ckpt_ax},
        }

        # Dynamically determine num_classes from the maximum across all plane configs
        # This allows support for different atlases (79 for FreeSurfer, 149 for ARM3 monkey)
        # Sagittal may have fewer classes due to hemisphere merging, but view aggregation
        # expands it back to the full label space
        # Filter out None configs when calculating num_classes
        valid_configs = [
            view["cfg"]
            for view in self.view_ops.values()
            if view["cfg"] is not None
        ]
        if not valid_configs:
            raise RuntimeError(
                "No valid plane configurations found. "
                "At least one checkpoint must be provided."
            )
        self.num_classes = max(cfg.MODEL.NUM_CLASSES for cfg in valid_configs)

        self.models = {}
        for plane, view in self.view_ops.items():
            if all(view[key] is not None for key in ("cfg", "ckpt")):
                # Skip loading model if plane weight is 0 (waste of resources)
                plane_weight = self.plane_weights[plane]
                if plane_weight is not None and plane_weight == 0:
                    LOGGER.info(
                        f"Skipping {plane} model loading (plane weight is 0)"
                    )
                    continue

                # Update config with plane weights if provided
                cfg = view["cfg"]
                # Use explicit None check to allow 0 as a valid weight
                if self.plane_weights["coronal"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.CORONAL = (
                        self.plane_weights["coronal"]
                    )
                if self.plane_weights["axial"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.AXIAL = (
                        self.plane_weights["axial"]
                    )
                if self.plane_weights["sagittal"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.SAGITTAL = (
                        self.plane_weights["sagittal"]
                    )

                self.models[plane] = Inference(
                    cfg, ckpt=view["ckpt"], device=self.device, lut=self.lut
                )

        # Load preprocessing parameters from checkpoint (required)
        preprocess_from_ckpt = self._extract_preprocessing_params(
            ckpt_cor or ckpt_sag or ckpt_ax
        )

        if not preprocess_from_ckpt:
            raise RuntimeError(
                "Preprocessing parameters not found in checkpoint metadata. "
                "Please ensure your checkpoint file contains preprocessing configuration "
                "in DATA.PREPROCESSING section."
            )

        # Extract required preprocessing parameters
        self.vox_size = preprocess_from_ckpt.get("VOX_SIZE")
        self.image_size = preprocess_from_ckpt.get("IMG_SIZE")
        self.orientation = preprocess_from_ckpt.get("ORIENTATION")
        self.conform_to_1mm_threshold = preprocess_from_ckpt.get(
            "THRESHOLD_1MM"
        )

        # Validate that all required parameters are present
        missing_params = []
        if self.vox_size is None:
            missing_params.append("VOX_SIZE")
        if self.image_size is None:
            missing_params.append("IMG_SIZE")
        if self.orientation is None:
            missing_params.append("ORIENTATION")
        if self.conform_to_1mm_threshold is None:
            missing_params.append("THRESHOLD_1MM")

        if missing_params:
            raise RuntimeError(
                f"Missing required preprocessing parameters in checkpoint: {missing_params}. "
                "Please ensure your checkpoint file contains complete preprocessing configuration."
            )

        # Convert vox_size if needed (it might be stored as string "min" or float)
        try:
            self.vox_size = _vox_size(self.vox_size)
        except (ValueError, TypeError):
            raise ValueError(
                f"Invalid vox_size value in checkpoint: '{self.vox_size}'. "
                "Must be a float between 0 and 1, or 'min'."
            ) from None

        LOGGER.info(
            f"  Preprocessing: from checkpoint "
            f"(vox_size={self.vox_size}, orientation={self.orientation})"
        )

    def _extract_preprocessing_params(
        self, checkpoint_path: Path | str | None
    ) -> dict | None:
        """
        Extract preprocessing parameters from checkpoint config.

        Reads the checkpoint and extracts preprocessing settings like voxel size,
        orientation, and image size thresholds.

        Parameters
        ----------
        checkpoint_path : Path, str, None
            Path to checkpoint file.

        Returns
        -------
        dict, None
            Preprocessing parameters dict from checkpoint config, or None if not available.
        """
        if not checkpoint_path:
            return None

        try:
            import yaml

            # Load checkpoint using shared helper
            checkpoint = read_checkpoint_file(checkpoint_path)

            # Check if checkpoint has config
            if "config" not in checkpoint:
                return None

            # Parse config (it's saved as YAML string)
            config_str = checkpoint["config"]
            config_dict = yaml.safe_load(config_str)

            # Extract preprocessing parameters
            if (
                "DATA" in config_dict
                and "PREPROCESSING" in config_dict["DATA"]
            ):
                return config_dict["DATA"]["PREPROCESSING"]

            return None

        except Exception as e:
            LOGGER.warning(
                f"Could not load preprocessing params from checkpoint: {e}"
            )
            return None
    
    def _should_resample(self) -> bool:
        """
        Check if resampling to native space is needed.

        Returns
        -------
        bool
            True if the input image was conformed and needs resampling back to native space.
        """
        if self._input_native_img is None or self._conformed_img is None:
            return False
        return not is_conform(
            self._input_native_img, **self._conform_kwargs, verbose=False
        )

    def _resample_to_native(
        self,
        data: np.ndarray,
        interpolation: Literal["nearest", "linear"] = "linear",
    ) -> np.ndarray:
        """
        Resample data array from conformed space to native space using pure Python.
        
        Uses scipy.ndimage affine_transform for in-memory resampling. Supports both
        MGH and NIfTI formats.

        Parameters
        ----------
        data : np.ndarray
            Image data in conformed space.
        interpolation : {"nearest", "linear"}, default="linear"
            Interpolation method. Use "nearest" for segmentation/labels.

        Returns
        -------
        np.ndarray
            Resampled data in native space.

        Raises
        ------
        ValueError
            If native image context is not available.
        """
        if self._input_native_img is None or self._conformed_img is None:
            raise ValueError(
                "Cannot resample: native image context not available. "
                "Call get_prediction() first to establish resampling context."
            )

        # Create image object for map_image (expects SpatialImage)
        conformed_data_img = nib.nifti1.Nifti1Image(
                data,
                self._conformed_img.affine,
                self._conformed_img.header
            )

        # Map from conformed space to native space
        order = 0 if interpolation == "nearest" else 1
        resampled_data = map_image(
            conformed_data_img,
            out_affine=self._input_native_img.affine,
            out_shape=self._input_native_img.shape,
            order=order,
        )

        return resampled_data

    def set_model(self, plane: Plane) -> None:
        """
        Set the current model for the specified plane.

        Parameters
        ----------
        plane : Plane
            The plane for which to set the current model.
        """
        self.current_plane = plane

    def get_prediction(
        self,
        image_f: str,
        img: nib.analyze.SpatialImage | None = None,
    ) -> np.ndarray:
        """
        Run and get prediction.

        Parameters
        ----------
        image_f : str
            Original image filename (used for logging/identification).
        img : nib.analyze.SpatialImage, optional
            Image object in native space. If None, will be loaded from image_f.
            Will be automatically conformed if needed, and context will be captured
            for automatic native space resampling in save_img().

        Returns
        -------
        np.ndarray
            Predicted classes.
        """
        # Load image if not provided
        if img is None:
            img = nib.load(image_f)

        # Store the native image and set up context for resampling
        conform_kwargs = {
            "threshold_1mm": self.conform_to_1mm_threshold,
            "vox_size": self.vox_size,
            "orientation": self.orientation,
            "img_size": self.image_size,
        }

        # Store input context for automatic resampling
        self._input_master_path = Path(image_f)
        self._input_native_img = img
        self._conform_kwargs = conform_kwargs

        # Conform image if needed
        if not is_conform(img, **conform_kwargs, verbose=True):
            LOGGER.info("Conforming image to standard space...")
            img = conform(img, **conform_kwargs)
        else:
            LOGGER.info("Image is already conformed")

        # Store conformed image for use as reference in save_img
        self._conformed_img = img

        # Extract data, zoom, and affine from image
        orig_data = np.asanyarray(img.dataobj)
        zoom = img.header.get_zooms()
        affine = img.affine

        kwargs = {
            "device": self.viewagg_device,
            "dtype": torch.float16,
            "requires_grad": False,
        }

        _zoom = np.asarray(zoom)
        if not np.allclose(_zoom, np.mean(zoom), atol=1e-4, rtol=1e-3):
            msg = (
                "FastSurfer support for anisotropic images is experimental, "
                "we detected the following voxel sizes"
            )
            LOGGER.warning(f"{msg}: {np.round(_zoom, decimals=4).tolist()}!")

        orig_in_lia, back_to_native = to_target_orientation(
            orig_data, affine, target_orientation="LIA"
        )
        shape = orig_in_lia.shape + (self.get_num_classes(),)
        _ornt_transform, _ = orientation_to_ornts(
            affine, target_orientation="LIA"
        )
        _zoom = _zoom[_ornt_transform[:, 0]]

        pred_prob = torch.zeros(shape, **kwargs)

        # Inference and view aggregation
        for plane, model in self.models.items():
            LOGGER.info(f"Run {plane} prediction")
            self.set_model(plane)
            # pred_prob is updated inplace to conserve memory
            pred_prob = model.run(
                pred_prob, image_f, orig_in_lia, _zoom, out=pred_prob
            )

        # Get hard predictions
        pred_classes = torch.argmax(pred_prob, 3)
        del pred_prob

        # Reorder from LIA to native
        pred_classes = back_to_native(pred_classes)

        # Map to FreeSurfer label space
        pred_classes = data_utils.map_label2aparc_aseg(
            pred_classes, self.labels
        )

        # Return numpy array
        pred_classes = pred_classes.cpu().numpy()

        # Apply FreeSurfer-specific post-processing only for FreeSurfer atlases
        if data_utils.is_freesurfer_lut(self.lut["ID"].values):
            LOGGER.info("Applying FreeSurfer-specific cortex label splitting")
            pred_classes = data_utils.split_cortex_labels(pred_classes)
        else:
            LOGGER.info("Skipping cortex label splitting (custom atlas)")

        # Apply WM island fixing (generic post-processing, enabled by default)
        if self.fix_wm_islands:
            LOGGER.info(
                "Applying WM island correction "
                "(flipping mislabeled disconnected WM regions)..."
            )
            pred_classes = flip_wm_islands_auto(
                pred_classes, lut_path=self.lut_path
            )
        else:
            LOGGER.info("Skipping WM island correction")

        return pred_classes

    def set_up_model_params(
        self,
        plane: Plane,
        cfg: "yacs.config.CfgNode",
        ckpt: "torch.Tensor",
    ) -> None:
        """
        Set up the model parameters from the configuration and checkpoint.

        Parameters
        ----------
        plane : Plane
            The plane for which to set up model parameters.
        cfg : yacs.config.CfgNode
            Configuration node for the model.
        ckpt : torch.Tensor
            Checkpoint tensor (note: this parameter type may be incorrect).
        """
        self.view_ops[plane]["cfg"] = cfg
        self.view_ops[plane]["ckpt"] = ckpt

    def get_num_classes(self) -> int:
        """
        Return the number of classes.

        Returns
        -------
        int
            The number of classes.
        """
        return self.num_classes

# ============================================================================
# High-level API functions
# ============================================================================

def _apply_two_pass_refinement(
    input_image: Path,
    output_dir: Path,
    file_ext: str,
    atlas_name: str,
    atlas_metadata: dict | None,
    ckpt_ax: Path | None,
    ckpt_sag: Path | None,
    ckpt_cor: Path | None,
    device: str,
    viewagg_device: str,
    threads: int,
    batch_size: int,
    plane_weight_coronal: float | None,
    plane_weight_axial: float | None,
    plane_weight_sagittal: float | None,
    fix_wm_islands: bool,
    output_data_format: Literal["mgz", "nifti"],
) -> bool:
    """
    Apply two-pass refinement: crop image and run fresh segmentation.
    
    This function moves first-pass outputs to pass_1/ directory, crops the 
    ORIGINAL input image using the brain mask, then runs a completely fresh
    segmentation on the cropped image. This avoids any state/affine issues
    from reusing the predictor.
    
    Parameters
    ----------
    input_image : Path
        Original input image path
    output_dir : Path
        Output directory
    file_ext : str
        File extension for output files
    atlas_name : str
        Name of the atlas
    atlas_metadata : dict, optional
        Atlas metadata from checkpoint
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Checkpoint paths for each plane
    device : str
        Device to run inference on
    viewagg_device : str
        Device to run view aggregation on
    threads : int
        Number of threads for CPU operations
    batch_size : int
        Batch size for inference
    plane_weight_coronal, plane_weight_axial, plane_weight_sagittal : float, optional
        Weights for multi-view prediction
    fix_wm_islands : bool
        Whether to apply WM island correction
    output_data_format : {"mgz", "nifti"}
        Output file format
        
    Returns
    -------
    bool
        True if refinement completed successfully, False if it failed
    """
    pass_1_dir = output_dir / "pass_1"
    pass_1_dir.mkdir(parents=True, exist_ok=True)
    
    LOGGER.info("Applying two-pass refinement...")
    LOGGER.info(f"  Moving first-pass outputs to {pass_1_dir.name}/")
    
    # Define first-pass files
    first_pass_files = {
        "segmentation": output_dir / f"segmentation{file_ext}",
        "mask": output_dir / f"mask{file_ext}",
    }
    
    # Check for hemimask
    hemi_mask_path = output_dir / f"mask_hemi{file_ext}"
    if hemi_mask_path.exists():
        first_pass_files["hemimask"] = hemi_mask_path
    
    try:
        # Step 1: Move first-pass outputs to pass_1 directory
        for key, src_path in first_pass_files.items():
            if src_path.exists():
                dst_path = pass_1_dir / src_path.name
                shutil.move(str(src_path), str(dst_path))
                LOGGER.info(f"  Moved {key}: {src_path.name}")
        
        # Step 2: Crop ORIGINAL input image using first-pass mask
        mask_path = pass_1_dir / f"mask{file_ext}"
        cropped_input_path = output_dir / f"input_cropped{file_ext}"
        
        LOGGER.info(f"  Cropping original input to brain region (margin={TWO_PASS_CROP_MARGIN*100:.0f}%)...")
        
        # Load original image to get its shape for logging
        orig_img = nib.load(input_image)
        
        cropped_img = crop_image_to_brain_mask(
            str(input_image),  # Crop the ORIGINAL input image
            str(mask_path),     # Using mask from first pass
            margin=TWO_PASS_CROP_MARGIN,
            save_path=cropped_input_path,
        )
        
        LOGGER.info(f"  ✓ Cropped: {orig_img.shape} → {cropped_img.shape}")
        LOGGER.info(f"  ✓ Space saved: {np.prod(orig_img.shape) / np.prod(cropped_img.shape):.1f}x reduction")
        LOGGER.info(f"  ✓ Saved cropped input: {cropped_input_path.name}")
        
        # Step 3: Run FRESH segmentation on cropped image (starting from scratch)
        LOGGER.info("  Running 2nd pass with fresh predictor on cropped image...")
        LOGGER.info("  (This runs the full pipeline from scratch - no state reuse)")
        
        run_segmentation(
            input_image=cropped_input_path,
            output_dir=output_dir,  # Outputs go back to main directory
            atlas_name=atlas_name,
            atlas_metadata=atlas_metadata,
            ckpt_ax=ckpt_ax,
            ckpt_sag=ckpt_sag,
            ckpt_cor=ckpt_cor,
            device=device,
            viewagg_device=viewagg_device,
            threads=threads,
            batch_size=batch_size,
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
            fix_wm_islands=fix_wm_islands,
            output_data_format=output_data_format,
            enable_crop_2round=False,  # Don't recurse!
        )
        
        LOGGER.info("  ✓ Two-pass refinement completed successfully")
        return True
        
    except Exception as e:
        LOGGER.error(f"  ✗ Two-pass refinement failed: {e}")
        LOGGER.debug(f"  Error details: {traceback.format_exc()}")
        LOGGER.warning("  Falling back to first-pass prediction")
        LOGGER.info(f"  First-pass outputs are available in {pass_1_dir.name}/")
        
        # Try to restore first-pass outputs to main directory
        try:
            LOGGER.info("  Restoring first-pass outputs to main directory...")
            for key, src_path in first_pass_files.items():
                dst_path = pass_1_dir / src_path.name
                if dst_path.exists():
                    shutil.copy(str(dst_path), str(src_path))
                    LOGGER.info(f"  Restored {key}: {src_path.name}")
        except Exception as restore_error:
            LOGGER.error(f"  Failed to restore first-pass outputs: {restore_error}")
        
        return False


def run_segmentation(
    input_image: str | Path,
    output_dir: str | Path,
    atlas_name: str,
    atlas_metadata: dict | None = None,
    ckpt_ax: Path | None = None,
    ckpt_sag: Path | None = None,
    ckpt_cor: Path | None = None,
    device: str = "auto",
    viewagg_device: str = "auto",
    threads: int = 1,
    batch_size: int = 1,
    plane_weight_coronal: float | None = None,
    plane_weight_axial: float | None = None,
    plane_weight_sagittal: float | None = None,
    fix_wm_islands: bool = True,
    output_data_format: Literal["mgz", "nifti"] = "nifti",
    enable_crop_2round: bool = False,
) -> dict[str, Path]:
    """
    Run segmentation and save outputs (segmentation, mask, hemimask) to output directory.
    
    This is a high-level convenience function that implements the automatic 
    "input space → model space → input space" workflow:
    1. Runs FastSurferCNN segmentation on the input image (in model space)
    2. Resamples segmentation back to native input space (in-memory, pure Python)
    3. Creates brain mask and hemisphere mask from the resampled segmentation
    4. Saves all outputs to the specified output directory (all in native space)
    
    All outputs are automatically in the same space as the input image.
    Uses pure Python resampling (no external tool dependencies).
    
    Parameters
    ----------
    input_image : str, Path
        Path to input image
    output_dir : str, Path
        Output directory where segmentation, mask, and hemimask will be saved
    atlas_name : str
        Name of the atlas (e.g., "ARM2", "ARM3")
    atlas_metadata : dict, optional
        Atlas metadata extracted from checkpoint
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Checkpoint paths for each plane
    device : str, default="auto"
        Device to run inference on
    viewagg_device : str, default="auto"
        Device to run view aggregation on
    threads : int, default=1
        Number of threads for CPU operations
    batch_size : int, default=1
        Batch size for inference
    plane_weight_coronal, plane_weight_axial, plane_weight_sagittal : float, optional
        Weights for multi-view prediction
    fix_wm_islands : bool, default=True
        Whether to apply WM island correction
    output_data_format : {"mgz", "nifti"}, default="nifti"
        Output file format. "mgz" saves as .mgz (MGH format), "nifti" saves as .nii.gz (NIfTI format).
        Resampling uses pure Python (in-memory), no external tools needed.
    enable_crop_2round : bool, default=False
        If True, enable two-pass refinement: after first pass, if brain occupies < 20% of FOV
        and image dimension > model height, crop the ORIGINAL input image to brain region 
        and run a completely fresh segmentation on it. First-pass outputs are moved to 
        output_dir/pass_1/, cropped input is saved as output_dir/input_cropped.{ext}, and 
        final outputs (from second pass) are saved to main output_dir in cropped image's native space.
        
    Note
    ----
    Preprocessing parameters (vox_size, orientation, image_size, conform_to_1mm_threshold)
    are automatically read from checkpoint metadata (required), ensuring consistency
    with the training configuration.
    
    Returns
    -------
    dict[str, Path]
        Dictionary with keys:
        - 'segmentation': Path to saved segmentation file
        - 'mask': Path to saved brain mask file
        - 'hemimask': Path to saved hemisphere mask file (if created)
        - 'input_cropped': Path to cropped input (if two-pass refinement was applied)
    """
    input_image = Path(input_image)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate checkpoints
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)

    # Initialize predictor
    # Preprocessing parameters (vox_size, orientation, image_size,
    # conform_to_1mm_threshold) are automatically read from checkpoint
    # metadata if available
    predictor = RunModelOnData(
        atlas_name=atlas_name,
        atlas_metadata=atlas_metadata,
        ckpt_ax=ckpt_ax,
        ckpt_sag=ckpt_sag,
        ckpt_cor=ckpt_cor,
        device=device,
        viewagg_device=viewagg_device,
        threads=threads,
        batch_size=batch_size,
        plane_weight_coronal=plane_weight_coronal,
        plane_weight_axial=plane_weight_axial,
        plane_weight_sagittal=plane_weight_sagittal,
        fix_wm_islands=fix_wm_islands,
    )

    # Run prediction (returns segmentation in model/conformed space)
    LOGGER.info(f"Running segmentation on {input_image}")
    pred_data = predictor.get_prediction(str(input_image))

    # Map output format to file extension
    format_to_ext = {"mgz": ".mgz", "nifti": ".nii.gz"}
    file_ext = format_to_ext[output_data_format]
    seg_path = output_dir / f"segmentation{file_ext}"
    seg_path.parent.mkdir(parents=True, exist_ok=True)

    # Always resample to native space
    if predictor._should_resample():
        LOGGER.info("Resampling segmentation to native space...")
        pred_data_final = predictor._resample_to_native(
            pred_data, interpolation="nearest"
        )
        LOGGER.info(f"Successfully resampled segmentation (shape: {pred_data_final.shape})")
        
        data_utils.save_image(
            predictor._input_native_img.header,
            predictor._input_native_img.affine,
            pred_data_final,
            seg_path,
            dtype=np.int16,
        )
    else:
        # Input was already conformed - save directly (still in native space)
        LOGGER.info("No resampling needed - input was already conformed")
        data_utils.save_image(
            predictor._conformed_img.header,
            predictor._conformed_img.affine,
            pred_data,
            seg_path,
            dtype=np.int16,
        )
        pred_data_final = pred_data

    # Create masks from the final segmentation
    LOGGER.info("Creating brain mask...")
    brain_mask = create_mask(
        copy.deepcopy(pred_data_final),
        MASK_DILATION_SIZE,
        MASK_EROSION_SIZE,
    )
    brain_mask = brain_mask.astype(np.uint8)

    LOGGER.info("Creating hemisphere mask...")
    try:
        hemi_mask = create_hemisphere_masks(
            brain_mask, pred_data_final, lut_path=predictor.lut_path
        )
    except Exception as e:
        LOGGER.warning(f"Could not create hemisphere mask: {e}")
        hemi_mask = None

    # Save mask and hemimask
    # Get reference image for header/affine (always use native if available)
    if predictor._should_resample():
        reference_img = predictor._input_native_img
    else:
        reference_img = predictor._conformed_img

    mask_path = output_dir / f"mask{file_ext}"
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving brain mask to {mask_path}")
    data_utils.save_image(
        reference_img.header,
        reference_img.affine,
        brain_mask,
        mask_path,
        dtype=np.uint8,
    )

    if hemi_mask is not None:
        hemi_mask_path = output_dir / f"mask_hemi{file_ext}"
        hemi_mask_path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Saving hemisphere mask to {hemi_mask_path}")
        data_utils.save_image(
            reference_img.header,
            reference_img.affine,
            hemi_mask,
            hemi_mask_path,
            dtype=np.uint8,
        )
    else:
        hemi_mask_path = None

    # Build result dictionary
    result = {
        "segmentation": seg_path,
        "mask": mask_path,
    }
    if hemi_mask_path is not None:
        result["hemimask"] = hemi_mask_path

    # Check if two-pass refinement is needed
    if enable_crop_2round:
        # Get model height from checkpoint config
        model_height = predictor.cfg_fin.MODEL.HEIGHT
        
        # Check if refinement should be applied
        should_refine, brain_ratio, max_orig_dim = _should_apply_refinement(
            brain_mask, reference_img, model_height
        )
        
        LOGGER.info(f"Checking two-pass refinement criteria...")
        LOGGER.info(f"  Brain occupancy: {brain_ratio*100:.1f}% of FOV")
        LOGGER.info(f"  Image dimensions: {reference_img.shape} (max: {max_orig_dim})")
        LOGGER.info(f"  Model height: {model_height}")
        
        if should_refine:
            LOGGER.info(
                f"  → Applying two-pass refinement "
                f"(brain < {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%, dim > {model_height})"
            )
            
            # Apply two-pass refinement (runs fresh segmentation on cropped image)
            refinement_applied = _apply_two_pass_refinement(
                input_image=input_image,
                output_dir=output_dir,
                file_ext=file_ext,
                atlas_name=atlas_name,
                atlas_metadata=atlas_metadata,
                ckpt_ax=ckpt_ax,
                ckpt_sag=ckpt_sag,
                ckpt_cor=ckpt_cor,
                device=device,
                viewagg_device=viewagg_device,
                threads=threads,
                batch_size=batch_size,
                plane_weight_coronal=plane_weight_coronal,
                plane_weight_axial=plane_weight_axial,
                plane_weight_sagittal=plane_weight_sagittal,
                fix_wm_islands=fix_wm_islands,
                output_data_format=output_data_format,
            )
            
            # If refinement succeeded, update result paths to reflect second-pass outputs
            # (which are already saved by the fresh run_segmentation call)
            if refinement_applied:
                LOGGER.info("  ✓ Second-pass outputs are now in main directory")
                # Update result dict to include cropped input
                result["input_cropped"] = output_dir / f"input_cropped{file_ext}"
        else:
            if brain_ratio >= TWO_PASS_BRAIN_RATIO_THRESHOLD:
                LOGGER.info(
                    f"  → Skipping refinement (brain occupancy >= {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%)"
                )
            else:
                LOGGER.info(
                    f"  → Skipping refinement (image dimension <= {model_height})"
                )

    return result

