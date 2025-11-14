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

# IMPORTS
import argparse
import copy
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

# Add parent directory to path for module imports
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent))

import nibabel as nib
import numpy as np
import torch
import yacs.config

import FastSurferCNN.postprocessing.step1_fix_v1_wm as fix_v1_wm
import FastSurferCNN.postprocessing.step2_reduce_to_aseg as rta
from FastSurferCNN.atlas.atlas_manager import AtlasManager
from FastSurferCNN.data_loader import data_utils as du
from FastSurferCNN.data_loader.conform import conform, is_conform, map_image, orientation_to_ornts, to_target_orientation
from FastSurferCNN.inference.inference import Inference
from FastSurferCNN.seg_statistics.quick_qc import check_volume
from FastSurferCNN.utils import PLANES, Plane, logging, parser_defaults
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.arg_types import vox_size as _vox_size
from FastSurferCNN.utils.checkpoint import get_checkpoints, load_checkpoint_config_defaults
from FastSurferCNN.utils.common import (
    SerialExecutor,
    SubjectDirectory,
    SubjectList,
    find_device,
    handle_cuda_memory_exception,
    pipeline,
)
from FastSurferCNN.utils.logging import setup_logging

##
# Global Variables
##
from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"

##
# Constants
##

# Two-pass refinement thresholds
TWO_PASS_BRAIN_RATIO_THRESHOLD = 0.20  # Trigger refinement if brain occupies < 20% of FOV
TWO_PASS_MAX_DIMENSION_THRESHOLD = 256  # Only refine if original image dimension > 256 voxels
TWO_PASS_CROP_MARGIN = 0.08  # 8% margin around brain bounding box

# Brain mask creation parameters
MASK_DILATION_SIZE = 5  # Dilation kernel size for mask creation
MASK_EROSION_SIZE = 4   # Erosion kernel size for mask creation

##
# ANTs-based backprojection utilities
##

def check_command_available(commands: str | list[str]) -> bool:
    """
    Check if command(s) are available in the system PATH.
    
    Parameters
    ----------
    commands : str or list[str]
        Single command or list of commands to check.
    
    Returns
    -------
    bool
        True if all commands are available, False otherwise.
    """
    from shutil import which
    
    if isinstance(commands, str):
        commands = [commands]
    
    return all(which(cmd) is not None for cmd in commands)


def check_ants_available() -> bool:
    """Check if ANTs is available in the system."""
    return check_command_available(["antsRegistration", "antsApplyTransforms"])


def check_mri_convert_available() -> bool:
    """Check if mri_convert (FreeSurfer) is available."""
    return check_command_available("mri_convert")


def check_macacamriprep_available() -> bool:
    """
    Check if macacaMRIprep is available for import.
    
    Returns
    -------
    bool
        True if macacaMRIprep can be imported, False otherwise.
    """
    try:
        from macacaMRIprep.operations.registration import ants_register, ants_apply_transforms
        return True
    except ImportError:
        # Try alternative import path (top-level re-export)
        try:
            from macacaMRIprep.operations import ants_register, ants_apply_transforms
            return True
        except ImportError as e:
            LOGGER.debug(f"macacaMRIprep import failed: {e}")
            return False


def convert_mgz_to_nifti(mgz_path: Path | str, nii_path: Path | str) -> None:
    """
    Convert MGZ file to NIfTI using mri_convert.
    
    Parameters
    ----------
    mgz_path : Path, str
        Path to input MGZ file.
    nii_path : Path, str
        Path to output NIfTI file.
    
    Raises
    ------
    RuntimeError
        If mri_convert is not available or conversion fails.
    """
    if not check_mri_convert_available():
        raise RuntimeError(
            "mri_convert (FreeSurfer) is required for backprojection but not found. "
            "Please ensure FreeSurfer is installed and in your PATH."
        )
    
    mgz_path = Path(mgz_path)
    nii_path = Path(nii_path)
    
    if not mgz_path.exists():
        raise FileNotFoundError(f"Input MGZ file not found: {mgz_path}")
    
    # Ensure output directory exists
    nii_path.parent.mkdir(parents=True, exist_ok=True)
    
    LOGGER.info(f"Converting {mgz_path.name} to {nii_path.name}...")
    result = subprocess.run(
        ["mri_convert", str(mgz_path), str(nii_path)],
        capture_output=True,
        text=True,
        check=True
    )
    
    if not nii_path.exists():
        raise RuntimeError(
            f"mri_convert failed to create {nii_path}. "
            f"stderr: {result.stderr}"
        )


##
# File management helpers
##

@contextmanager
def temporary_files(directory: Path, *filenames: str):
    """
    Context manager for temporary files that ensures cleanup.
    
    Parameters
    ----------
    directory : Path
        Directory where temporary files will be created.
    *filenames : str
        Names of temporary files to create.
        
    Yields
    ------
    dict[str, Path]
        Dictionary mapping filename to Path object.
    """
    directory.mkdir(parents=True, exist_ok=True)
    temp_paths = {name: directory / name for name in filenames}
    try:
        yield temp_paths
    finally:
        # Clean up temporary files
        for path in temp_paths.values():
            if path.exists():
                try:
                    path.unlink()
                except Exception as e:
                    LOGGER.debug(f"Could not remove temporary file {path}: {e}")


##
# Validation helpers
##

def validate_checkpoints(ckpt_ax: Path | None, ckpt_cor: Path | None, ckpt_sag: Path | None) -> None:
    """
    Validate that at least one checkpoint is provided.
    
    Parameters
    ----------
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Checkpoint paths for each plane.
        
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


##
# Processing
##
def crop_image_to_brain_mask(
    image_path: Path | str,
    brain_mask_path: Path | str,
    margin: float = 0.1,
    save_path: Path | str | None = None,
    make_cubic: bool = True,
) -> nib.analyze.SpatialImage:
    """
    Crop image to brain mask region with margin, optionally making it cubic.
    
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
    make_cubic : bool, default=True
        If True, crop to cubic dimensions by expanding smaller dimensions
        to match the largest dimension (splits extra space equally on both sides)
        
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
    
    # Make cubic if requested (expand smaller dimensions to match largest)
    if make_cubic:
        # Calculate current crop sizes with margin
        crop_sizes = dim_range[:, 1] - dim_range[:, 0] + 1
        max_size = np.max(crop_sizes)
        
        # Expand each dimension to match max_size
        for i in range(n_dims):
            if crop_sizes[i] < max_size:
                extra_space = max_size - crop_sizes[i]
                # Split extra space equally on both sides
                expand_before = extra_space // 2
                expand_after = extra_space - expand_before
                
                dim_range[i, 0] = dim_range[i, 0] - expand_before
                dim_range[i, 1] = dim_range[i, 1] + expand_after
    
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
    origin_voxel = np.array([xmin, ymin, zmin, 1.0])
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


def _load_checkpoint_data(checkpoint_path: Path | str) -> dict[str, Any]:
    """
    Load checkpoint data from file (shared helper).
    
    Parameters
    ----------
    checkpoint_path : Path, str
        Path to checkpoint file
        
    Returns
    -------
    dict
        Checkpoint dictionary
        
    Raises
    ------
    FileNotFoundError
        If checkpoint file doesn't exist
    """
    import torch
    
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    
    return torch.load(checkpoint_path, map_location='cpu', weights_only=False)


def load_config_from_checkpoint(checkpoint_path: Path | str, batch_size: int = 1) -> yacs.config.CfgNode:
    """
    Load configuration from checkpoint file.
    
    Parameters
    ----------
    checkpoint_path : Path, str
        Path to checkpoint file
    batch_size : int, default=1
        Batch size for testing
        
    Returns
    -------
    yacs.config.CfgNode
        Configuration object
    """
    import yaml
    
    checkpoint = _load_checkpoint_data(checkpoint_path)
    
    if 'config' not in checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_path} does not contain config!")
    
    # Parse config from checkpoint (saved as YAML string)
    config_str = checkpoint['config']
    config_dict = yaml.safe_load(config_str)
    
    # Convert back to CfgNode
    from FastSurferCNN.config.defaults import get_cfg_defaults
    cfg = get_cfg_defaults()
    cfg.merge_from_other_cfg(yacs.config.CfgNode(config_dict))
    
    # Set up for inference
    cfg.OUT_LOG_NAME = "fastsurfer"
    cfg.TEST.BATCH_SIZE = batch_size
    cfg.MODEL.OUT_TENSOR_WIDTH = cfg.DATA.PADDED_SIZE
    cfg.MODEL.OUT_TENSOR_HEIGHT = cfg.DATA.PADDED_SIZE
    
    return cfg


def setup_atlas_from_checkpoints(
    ckpt_ax: Path | None,
    ckpt_cor: Path | None,
    ckpt_sag: Path | None,
) -> tuple[str, dict]:
    """
    Extract and validate atlas metadata from checkpoint files.
    
    Parameters
    ----------
    ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
        Paths to checkpoint files for each plane.
    
    Returns
    -------
    tuple[str, dict]
        Atlas name and full atlas metadata dictionary.
        
    Raises
    ------
    RuntimeError
        If no atlas metadata found or checkpoints use different atlases.
    """
    from FastSurferCNN.utils.checkpoint import extract_atlas_metadata
    
    LOGGER.info("Extracting atlas information from checkpoints...")
    
    # Try to extract atlas from each checkpoint (they should all be the same atlas)
    atlas_metadatas = {}
    for plane, ckpt_path in [("axial", ckpt_ax), ("coronal", ckpt_cor), ("sagittal", ckpt_sag)]:
        if ckpt_path is not None:
            metadata = extract_atlas_metadata(ckpt_path)
            if metadata:
                atlas_metadatas[plane] = metadata
                LOGGER.info(f"  {plane.capitalize():9s}: {metadata['atlas_name']} "
                           f"({metadata['num_classes']} classes)")
    
    if not atlas_metadatas:
        raise RuntimeError(
            "Could not extract atlas metadata from any checkpoint. "
            "Please verify your checkpoint files are valid and contain atlas information."
        )
    
    # Validate that all checkpoints use the same atlas
    atlas_names = {meta['atlas_name'] for meta in atlas_metadatas.values()}
    if len(atlas_names) > 1:
        raise RuntimeError(
            f"Checkpoint atlas mismatch: {atlas_names}. "
            f"All checkpoints must be trained on the same atlas."
        )
    
    # Use the atlas from any checkpoint (they're all the same)
    atlas_name = list(atlas_metadatas.values())[0]['atlas_name']
    atlas_metadata = list(atlas_metadatas.values())[0]
    
    LOGGER.info(f"✓ Validated atlas: {atlas_name}")
    
    return atlas_name, atlas_metadata


def args2cfg(
    ckpt_ax: Path | None = None,
    ckpt_cor: Path | None = None,
    ckpt_sag: Path | None = None,
    batch_size: int = 1,
) -> tuple[
    yacs.config.CfgNode, yacs.config.CfgNode, yacs.config.CfgNode, yacs.config.CfgNode
]:
    """
    Load configuration objects from checkpoints.
    
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
            cfgs[plane_name] = load_config_from_checkpoint(ckpt, batch_size)
        else:
            cfgs[plane_name] = None
    
    cfg_cor, cfg_sag, cfg_ax = cfgs["coronal"], cfgs["sagittal"], cfgs["axial"]
    
    # Return the first non-None cfg as cfg_fin
    cfg_fin = next((cfg for cfg in (cfg_cor, cfg_sag, cfg_ax) if cfg is not None), None)
    if cfg_fin is None:
        raise RuntimeError("No valid configuration passed! At least one checkpoint must be provided.")
    
    return (cfg_fin, cfg_cor, cfg_sag, cfg_ax)


##
# Input array preparation
##


class RunModelOnData:
    """
    Run the model prediction on given data.

    Attributes
    ----------
    vox_size : float, 'min'
    current_plane : str
    models : Dict[str, Inference]
    view_ops : Dict[str, Dict[str, Any]]
    orientation : OrientationType
    conform_to_1mm_threshold : float, optional
        threshold until which the image will be conformed to 1mm res

    Methods
    -------
    __init__()
        Construct object.
    set_and_create_outdir()
        Sets and creates output directory.
    conform_and_save_orig()
        Saves original image.
    set_subject()
        Setter.
    get_subject_name()
        Getter.
    set_model()
        Setter.
    run_model()
        Calculates prediction.
    get_img()
        Getter.
    save_img()
        Saves image as file.
    set_up_model_params()
        Setter.
    get_num_classes()
        Getter.
    """

    vox_size: float | Literal["min"]
    current_plane: Plane
    models: dict[Plane, Inference]
    view_ops: dict[Plane, dict[str, Any]]
    conform_to_1mm_threshold: float | None
    device: torch.device
    viewagg_device: torch.device
    orientation: OrientationType
    _pool: Executor

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
            vox_size: VoxSizeOption = "min",
            orientation: OrientationType = "lia",
            image_size: bool = True,
            async_io: bool = False,
            conform_to_1mm_threshold: float = 0.95,
            plane_weight_coronal: float | None = None,
            plane_weight_axial: float | None = None,
            plane_weight_sagittal: float | None = None,
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
        ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
            Paths to checkpoint files (contain full config inside).
        viewagg_device : str, default="auto"
            Device to run viewagg on. Can be auto, cuda or cpu.
        """
        self._threads = threads
        torch.set_num_threads(self._threads)
        self._async_io = async_io
        self.orientation = orientation
        self.image_size = image_size

        self.sf = 1.0

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
            # check, if GPU is big enough to run view agg on it (this currently takes the memory of the passed device)
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
                f"Please verify the atlas is installed correctly."
            )
        
        self.lut_path = lut_path
        self.lut = du.read_classes_from_lut(lut_path)
        LOGGER.info(f"  Loaded LUT: {lut_path.name}")
        
        # Use the EXACT same dense-to-sparse mapping as training
        if atlas_metadata and atlas_metadata.get('dense_to_sparse_mapping') is not None:
            # Use the exact mapping from checkpoint (gold standard)
            self.labels = atlas_metadata['dense_to_sparse_mapping']
            self.torch_labels = torch.from_numpy(self.labels)
            LOGGER.info(f"  Label mapping: from checkpoint ({len(self.labels)} classes)")
        else:
            # Fallback: derive from AtlasManager
            try:
                atlas_manager = AtlasManager(atlas_name, atlas_dir=atlas_dir)
                self.labels = atlas_manager.get_dense_to_sparse_mapping()
                self.torch_labels = torch.from_numpy(self.labels)
                LOGGER.info(f"  Label mapping: from AtlasManager ({len(self.labels)} classes)")
                LOGGER.warning("  Checkpoint metadata not available - using AtlasManager fallback")
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialize label mapping for atlas '{atlas_name}': {e}. "
                    f"Please verify your atlas installation is complete."
                ) from e
        self.names = ["SubjectName", "Average", "Subcortical", "Cortical"]
        self.cfg_fin, cfg_cor, cfg_sag, cfg_ax = args2cfg(
            ckpt_ax=ckpt_ax, ckpt_cor=ckpt_cor, ckpt_sag=ckpt_sag,
            batch_size=batch_size
        )
        # the order in this dictionary dictates the order in the view aggregation
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
        valid_configs = [view["cfg"] for view in self.view_ops.values() if view["cfg"] is not None]
        if not valid_configs:
            raise RuntimeError("No valid plane configurations found. At least one checkpoint must be provided.")
        self.num_classes = max(cfg.MODEL.NUM_CLASSES for cfg in valid_configs)
        self.models = {}
        for plane, view in self.view_ops.items():
            if all(view[key] is not None for key in ("cfg", "ckpt")):
                # Skip loading model if plane weight is 0 (waste of resources)
                plane_weight = self.plane_weights[plane]
                if plane_weight is not None and plane_weight == 0:
                    LOGGER.info(f"Skipping {plane} model loading (plane weight is 0)")
                    continue
                
                # Update config with plane weights if provided
                cfg = view["cfg"]
                # Use explicit None check to allow 0 as a valid weight
                if self.plane_weights["coronal"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.CORONAL = self.plane_weights["coronal"]
                if self.plane_weights["axial"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.AXIAL = self.plane_weights["axial"]
                if self.plane_weights["sagittal"] is not None:
                    cfg.MULTIVIEW.PLANE_WEIGHTS.SAGITTAL = self.plane_weights["sagittal"]
                
                self.models[plane] = Inference(cfg, ckpt=view["ckpt"], device=self.device, lut=self.lut)

        # Load preprocessing parameters (prefer checkpoint over CLI)
        preprocess_from_ckpt = self._load_preprocessing_from_checkpoint(ckpt_cor or ckpt_sag or ckpt_ax)
        
        if preprocess_from_ckpt:
            self.vox_size = preprocess_from_ckpt.get('VOX_SIZE', vox_size)
            self.image_size = preprocess_from_ckpt.get('IMG_SIZE', image_size)
            self.orientation = preprocess_from_ckpt.get('ORIENTATION', orientation)
            self.conform_to_1mm_threshold = preprocess_from_ckpt.get('THRESHOLD_1MM', conform_to_1mm_threshold)
            LOGGER.info(f"  Preprocessing: from checkpoint (vox_size={self.vox_size}, orientation={self.orientation})")
        else:
            try:
                self.vox_size = _vox_size(vox_size)
            except (argparse.ArgumentTypeError, ValueError):
                raise ValueError(
                    f"Invalid vox_size value: '{vox_size}'. "
                    f"Must be a float between 0 and 1, or 'min'."
                ) from None
            self.conform_to_1mm_threshold = conform_to_1mm_threshold
            LOGGER.info(f"  Preprocessing: from CLI args (vox_size={self.vox_size}, orientation={orientation})")
            LOGGER.warning("  Checkpoint lacks preprocessing metadata - using CLI defaults")

    def _load_preprocessing_from_checkpoint(self, checkpoint_path: Path | str | None) -> dict | None:
        """
        Load preprocessing parameters from checkpoint config.
        
        Parameters
        ----------
        checkpoint_path : Path, str, None
            Path to checkpoint file
            
        Returns
        -------
        dict, None
            Preprocessing parameters dict from checkpoint config, or None if not available
        """
        if not checkpoint_path:
            return None
            
        try:
            import yaml
            
            # Load checkpoint using shared helper
            checkpoint = _load_checkpoint_data(checkpoint_path)
            
            # Check if checkpoint has config
            if 'config' not in checkpoint:
                return None
            
            # Parse config (it's saved as YAML string)
            config_str = checkpoint['config']
            config_dict = yaml.safe_load(config_str)
            
            # Extract preprocessing parameters
            if 'DATA' in config_dict and 'PREPROCESSING' in config_dict['DATA']:
                return config_dict['DATA']['PREPROCESSING']
            
            return None
            
        except Exception as e:
            LOGGER.warning(f"Could not load preprocessing params from checkpoint: {e}")
            return None
    
    @property
    def pool(self) -> Executor:
        """
        Return, and maybe create the objects executor object (with the number of threads
        specified in __init__).
        """
        if not hasattr(self, "_pool"):
            self._pool = ThreadPoolExecutor(self._threads) if self._async_io else SerialExecutor()
        return self._pool

    def __del__(self):
        """Class destructor."""
        if hasattr(self, "_pool"):
            # only wait on futures, if we specifically ask (see end of the script, so we
            # do not wait if we encounter a fail case)
            self._pool.shutdown(True)

    def __conform_kwargs(self, **kwargs) -> dict[str, Any]:
        return dict({
            "threshold_1mm": self.conform_to_1mm_threshold,
            "vox_size": self.vox_size,
            "orientation": self.orientation,
            "img_size": self.image_size,
        }, **kwargs)

    def conform_and_save_orig(
        self, subject: SubjectDirectory,
    ) -> tuple[nib.analyze.SpatialImage, np.ndarray]:
        """
        Conform and saves original image.

        Parameters
        ----------
        subject : SubjectDirectory
            Subject directory object.

        Returns
        -------
        tuple[nib.analyze.SpatialImage, np.ndarray]
            Conformed image.
        """
        orig, orig_data = du.load_image(subject.orig_name, "orig image")
        LOGGER.info(f"Successfully loaded image from {subject.orig_name}.")

        # Save input image to standard location, but only
        if subject.has_attribute("copy_orig_name") and subject.can_resolve_attribute("copy_orig_name"):
            self.async_save_img(subject.copy_orig_name, orig_data, orig, orig_data.dtype)

        if not is_conform(orig, **self.__conform_kwargs(verbose=True)):
            if (self.orientation is None or self.orientation == "native") and \
                    not is_conform(orig, **self.__conform_kwargs(verbose=False, dtype=None, vox_size="min")):
                LOGGER.warning("Support for anisotropic voxels is experimental. Careful QC of all images is needed!")
            LOGGER.info("Conforming image...")
            orig = conform(orig, **self.__conform_kwargs())
            orig_data = np.asanyarray(orig.dataobj)

        # Save conformed input image
        if subject.can_resolve_attribute("conf_name"):
            self.async_save_img(subject.conf_name, orig_data, orig, dtype=np.uint8)
            LOGGER.info(f"Saving conformed image to {subject.conf_name}...")
        else:
            raise RuntimeError("Cannot resolve the name to the conformed image, please specify an absolute path.")

        return orig, orig_data

    def set_model(self, plane: Plane):
        """
        Set the current model for the specified plane.

        Parameters
        ----------
        plane : Plane
            The plane for which to set the current model.
        """
        self.current_plane = plane

    def get_prediction(
        self, image_name: str, img: nib.analyze.SpatialImage | None = None,
    ) -> np.ndarray:
        """
        Run and get prediction.

        Parameters
        ----------
        image_name : str
            Original image filename (used for logging/identification).
        img : nib.analyze.SpatialImage, optional
            Image object. If None, will be loaded from image_name.

        Returns
        -------
        np.ndarray
            Predicted classes.
        """
        # Load image if not provided
        if img is None:
            img = nib.load(image_name)
        
        # Extract data, zoom, and affine from image
        orig_data = np.asanyarray(img.dataobj)
        zoom = img.header.get_zooms()
        affine = img.affine
        
        kwargs = {
            "device": self.viewagg_device,
            "dtype": torch.float16,
            "requires_grad": False,
        }

        if not np.allclose(_zoom := np.asarray(zoom), np.mean(zoom), atol=1e-4, rtol=1e-3):
            msg = "FastSurfer support for anisotropic images is experimental, we detected the following voxel sizes"
            LOGGER.warning(f"{msg}: {np.round(_zoom, decimals=4).tolist()}!")

        orig_in_lia, back_to_native = to_target_orientation(orig_data, affine, target_orientation="LIA")
        shape = orig_in_lia.shape + (self.get_num_classes(),)
        _ornt_transform, _ = orientation_to_ornts(affine, target_orientation="LIA")
        _zoom = _zoom[_ornt_transform[:, 0]]

        pred_prob = torch.zeros(shape, **kwargs)

        # inference and view aggregation
        for plane, model in self.models.items():
            LOGGER.info(f"Run {plane} prediction")
            self.set_model(plane)
            # pred_prob is updated inplace to conserve memory
            pred_prob = model.run(pred_prob, image_name, orig_in_lia, _zoom, out=pred_prob)

        # Get hard predictions
        pred_classes = torch.argmax(pred_prob, 3)
        del pred_prob
        # reorder from lia to native
        pred_classes = back_to_native(pred_classes)
        # map to freesurfer label space
        pred_classes = du.map_label2aparc_aseg(pred_classes, self.labels)
        # return numpy array
        pred_classes = pred_classes.cpu().numpy()
        
        # Apply FreeSurfer-specific post-processing only for FreeSurfer atlases
        if du.is_freesurfer_lut(self.lut["ID"].values):
            LOGGER.info("Applying FreeSurfer-specific cortex label splitting")
            pred_classes = du.split_cortex_labels(pred_classes)
        else:
            LOGGER.info("Skipping cortex label splitting (custom atlas)")
        
        return pred_classes

    def save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        ref_image: nib.analyze.SpatialImage,
        dtype: type | None = None,
    ) -> None:
        """
        Save image as a file.

        Parameters
        ----------
        save_as : str, Path
            Filename to give the image.
        data : np.ndarray, torch.Tensor
            Image data.
        orig : nib.analyze.SpatialImage
            Original Image.
        dtype : type, optional
            Data type to use for saving the image. If None, the original data type is used.
        """
        save_as = Path(save_as)
        # Create output directory if it does not already exist.
        if not save_as.parent.exists():
            LOGGER.info(f"Output image directory {save_as.parent} does not exist. Creating it now...")
            save_as.parent.mkdir(parents=True)

        np_data = data if isinstance(data, np.ndarray) else data.cpu().numpy()
        if dtype is not None:
            _header = ref_image.header.copy()
            _header.set_data_dtype(dtype)
        else:
            _header = ref_image.header
        du.save_image(_header, ref_image.affine, np_data, save_as, dtype=dtype)
        LOGGER.info(f"Successfully saved image {'asynchronously ' if self._async_io else ''}as {save_as}.")

    def async_save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        orig: nib.analyze.SpatialImage,
        dtype: type | None = None,
    ) -> Future[None]:
        """
        Save the image asynchronously and return a concurrent.futures.Future to track,
        when this finished.

        Parameters
        ----------
        save_as : str, Path
            Filename to give the image.
        data : np.ndarray, torch.Tensor
            Image data.
        orig : nib.analyze.SpatialImage
            Original Image.
        dtype : type, optional
            Data type to use for saving the image. If None, the original data type is used.

        Returns
        -------
        Future[None]
            A Future object to synchronize (and catch/handle exceptions in the save_img method).
        """
        return self.pool.submit(self.save_img, save_as, data, orig, dtype)

    def set_up_model_params(
            self,
            plane: Plane,
            cfg: "yacs.config.CfgNode",
            ckpt: "torch.Tensor",
    ) -> None:
        """
        Set up the model parameters from the configuration and checkpoint.
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

    def pipeline_conform_and_save_orig(
        self, subjects: SubjectList,
    ) -> Iterator[tuple[SubjectDirectory, tuple[nib.analyze.SpatialImage, np.ndarray]]]:
        """
        Pipeline for conforming and saving original images asynchronously.

        Parameters
        ----------
        subjects : SubjectList
            List of subjects to process.

        Yields
        ------
        tuple[SubjectDirectory, tuple[nib.analyze.SpatialImage, np.ndarray]]
            Subject directory and a tuple with the image and its data.
        """
        if not self._async_io:
            # do not pipeline, direct iteration and function call
            for subject in subjects:
                # yield subject and load orig
                yield subject, self.conform_and_save_orig(subject)
        else:
            # pipeline the same
            yield from pipeline(self.pool, self.conform_and_save_orig, subjects)


def apply_two_pass_refinement(
    orig_img: nib.analyze.SpatialImage,
    pred_data_first: np.ndarray,
    predictor: "RunModelOnData",
    output_dir: Path,
    pred_name: str,
    cleanup_temp: bool = False,
) -> tuple[np.ndarray, nib.analyze.SpatialImage, bool, str | None]:
    """
    Apply two-pass refinement if brain is small relative to FOV.
    
    Two-pass refinement crops the image to the brain region and reruns prediction
    for better accuracy when the brain occupies a small portion of the field of view.
    
    Uses FreeSurfer directory structure: output_dir/mri/prediction_orig/
    
    Parameters
    ----------
    orig_img : nib.analyze.SpatialImage
        Original conformed image.
    pred_data_first : np.ndarray
        First-pass prediction data.
    predictor : RunModelOnData
        Model runner object.
    output_dir : Path
        Output directory (subject directory equivalent).
        Two-pass files will be saved to output_dir/mri/prediction_orig/
    pred_name : str
        Final prediction filename (e.g., "mri/aparc.ARM2atlas+aseg.deep.mgz").
        First-pass prediction will be saved with "_1st_pass" suffix.
    cleanup_temp : bool, default=False
        If True, clean up pass_1_dir after processing.
    
    Returns
    -------
    tuple
        (final_pred_data, final_orig_img, refinement_applied, cropped_conf_path)
        cropped_conf_path: Path to cropped conformed image (output_dir/mri/orig.mgz) if two-pass was done, None otherwise
    """
    LOGGER.info("Checking if two-pass refinement is beneficial...")
    
    # Create brain mask from first prediction
    brain_mask = rta.create_mask(copy.deepcopy(pred_data_first), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
    brain_volume = np.sum(brain_mask > 0)
    total_volume = np.prod(brain_mask.shape)
    brain_ratio = brain_volume / total_volume
    
    orig_shape = orig_img.shape
    max_orig_dim = max(orig_shape)
    
    LOGGER.info(f"  Brain occupancy: {brain_ratio*100:.1f}% of FOV ({brain_volume:,} voxels)")
    LOGGER.info(f"  Image dimensions: {orig_shape} (max: {max_orig_dim})")
    
    # Check if two-pass refinement is needed
    should_refine = (brain_ratio < TWO_PASS_BRAIN_RATIO_THRESHOLD and 
                     max_orig_dim > TWO_PASS_MAX_DIMENSION_THRESHOLD)
    
    if not should_refine:
        if brain_ratio >= TWO_PASS_BRAIN_RATIO_THRESHOLD:
            LOGGER.info(f"  → Skipping refinement (brain occupancy >= {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%)")
        else:
            LOGGER.info(f"  → Skipping refinement (image dimension <= {TWO_PASS_MAX_DIMENSION_THRESHOLD})")
        return pred_data_first, orig_img, False, None
    
    LOGGER.info(f"  → Applying two-pass refinement (brain < {TWO_PASS_BRAIN_RATIO_THRESHOLD*100:.0f}%, dim > {TWO_PASS_MAX_DIMENSION_THRESHOLD})")
    
    # Setup pass_1_dir for two-pass refinement intermediate files (FreeSurfer structure)
    mri_dir = output_dir / "mri"
    pass_1_dir = mri_dir / "prediction_orig"
    conf_file = mri_dir / "orig.mgz"
    orig_conf_path = pass_1_dir / "orig.mgz"
    mask_path = pass_1_dir / "mask.mgz"
    cropped_input_path = pass_1_dir / "orig_cropped_cubic.nii.gz"
    final_pred_path = None  # Will be determined from output_dir structure if needed
    pred_1st_path = None
    
    pass_1_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Save conformed image
        if conf_file.exists():
            # Move existing conformed image to pass_1_dir
            LOGGER.info(f"  Moving conformed image to {orig_conf_path.name}")
            conf_file.rename(orig_conf_path)
            conf_img = nib.load(orig_conf_path)
        else:
            # Save from image object
            LOGGER.info(f"  Saving conformed image temporarily...")
            predictor.save_img(orig_conf_path, np.asanyarray(orig_img.dataobj), orig_img, dtype=np.uint8)
            conf_img = orig_img
        
        # Step 2: Save brain mask
        predictor.save_img(mask_path, brain_mask, orig_img, dtype=np.uint8)
        
        # Step 3: Save first-pass prediction for reference (use same name as final prediction)
        # Extract filename from pred_name (e.g., "mri/aparc.ARM2atlas+aseg.deep.mgz" -> "aparc.ARM2atlas+aseg.deep.mgz")
        pred_filename = Path(pred_name).name
        pred_1st_path = pass_1_dir / pred_filename
        LOGGER.info(f"  Saving first-pass prediction: {pred_1st_path.name}")
        predictor.save_img(pred_1st_path, pred_data_first, orig_img, dtype=np.int16)
        
        # Step 4: Crop to brain region AND make cubic in one step
        LOGGER.info(f"  Cropping to cubic brain region (margin={TWO_PASS_CROP_MARGIN*100:.0f}%)...")
        
        cropped_img_cubic = crop_image_to_brain_mask(
            orig_conf_path, mask_path, 
            margin=TWO_PASS_CROP_MARGIN, 
            save_path=cropped_input_path,
            make_cubic=True  # Crop directly to cubic dimensions
        )
        
        if not cropped_input_path.exists():
            raise RuntimeError(f"Failed to save cropped image to {cropped_input_path}")
        
        if conf_file is not None and conf_file.exists():
            raise RuntimeError(f"Conformed image still at {conf_file} - would cause incorrect 2nd pass!")
        
        LOGGER.info(f"  ✓ Cropped to cubic: {orig_img.shape} → {cropped_img_cubic.shape}")
        LOGGER.info(f"  ✓ Space saved: {np.prod(orig_img.shape) / np.prod(cropped_img_cubic.shape):.1f}x reduction!")
        
        # Step 5: Save cropped image as orig.mgz
        LOGGER.info(f"  Saving cubic cropped image as orig.mgz...")
        cropped_data = np.asanyarray(cropped_img_cubic.dataobj)
        predictor.save_img(
            conf_file,
            cropped_data,
            cropped_img_cubic,
            dtype=np.uint8
        )
        cropped_conf_path = str(conf_file)
        
        # Step 6: Run second-pass prediction on cubic cropped image
        LOGGER.info("  Running 2nd pass prediction...")
        pred_data_second = predictor.get_prediction(
            str(cropped_input_path),
            cropped_img_cubic
        )
        
        LOGGER.info("  ✓ Two-pass refinement completed successfully")
        
        # Clean up temporary files (standalone mode only)
        if cleanup_temp:
            LOGGER.info("  Cleaning up temporary files...")
            shutil.rmtree(pass_1_dir, ignore_errors=True)
        
        return pred_data_second.astype(np.int16), cropped_img_cubic, True, cropped_conf_path
        
    except Exception as e:
        LOGGER.error(f"  ✗ Two-pass refinement failed: {e}")
        LOGGER.warning("  Falling back to first-pass prediction")
        
        # Restore conf_file if it was moved
        if 'orig_conf_path' in locals() and orig_conf_path.exists() and not conf_file.exists():
            orig_conf_path.rename(conf_file)
        
        # Clean up on error (standalone mode only)
        if cleanup_temp and pass_1_dir.exists():
            shutil.rmtree(pass_1_dir, ignore_errors=True)
        
        return pred_data_first, orig_img, False, None


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
    two_pass_done: bool,
    cropped_conf_path: str | None,
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
        Original image (possibly cropped if two-pass was applied).
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
    two_pass_done : bool
        Whether two-pass refinement was applied.
    cropped_conf_path : str, optional
        Path to cropped conformed image (if two-pass was applied).
    
    Returns
    -------
    np.ndarray
        Corrected segmentation data.
    """
    LOGGER.info("Applying V1 white matter correction...")
    
    try:
        # Get file paths (FreeSurfer structure)
        segfile = output_dir / pred_name
        conf_file = Path(cropped_conf_path) if two_pass_done and cropped_conf_path else (output_dir / conf_name)
        mask_file = output_dir / brainmask_name
        
        # Create masks if they don't exist
        if not Path(mask_file).exists():
            LOGGER.info("  Creating brain mask...")
            temp_mask = rta.create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
            predictor.save_img(mask_file, temp_mask, orig_img, dtype=np.uint8)
        
        # Create hemisphere mask if it doesn't exist
        hemi_mask_file = mask_file.parent / (mask_file.stem + "_hemi" + mask_file.suffix)
        if not hemi_mask_file.exists():
            LOGGER.info("  Creating hemisphere mask...")
            temp_mask = nib.load(mask_file).get_fdata().astype(np.int16)
            hemi_mask = rta.create_hemisphere_masks(temp_mask, pred_data, lut_path=predictor.lut_path)
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
    Create aseg and brainmask files with optional WM island correction.
    
    Saves files synchronously (no async).
    
    Parameters
    ----------
    pred_data : np.ndarray
        Prediction data.
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
        Skip WM island correction.
    debug_wm_correction : bool
        Save debug files showing before/after WM correction.
    """
    # Note: Brain mask and hemisphere mask are already saved in process_image_freesurfer_pipeline
    # This function only creates aseg
    
    # Load brain mask (already saved)
    mask_path = output_dir / brainmask_name
    if not mask_path.exists():
        LOGGER.warning(f"Brain mask not found at {mask_path}, creating it...")
        brain_mask = rta.create_mask(copy.deepcopy(pred_data), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        predictor.save_img(mask_path, brain_mask, orig_img, dtype=np.uint8)
    else:
        brain_mask = nib.load(mask_path).get_fdata().astype(np.uint8)
    
    # Create and save aseg
    LOGGER.info("Creating aseg (converting to FreeSurfer label conventions)...")
    aseg = rta.reduce_to_aseg(pred_data, lut_path=predictor.lut_path, verbose=True)
    aseg[brain_mask == 0] = 0
    
    # Optional debug: save BEFORE WM correction
    if debug_wm_correction and not skip_wm_correction:
        aseg_before = copy.deepcopy(aseg)
        debug_before_path = output_dir / aseg_name.replace(".mgz", ".BEFORE_WM_FLIP.mgz")
        debug_dtype = np.int16 if np.any(aseg_before < 0) else np.uint8
        LOGGER.info(f"  [DEBUG] Saving pre-correction: {debug_before_path.name}")
        predictor.save_img(debug_before_path, aseg_before, orig_img, dtype=debug_dtype)
    
    # Apply WM island correction
    if not skip_wm_correction:
        aseg = rta.flip_wm_islands_auto(aseg, lut_path=predictor.lut_path)
        
        # Optional debug: save AFTER WM correction
        if debug_wm_correction:
            debug_after_path = output_dir / aseg_name.replace(".mgz", ".AFTER_WM_FLIP.mgz")
            debug_dtype = np.int16 if np.any(aseg < 0) else np.uint8
            LOGGER.info(f"  [DEBUG] Saving post-correction: {debug_after_path.name}")
            predictor.save_img(debug_after_path, aseg, orig_img, dtype=debug_dtype)
    else:
        LOGGER.info("  Skipping WM island correction")
    
    # Save final aseg
    aseg_path = output_dir / aseg_name
    aseg_dtype = np.int16 if np.any(aseg < 0) else np.uint8
    LOGGER.info(f"Saving aseg: {aseg_path.name}")
    predictor.save_img(aseg_path, aseg, orig_img, dtype=aseg_dtype)


def make_parser():
    """
    Create the argparse object.

    Returns
    -------
    argparse.ArgumentParser
        The parser object.
    """
    parser = argparse.ArgumentParser(description="FastSurfer segmentation prediction")

    # 1. Output format selection (NEW)
    parser.add_argument(
        "--output_format",
        choices=["standalone", "freesurfer"],
        default="standalone",
        help="Output format: 'standalone' for simple NIfTI outputs in input space, "
             "'freesurfer' for FreeSurfer-compatible MGZ outputs for surf_recon pipeline (default: standalone)"
    )

    # 2. Input options
    parser = parser_defaults.add_arguments(
        parser,
        ["t1"],
    )
    
    # 3. Standalone mode output options
    parser.add_argument(
        "--output_dir",
        type=Path,
        help="Output directory for standalone mode (required if --output_format standalone)"
    )

    # 4. FreeSurfer mode input/output options
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
        help="Skip WM island correction (flipping mislabeled disconnected WM regions to correct hemisphere). "
             "By default, WM island correction is enabled to fix occasional CNN mislabeling and improve mri_cc performance.",
        default=False,
    )
    parser.add_argument(
        "--debug_wm_correction",
        dest="debug_wm_correction",
        action="store_true",
        help="Save debug files for WM island correction: aseg.auto_noCCseg.BEFORE_WM_FLIP.mgz and "
             "aseg.auto_noCCseg.AFTER_WM_FLIP.mgz for visual comparison. Only used if WM correction is enabled.",
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
) -> tuple[np.ndarray, nib.analyze.SpatialImage, bool, str | None]:
    """
    Process a single image through the FreeSurfer pipeline (conform, predict, two-pass).
    
    This function implements the core processing logic used by both standalone and FreeSurfer modes.
    Always uses FreeSurfer directory structure (output_dir/mri/...).
    Returns results in conformed space.
    
    Parameters
    ----------
    output_dir : Path
        Output directory (equivalent to subject directory). 
        For FreeSurfer mode: sub_dir/sub_id
        For standalone mode: output_dir/intermediate_dir
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
    tuple[np.ndarray, nib.analyze.SpatialImage, bool, str | None]
        (prediction_data_in_conformed_space, conformed_image, two_pass_done, cropped_conf_path)
        two_pass_done: True if two-pass refinement was applied, False otherwise
        cropped_conf_path: Path to cropped conformed image if two-pass was done, None otherwise
    """
    # Determine conformed image
    if orig_img_native is not None:
        # Standalone mode: need to conform
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
    
    # Run initial prediction in conformed space
    LOGGER.info("Running initial prediction...")
    pred_data_conformed = predictor.get_prediction(orig_name_for_pred, conformed_img)
    
    # Apply two-pass refinement if beneficial (uses output_dir/mri/prediction_orig)
    pred_data_conformed, conformed_img, two_pass_done, cropped_conf_path = apply_two_pass_refinement(
        conformed_img,
        pred_data_conformed,
        predictor,
        output_dir=output_dir,
        pred_name=pred_name,
        cleanup_temp=False  # Keep pass_1 files
    )
    
    # Save prediction to FreeSurfer structure
    pred_file = output_dir / pred_name
    pred_file.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving prediction: {pred_file.name}")
    predictor.save_img(pred_file, pred_data_conformed, conformed_img, dtype=np.int16)
    
    # Create and save brain mask and hemisphere mask in mri/
    LOGGER.info("Creating brain and hemisphere masks...")
    try:
        brain_mask = rta.create_mask(copy.deepcopy(pred_data_conformed), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
        hemi_mask = rta.create_hemisphere_masks(brain_mask, pred_data_conformed, lut_path=predictor.lut_path)
        
        mask_path = output_dir / "mri" / "mask.mgz"
        predictor.save_img(mask_path, brain_mask, conformed_img, dtype=np.uint8)
        LOGGER.info(f"  Saved: {mask_path.name}")
        
        hemi_mask_path = output_dir / "mri" / "mask_hemi.mgz"
        predictor.save_img(hemi_mask_path, hemi_mask, conformed_img, dtype=np.uint8)
        LOGGER.info(f"  Saved: {hemi_mask_path.name}")
    except Exception as e:
        LOGGER.warning(f"Could not create masks: {e}")
    
    return pred_data_conformed, conformed_img, two_pass_done, cropped_conf_path


def run_freesurfer_mode(
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
    Run FreeSurfer-compatible prediction mode.
    
    Single subject processing only. Uses output_dir directly as the subject directory.
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
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
            async_io=async_io,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
        )
    except RuntimeError as e:
        return e.args[0]

    try:
        # Load original image
        orig_img_native = nib.load(orig_name)
        
        # Run FreeSurfer pipeline (conform, predict, two-pass)
        # Results saved to subject_dir/mri/... (FreeSurfer structure)
        pred_data, orig_img, two_pass_done, cropped_conf_path = process_image_freesurfer_pipeline(
            output_dir=subject_dir,
            predictor=predictor,
            orig_img_native=orig_img_native,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
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
                brainmask_name=brainmask_name,
                two_pass_done=two_pass_done,
                cropped_conf_path=cropped_conf_path
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

def run_standalone_prediction(
        *,
        orig_name: Path | str,
        output_dir: Path,
        ckpt_ax: Path | None,
        ckpt_sag: Path | None,
        ckpt_cor: Path | None,
        device: str = "auto",
        viewagg_device: str = "auto",
        batch_size: int = 1,
        vox_size: VoxSizeOption = "min",
        orientation: OrientationType = "lia",
        image_size: bool = True,
        async_io: bool = True,
        threads: int = -1,
        conform_to_1mm_threshold: float = 0.95,
        plane_weight_coronal: float | None = None,
        plane_weight_axial: float | None = None,
        plane_weight_sagittal: float | None = None,
        **kwargs,
) -> Literal[0] | str:
    """
    Run standalone prediction with outputs in input space as NIfTI files.
    
    This function:
    1. Runs the FreeSurfer pipeline (conform, predict, two-pass) first
    2. Saves intermediate results in conformed space to output_dir/intermediate_dir
    3. Backprojects results from conformed space to original input space
    4. Saves final outputs as NIfTI files in output_dir
    
    Directory structure:
    - output_dir/pass_1_dir/: Two-pass refinement intermediate files (core algorithm)
    - output_dir/intermediate_dir/: Final conformed results (segmentation, conformed image)
    - output_dir/: Final outputs in native space (segmentation.nii.gz, mask.nii.gz, etc.)
    
    All intermediate files are preserved for debugging.
    
    Parameters
    ----------
    orig_name : Path, str
        Input T1 image path
    output_dir : Path
        Output directory for results (final outputs) and intermediate_dir (intermediate results)
    (other parameters same as main())
    
    Returns
    -------
    int or str
        0 on success, error message on failure
    """
    LOGGER.info("=" * 80)
    LOGGER.info("Running in STANDALONE mode")
    LOGGER.info("=" * 80)
    
    if len(kwargs) > 0:
        LOGGER.warning(f"Unknown arguments {list(kwargs.keys())} in standalone mode.")
    
    # Validate that at least one checkpoint is provided
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    
    # Create output directory
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Output directory: {output_dir}")
    
    # Download checkpoints if needed
    if any(ckpt is not None for ckpt in [ckpt_ax, ckpt_cor, ckpt_sag]):
        LOGGER.info("Checking or downloading checkpoints...")
        urls = load_checkpoint_config_defaults("url", filename=CHECKPOINT_PATHS_FILE)
        get_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag, urls=urls)
    
    # Extract atlas information from checkpoints
    atlas_name, atlas_metadata = setup_atlas_from_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    
    # Update pred_name to use the atlas name if it's using the generic default
    default_pred_name = "mri/aparc+aseg.deep.mgz"
    pred_name = default_pred_name  # Use default for standalone mode
    if pred_name == default_pred_name:
        pred_name = f"mri/aparc.{atlas_name}atlas+aseg.deep.mgz"
        LOGGER.info(f"Updated output filename to: {pred_name}")
    
    try:
        # Set up predictor
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
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
            async_io=async_io,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
        )
    except RuntimeError as e:
        return e.args[0]
    
    # Load original image (keep reference for backprojection)
    LOGGER.info(f"Loading input image: {orig_name}")
    orig_img_native = nib.load(orig_name)
    
    # Create intermediate_dir (equivalent to sub_dir/sub_id in FreeSurfer mode)
    intermediate_dir = output_dir / "intermediate_dir"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Intermediate directory (FreeSurfer structure): {intermediate_dir}")
    
    # Run FreeSurfer pipeline (conform, predict, two-pass) - returns results in conformed space
    # Results are saved to intermediate_dir/mri/... (FreeSurfer structure)
    pred_data_conformed, orig_img_conformed, _, _ = process_image_freesurfer_pipeline(
        output_dir=intermediate_dir,
        predictor=predictor,
        orig_img_native=orig_img_native,
        conform_to_1mm_threshold=conform_to_1mm_threshold,
        vox_size=vox_size,
        orientation=orientation,
        image_size=image_size,
        orig_name=orig_name,
        pred_name=pred_name
    )
    
    # Results are already saved in intermediate_dir/mri/ by process_image_freesurfer_pipeline
    LOGGER.info("FreeSurfer pipeline completed. Results saved in intermediate_dir/mri/")
    
    # Backproject results from conformed space to original input space using ANTs
    LOGGER.info("=" * 80)
    LOGGER.info("Backprojecting results to input space using ANTs...")
    LOGGER.info("=" * 80)
    
    # Check ANTs and FreeSurfer availability (hard requirement)
    if not check_ants_available():
        raise RuntimeError(
            "ANTs is required for backprojection but not found. "
            "Please ensure ANTs is installed and in your PATH."
        )
    if not check_mri_convert_available():
        raise RuntimeError(
            "mri_convert (FreeSurfer) is required for backprojection but not found. "
            "Please ensure FreeSurfer is installed and in your PATH."
        )
    
    try:
        from macacaMRIprep.operations.registration import ants_register, ants_apply_transforms
    except ImportError:
        try:
            from macacaMRIprep.operations import ants_register, ants_apply_transforms
        except ImportError:
            raise ImportError(
                "macacaMRIprep is required for backprojection but not found. "
                "Please install macacaMRIprep or ensure it's in your Python path."
            )
    
    # Get final conformed image path (after two-pass if applied)
    conf_file = intermediate_dir / "mri" / "orig.mgz"
    if not conf_file.exists():
        raise FileNotFoundError(f"Conformed image not found at {conf_file}")
    
    # Create brain mask and hemisphere mask in conformed space
    LOGGER.info("Creating masks in conformed space...")
    mask_conformed = rta.create_mask(
        copy.deepcopy(pred_data_conformed),
        MASK_DILATION_SIZE,
        MASK_EROSION_SIZE
    )
    hemimask_conformed = rta.create_hemisphere_masks(
        mask_conformed,
        pred_data_conformed,
        lut_path=predictor.lut_path
    )
    
    # ------------------------------------------------------------
    # Backprojection: Transform results from conformed space to native input space
    # ------------------------------------------------------------
    backprojection_dir = intermediate_dir / "backprojection"
    backprojection_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Prepare images for registration
    # Convert conformed image (orig.mgz) to NIfTI
    conf_nii = backprojection_dir / "orig_conformed.nii.gz"
    convert_mgz_to_nifti(conf_file, conf_nii)
    
    # Use input image directly if NIfTI, convert if MGZ
    if str(orig_name).lower().endswith(".mgz"):
        input_nii = backprojection_dir / "input_native.nii.gz"
        convert_mgz_to_nifti(orig_name, input_nii)
    else:
        input_nii = Path(orig_name)
    
    # Step 2: Register conformed image to input image using ANTs (rigid)
    LOGGER.info("Registering conformed image to input image...")
    
    outputs = ants_register(
        fixedf=str(input_nii),  # Target space (native input)
        movingf=str(conf_nii),  # Source space (conformed)
        working_dir=str(backprojection_dir),
        output_prefix="conformed_to_native",
        config=None,
        logger=LOGGER,
        xfm_type='rigid'
    )
    
    xfm_file = Path(outputs.get('forward_transform', backprojection_dir / "conformed_to_native_Composite.h5"))
    if not xfm_file.exists():
        raise RuntimeError(f"ANTs registration failed to create forward transform at {xfm_file}")
    LOGGER.info(f"  Transformation saved: {xfm_file.name}")
    
    # Step 3: Transform all outputs (segmentation, mask, hemimask)
    LOGGER.info("Transforming outputs to native space...")
    
    # Load conformed image for header/affine
    orig_img_conformed = nib.load(conf_file)
    
    # Define outputs to transform
    outputs_to_transform = [
        ("segmentation", pred_data_conformed, np.int16, output_dir / "segmentation.nii.gz"),
        ("brain mask", mask_conformed, np.uint8, output_dir / "mask.nii.gz"),
        ("hemisphere mask", hemimask_conformed, np.uint8, output_dir / "hemimask.nii.gz"),
    ]
    
    # Process each output: save as MGZ -> convert to NIfTI -> transform with ANTs
    # Use context manager for temporary files (ensures cleanup)
    with temporary_files(backprojection_dir, "temp.mgz", "temp.nii.gz") as temp_files:
        temp_mgz = temp_files["temp.mgz"]
        temp_nii = temp_files["temp.nii.gz"]
        
        for name, data, dtype, output_file in outputs_to_transform:
            # Save as MGZ, then convert to NIfTI
            predictor.save_img(temp_mgz, data, orig_img_conformed, dtype=dtype)
            convert_mgz_to_nifti(temp_mgz, temp_nii)
            
            # Transform to native space
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_rel = output_file.name
            
            LOGGER.info(f"Applying transformation to {temp_nii.name}...")
            outputs = ants_apply_transforms(
                movingf=str(temp_nii),
                moving_type=0,
                interpolation="NearestNeighbor",
                outputf_name=output_rel,
                fixedf=str(input_nii),
                working_dir=str(backprojection_dir),
                transformf=str(xfm_file),
                logger=LOGGER,
                reff=str(input_nii),
                generate_tmean=False
            )
            
            # Move output to final location if needed
            transformed_path = Path(outputs.get('imagef_registered', backprojection_dir / output_rel))
            if transformed_path.resolve() != output_file.resolve():
                shutil.move(str(transformed_path), str(output_file))
            
            if not output_file.exists():
                raise RuntimeError(f"antsApplyTransforms failed to create {output_file}")
            LOGGER.info(f"  Saved: {output_file.name}")
    
    LOGGER.info("=" * 80)
    LOGGER.info("Standalone prediction completed successfully!")
    LOGGER.info("=" * 80)
    
    return 0


def main(
        *,
        orig_name: Path | str,
        output_dir: Path | None = None,
        output_format: str = "standalone",
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
    Main entry point that routes to standalone or FreeSurfer mode.
    
    Parameters
    ----------
    output_format : str
        "standalone" or "freesurfer" mode
    output_dir : Path, optional
        Output directory (required for both modes)
    (other parameters documented in run_standalone_prediction and FreeSurfer mode)
    """
    
    if len(kwargs) > 0:
        LOGGER.warning(f"Unknown arguments {list(kwargs.keys())} in {__file__}:main.")
    
    # Route to appropriate mode
    if output_format == "standalone":
        # Validate standalone mode requirements
        if output_dir is None:
            raise ValueError("--output_dir is required for standalone mode")
        
        # Call standalone prediction function
        return run_standalone_prediction(
            orig_name=orig_name,
            output_dir=output_dir,
            ckpt_ax=ckpt_ax,
            ckpt_sag=ckpt_sag,
            ckpt_cor=ckpt_cor,
            device=device,
            viewagg_device=viewagg_device,
            batch_size=batch_size,
            vox_size=vox_size,
            orientation=orientation,
            image_size=image_size,
            async_io=async_io,
            threads=threads,
            conform_to_1mm_threshold=conform_to_1mm_threshold,
            plane_weight_coronal=plane_weight_coronal,
            plane_weight_axial=plane_weight_axial,
            plane_weight_sagittal=plane_weight_sagittal,
            **kwargs,
        )
    
    elif output_format == "freesurfer":
        # Validate FreeSurfer mode requirements
        if output_dir is None:
            raise ValueError("--output_dir is required for freesurfer mode")
        
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
        
        # Continue with original FreeSurfer mode logic
        return run_freesurfer_mode(
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
    
    else:
        raise ValueError(f"Invalid output_format: {output_format}. Must be 'standalone' or 'freesurfer'")


if __name__ == "__main__":
    parser = make_parser()
    _args = parser.parse_args()

    # Set up logging
    setup_logging(_args.log_name)

    # Remove log_name from args before passing to main (it's only used for logging setup)
    main_args = vars(_args)
    main_args.pop("log_name", None)

    sys.exit(main(**main_args))