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
import copy
import shutil
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
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

from FastSurferCNN.postprocessing.postseg_utils import flip_wm_islands_auto
from FastSurferCNN.atlas.atlas_manager import AtlasManager
from FastSurferCNN.data_loader import data_utils
from FastSurferCNN.data_loader.conform import conform, is_conform,orientation_to_ornts, to_target_orientation
from FastSurferCNN.inference.inference import Inference
from FastSurferCNN.utils import Plane, logging
from FastSurferCNN.utils.arg_types import OrientationType, VoxSizeOption
from FastSurferCNN.utils.arg_types import vox_size as _vox_size
from FastSurferCNN.utils.checkpoint import (
    extract_atlas_metadata,
    extract_training_config,
    read_checkpoint_file,
)
from FastSurferCNN.utils.common import (
    SerialExecutor,
    SubjectDirectory,
    SubjectList,
    find_device,
    pipeline,
)

##
# Global Variables
##
from FastSurferCNN.utils.parser_defaults import FASTSURFER_ROOT

LOGGER = logging.getLogger(__name__)
CHECKPOINT_PATHS_FILE = FASTSURFER_ROOT / "FastSurferCNN/config/checkpoint_paths.yaml"

##
# Constants
##

# Brain mask creation parameters
MASK_DILATION_SIZE = 5  # Dilation kernel size for mask creation
MASK_EROSION_SIZE = 4   # Erosion kernel size for mask creation



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


def load_multiplane_configs(
    ckpt_ax: Path | None = None,
    ckpt_cor: Path | None = None,
    ckpt_sag: Path | None = None,
    batch_size: int = 1,
) -> tuple[
    yacs.config.CfgNode, yacs.config.CfgNode, yacs.config.CfgNode, yacs.config.CfgNode
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
    Generic predictor for running multi-view segmentation on brain images.
    
    This class provides a generic interface for brain segmentation that works with
    any image format, not tied to FreeSurfer directory structures.

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
    conform_image(image_path, save_conformed, save_original_copy)
        Load and conform an image (generic method).
    get_prediction(image_name, img)
        Run inference and return prediction array.
    save_img(save_as, data, dtype, resample_to_native, interpolation)
        Save image with automatic native space resampling.
    async_save_img(save_as, data, dtype, resample_to_native)
        Asynchronously save image.
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
        ckpt_ax, ckpt_cor, ckpt_sag : Path, optional
            Paths to checkpoint files (contain full config inside).
        viewagg_device : str, default="auto"
            Device to run viewagg on. Can be auto, cuda or cpu.
        fix_wm_islands : bool, default=True
            Whether to apply WM island correction after segmentation. This fixes
            mislabeled disconnected WM regions by flipping them to the correct hemisphere.
            Enabled by default as it improves downstream processing (e.g., mri_cc performance).
        """
        self._threads = threads
        torch.set_num_threads(self._threads)
        self._async_io = async_io
        self.orientation = orientation
        self.image_size = image_size
        self.fix_wm_islands = fix_wm_islands

        # Context for native space resampling
        self._input_master_path: Path | None = None
        self._input_native_img: nib.analyze.SpatialImage | None = None
        self._conformed_img: nib.analyze.SpatialImage | None = None
        self._conform_kwargs: dict = {}

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
        self.lut = data_utils.read_classes_from_lut(lut_path)
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
        self.cfg_fin, cfg_cor, cfg_sag, cfg_ax = load_multiplane_configs(
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
        preprocess_from_ckpt = self._extract_preprocessing_params(ckpt_cor or ckpt_sag or ckpt_ax)
        
        if preprocess_from_ckpt:
            self.vox_size = preprocess_from_ckpt.get('VOX_SIZE', vox_size)
            self.image_size = preprocess_from_ckpt.get('IMG_SIZE', image_size)
            self.orientation = preprocess_from_ckpt.get('ORIENTATION', orientation)
            self.conform_to_1mm_threshold = preprocess_from_ckpt.get('THRESHOLD_1MM', conform_to_1mm_threshold)
            LOGGER.info(f"  Preprocessing: from checkpoint (vox_size={self.vox_size}, orientation={self.orientation})")
        else:
            try:
                self.vox_size = _vox_size(vox_size)
            except (ValueError,):
                raise ValueError(
                    f"Invalid vox_size value: '{vox_size}'. "
                    f"Must be a float between 0 and 1, or 'min'."
                ) from None
            self.conform_to_1mm_threshold = conform_to_1mm_threshold
            LOGGER.info(f"  Preprocessing: from CLI args (vox_size={self.vox_size}, orientation={orientation})")
            LOGGER.warning("  Checkpoint lacks preprocessing metadata - using CLI defaults")

    def _extract_preprocessing_params(self, checkpoint_path: Path | str | None) -> dict | None:
        """
        Extract preprocessing parameters from checkpoint config.
        
        Reads the checkpoint and extracts preprocessing settings like voxel size,
        orientation, and image size thresholds.
        
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
            checkpoint = read_checkpoint_file(checkpoint_path)
            
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

    def conform_image(
        self,
        image_path: str | Path,
        save_conformed: str | Path | None = None,
        save_original_copy: str | Path | None = None,
    ) -> tuple[nib.analyze.SpatialImage, np.ndarray]:
        """
        Load and conform an image to standard space.
        
        Generic function that works with any image file, not tied to FreeSurfer structure.

        Parameters
        ----------
        image_path : str, Path
            Path to the input image file.
        save_conformed : str, Path, optional
            If provided, save the conformed image to this path.
        save_original_copy : str, Path, optional
            If provided, save a copy of the original (unconformed) image to this path.

        Returns
        -------
        tuple[nib.analyze.SpatialImage, np.ndarray]
            Conformed image object and data array.
        """
        image_path = Path(image_path)
        orig, orig_data = data_utils.load_image(str(image_path), "input image")
        LOGGER.info(f"Successfully loaded image from {image_path}.")

        # Save copy of original image if requested
        if save_original_copy is not None:
            save_original_copy = Path(save_original_copy)
            save_original_copy.parent.mkdir(parents=True, exist_ok=True)
            self.async_save_img(save_original_copy, orig_data, orig, orig_data.dtype)

        # Conform image if needed
        if not is_conform(orig, **self.__conform_kwargs(verbose=True)):
            if (self.orientation is None or self.orientation == "native") and \
                    not is_conform(orig, **self.__conform_kwargs(verbose=False, dtype=None, vox_size="min")):
                LOGGER.warning("Support for anisotropic voxels is experimental. Careful QC of all images is needed!")
            LOGGER.info("Conforming image...")
            orig = conform(orig, **self.__conform_kwargs())
            orig_data = np.asanyarray(orig.dataobj)

        # Save conformed image if requested
        if save_conformed is not None:
            save_conformed = Path(save_conformed)
            save_conformed.parent.mkdir(parents=True, exist_ok=True)
            self.async_save_img(save_conformed, orig_data, orig, dtype=np.uint8)
            LOGGER.info(f"Saving conformed image to {save_conformed}...")

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
        self,
        image_name: str,
        img: nib.analyze.SpatialImage | None = None,
    ) -> np.ndarray:
        """
        Run and get prediction.

        Parameters
        ----------
        image_name : str
            Original image filename (used for logging/identification).
        img : nib.analyze.SpatialImage, optional
            Image object in native space. If None, will be loaded from image_name.
            Will be automatically conformed if needed, and context will be captured
            for automatic native space resampling in save_img().

        Returns
        -------
        np.ndarray
            Predicted classes.
        """
        # Load image if not provided
        if img is None:
            img = nib.load(image_name)
        
        # Store the native image and set up context for resampling
        conform_kwargs = {
            "threshold_1mm": self.conform_to_1mm_threshold,
            "vox_size": self.vox_size,
            "orientation": self.orientation,
            "img_size": self.image_size,
        }
        
        # Store input context for automatic resampling
        self._input_master_path = Path(image_name)
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
        pred_classes = data_utils.map_label2aparc_aseg(pred_classes, self.labels)
        # return numpy array
        pred_classes = pred_classes.cpu().numpy()
        
        # Apply FreeSurfer-specific post-processing only for FreeSurfer atlases
        if data_utils.is_freesurfer_lut(self.lut["ID"].values):
            LOGGER.info("Applying FreeSurfer-specific cortex label splitting")
            pred_classes = data_utils.split_cortex_labels(pred_classes)
        else:
            LOGGER.info("Skipping cortex label splitting (custom atlas)")
        
        # Apply WM island fixing (generic post-processing, enabled by default)
        if self.fix_wm_islands:
            LOGGER.info("Applying WM island correction (flipping mislabeled disconnected WM regions)...")
            pred_classes = flip_wm_islands_auto(pred_classes, lut_path=self.lut_path)
        else:
            LOGGER.info("Skipping WM island correction")
        
        return pred_classes

    def save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        dtype: type | None = None,
        resample_to_native: bool = True,
        interpolation: Literal["trilinear", "nearest"] = "trilinear",
    ) -> None:
        """
        Save image as a file, with automatic resampling back to native space.
        
        Uses the conformed image from the last get_prediction() call as reference.
        The image will be automatically resampled back to the original input's 
        native space if conforming was performed and resample_to_native is True.

        Parameters
        ----------
        save_as : str, Path
            Filename to give the image.
        data : np.ndarray, torch.Tensor
            Image data.
        dtype : type, optional
            Data type to use for saving the image. If None, the original data type is used.
        resample_to_native : bool, default=True
            If True, resample the image back to native space if conforming was performed.
            Set to False to keep the image in conformed space (e.g., for orig.mgz).
        interpolation : {"trilinear", "nearest"}, default="trilinear"
            Interpolation method for resampling. Use "nearest" for label/segmentation images
            to preserve discrete label values, "trilinear" for continuous images.
        """
        save_as = Path(save_as)
        # Create output directory if it does not already exist.
        if not save_as.parent.exists():
            LOGGER.info(f"Output image directory {save_as.parent} does not exist. Creating it now...")
            save_as.parent.mkdir(parents=True)

        # Use stored conformed image as reference
        if self._conformed_img is None:
            raise ValueError("save_img() requires get_prediction() to be called first")
        
        np_data = data if isinstance(data, np.ndarray) else data.cpu().numpy()
        if dtype is not None:
            _header = self._conformed_img.header.copy()
            _header.set_data_dtype(dtype)
        else:
            _header = self._conformed_img.header
        data_utils.save_image(_header, self._conformed_img.affine, np_data, save_as, dtype=dtype)
        LOGGER.info(f"Successfully saved image {'asynchronously ' if self._async_io else ''}as {save_as}.")
        
        # Automatically resample back to native space if context is available and requested
        if resample_to_native and self._input_master_path is not None and self._input_native_img is not None:
            # Check if resampling is needed
            if not is_conform(self._input_native_img, **self._conform_kwargs, verbose=True):
                LOGGER.info(f"Resampling {save_as.name} back to native space...")
                
                # Use FreeSurfer's mri_vol2vol for .mgz files, 3dresample for NIfTI files
                is_mgz = str(save_as).endswith('.mgz')
                
                if is_mgz:
                    # Use FreeSurfer's mri_vol2vol for .mgz files
                    command_resample = [
                        'mri_vol2vol',
                        '--mov', str(save_as),
                        '--targ', str(self._input_master_path),
                        '--o', str(save_as),
                        '--regheader'
                    ]
                    if interpolation == "nearest":
                        command_resample.extend(['--interp', 'nearest'])
                    tool_name = "mri_vol2vol"
                    tool_package = "FreeSurfer"
                else:
                    # Use AFNI's 3dresample for NIfTI files
                    command_resample = [
                        '3dresample',
                        '-input', str(save_as),
                        '-prefix', str(save_as),
                        '-master', str(self._input_master_path),
                        '-overwrite'
                    ]
                    if interpolation == "nearest":
                        command_resample.extend(['-rmode', 'NN'])
                    tool_name = "3dresample"
                    tool_package = "AFNI"
                
                try:
                    result = subprocess.run(
                        command_resample,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0:
                        LOGGER.info(f"Successfully resampled {save_as.name} back to native space")
                    else:
                        LOGGER.error(f"Failed to resample {save_as.name} back to native space: {result.stderr}")
                        raise RuntimeError(f"Failed to resample back to native space: {result.stderr}")
                except FileNotFoundError:
                    LOGGER.error(f"{tool_name} command not found. Please ensure {tool_package} is installed and in your PATH.")
                    raise RuntimeError(f"{tool_name} command not found. Please ensure {tool_package} is installed and in your PATH.")
            else:
                LOGGER.debug(f"Image {save_as.name} is already in native space, no resampling needed")

    def async_save_img(
        self,
        save_as: str | Path,
        data: np.ndarray | torch.Tensor,
        dtype: type | None = None,
        resample_to_native: bool = True,
    ) -> Future[None]:
        """
        Save the image asynchronously and return a concurrent.futures.Future to track,
        when this finished.
        
        Uses the conformed image from the last get_prediction() call as reference.
        The image will be automatically resampled back to the original input's 
        native space if conforming was performed and resample_to_native is True.

        Parameters
        ----------
        save_as : str, Path
            Filename to give the image.
        data : np.ndarray, torch.Tensor
            Image data.
        dtype : type, optional
            Data type to use for saving the image. If None, the original data type is used.
        resample_to_native : bool, default=True
            If True, resample the image back to native space if conforming was performed.
            Set to False to keep the image in conformed space (e.g., for orig.mgz).

        Returns
        -------
        Future[None]
            A Future object to synchronize (and catch/handle exceptions in the save_img method).
        """
        return self.pool.submit(self.save_img, save_as, data, dtype, resample_to_native)

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

##
# High-level API functions
##

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
    vox_size: VoxSizeOption = "min",
    orientation: OrientationType = "lia",
    image_size: bool = True,
    async_io: bool = False,
    conform_to_1mm_threshold: float = 0.95,
    plane_weight_coronal: float | None = None,
    plane_weight_axial: float | None = None,
    plane_weight_sagittal: float | None = None,
    fix_wm_islands: bool = True,
    seg_filename: str = "segmentation.mgz",
    mask_filename: str = "mask.mgz",
    hemimask_filename: str = "mask_hemi.mgz",
    resample_to_native: bool = True,
) -> dict[str, Path]:
    """
    Run segmentation and save outputs (segmentation, mask, hemimask) to output directory.
    
    This is a high-level convenience function that:
    1. Runs FastSurferCNN segmentation on the input image
    2. Creates brain mask and hemisphere mask from segmentation
    3. Saves all outputs to the specified output directory
    
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
    vox_size : VoxSizeOption, default="min"
        Voxel size option
    orientation : OrientationType, default="lia"
        Target orientation
    image_size : bool, default=True
        Whether to enforce standard image size
    async_io : bool, default=False
        Whether to use async I/O
    conform_to_1mm_threshold : float, default=0.95
        Threshold for conforming to 1mm resolution
    plane_weight_coronal, plane_weight_axial, plane_weight_sagittal : float, optional
        Weights for multi-view prediction
    fix_wm_islands : bool, default=True
        Whether to apply WM island correction
    seg_filename : str, default="segmentation.mgz"
        Filename for segmentation output (relative to output_dir)
    mask_filename : str, default="mask.mgz"
        Filename for brain mask output (relative to output_dir)
    hemimask_filename : str, default="mask_hemi.mgz"
        Filename for hemisphere mask output (relative to output_dir)
    resample_to_native : bool, default=True
        Whether to resample outputs back to native space
    
    Returns
    -------
    dict[str, Path]
        Dictionary with keys:
        - 'segmentation': Path to saved segmentation file
        - 'mask': Path to saved brain mask file
        - 'hemimask': Path to saved hemisphere mask file
        - 'conformed_image': Path to conformed image (if saved)
    """
    from FastSurferCNN.postprocessing.postseg_utils import create_mask, create_hemisphere_masks
    import copy
    
    input_image = Path(input_image)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate checkpoints
    validate_checkpoints(ckpt_ax, ckpt_cor, ckpt_sag)
    
    # Initialize predictor
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
        fix_wm_islands=fix_wm_islands,
    )
    
    # Run prediction
    LOGGER.info(f"Running segmentation on {input_image}")
    pred_data = predictor.get_prediction(str(input_image))
    
    # Save segmentation with nearest-neighbor interpolation to preserve label values
    seg_path = output_dir / seg_filename
    seg_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving segmentation to {seg_path}")
    predictor.save_img(seg_path, pred_data, dtype=np.int16, resample_to_native=resample_to_native, interpolation="nearest")
    
    # Load the resampled segmentation (now in native space if resampling was done)
    # This ensures masks are created from the correctly resampled segmentation
    LOGGER.info("Loading segmentation to create masks...")
    seg_img = nib.load(seg_path)
    pred_data_resampled = seg_img.get_fdata().astype(np.int16)
    
    # Create and save brain mask from resampled segmentation
    LOGGER.info("Creating brain mask from resampled segmentation...")
    brain_mask = create_mask(copy.deepcopy(pred_data_resampled), MASK_DILATION_SIZE, MASK_EROSION_SIZE)
    brain_mask = brain_mask.astype(np.uint8)
    
    mask_path = output_dir / mask_filename
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Saving brain mask to {mask_path}")
    # Save mask using the resampled segmentation's affine/header (already in native space)
    mask_header = seg_img.header.copy()
    mask_header.set_data_dtype(np.uint8)
    data_utils.save_image(mask_header, seg_img.affine, brain_mask, mask_path, dtype=np.uint8)
    
    # Create and save hemisphere mask from resampled segmentation
    LOGGER.info("Creating hemisphere mask from resampled segmentation...")
    try:
        hemi_mask = create_hemisphere_masks(brain_mask, pred_data_resampled, lut_path=predictor.lut_path)
        hemi_mask_path = output_dir / hemimask_filename
        hemi_mask_path.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.info(f"Saving hemisphere mask to {hemi_mask_path}")
        # Save hemimask using the resampled segmentation's affine/header (already in native space)
        hemi_header = seg_img.header.copy()
        hemi_header.set_data_dtype(np.uint8)
        data_utils.save_image(hemi_header, seg_img.affine, hemi_mask, hemi_mask_path, dtype=np.uint8)
    except Exception as e:
        LOGGER.warning(f"Could not create hemisphere mask: {e}")
        hemi_mask_path = None
    
    result = {
        'segmentation': seg_path,
        'mask': mask_path,
    }
    if hemi_mask_path is not None:
        result['hemimask'] = hemi_mask_path
    
    return result

