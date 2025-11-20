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
Multi-view predictor for brain segmentation.

This module contains the RunModelOnData class which orchestrates
multi-view inference across axial, coronal, and sagittal planes.
"""

from pathlib import Path
from typing import Any, Literal

import nibabel as nib
import numpy as np
import torch

from FastSurferCNN.atlas.atlas_manager import AtlasManager
from FastSurferCNN.data_loader import data_utils
from FastSurferCNN.data_loader.conform import (
    conform,
    is_conform,
    map_image,
)
from FastSurferCNN.inference.inference import Inference
from FastSurferCNN.inference.predictor_utils import load_multiplane_configs
from FastSurferCNN.postprocessing.postseg_utils import flip_wm_islands_auto
from FastSurferCNN.utils import Plane, logging
from FastSurferCNN.utils.arg_types import OrientationType
from FastSurferCNN.utils.arg_types import vox_size as _vox_size
from FastSurferCNN.utils.checkpoint import read_checkpoint_file
from FastSurferCNN.utils.common import find_device

LOGGER = logging.getLogger(__name__)


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
    fix_wm_islands : bool
        Whether to apply white matter island correction.

    Methods
    -------
    __init__()
        Construct predictor object.
    get_prediction(image_f, img)
        Run inference and return prediction array (in model space).
    _should_resample()
        Check if resampling to native space is needed.
    _resample_to_native(data, interpolation)
        Resample data from model space to native input space (pure Python).
    set_model(plane)
        Set the current model plane.
    get_num_classes()
        Get number of segmentation classes.
    """

    vox_size: float | Literal["min"]
    current_plane: Plane
    models: dict[Plane, Inference]
    view_ops: dict[Plane, dict[str, Any]]
    device: torch.device
    viewagg_device: torch.device
    orientation: OrientationType

    def __init__(
        self,
        atlas_name: str | None,
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
        atlas_name : str | None
            Name of the atlas (e.g., "ARM2", "ARM3") for multi-class tasks.
            None for binary brain mask tasks (NUM_CLASSES=2).
        atlas_metadata : dict, optional
            Atlas metadata extracted from checkpoint. Required for multi-class tasks.
            For binary tasks, should have is_binary_task=True.
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

        # Load configs first to determine if binary mode
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
        self.is_binary = (self.num_classes == 2)
        self.atlas_name = atlas_name  # Store for later use (e.g., FreeSurfer detection)
        
        # Initialize atlas and LUT based on mode
        if self.is_binary:
            # Binary brain mask mode - no atlas needed
            LOGGER.info(f"Binary segmentation mode detected (NUM_CLASSES={self.num_classes})")
            LOGGER.info("No atlas mapping required for brain mask task")
            self.labels = None
            self.torch_labels = None
            self.lut_path = None
            self.lut = None
        else:
            # Multi-class mode - require atlas
            if atlas_name is None:
                raise ValueError(
                    "Multi-class mode requires atlas_name. "
                    "For binary brain mask (NUM_CLASSES=2), use NUM_CLASSES=2 in checkpoint."
                )
            
            LOGGER.info(f"Multi-class segmentation mode (NUM_CLASSES={self.num_classes})")
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
            # Require atlas_metadata from checkpoint (no fallbacks)
            if not atlas_metadata or atlas_metadata.get("dense_to_sparse_mapping") is None:
                raise RuntimeError(
                    f"Multi-class mode requires atlas metadata with dense_to_sparse_mapping. "
                    f"Checkpoint for atlas '{atlas_name}' is missing required metadata. "
                    f"Please ensure the checkpoint was saved with atlas_metadata."
                )
            
            # Use the exact mapping from checkpoint
            self.labels = atlas_metadata["dense_to_sparse_mapping"]
            self.torch_labels = torch.from_numpy(self.labels)
            LOGGER.info(
                f"  Label mapping: from checkpoint ({len(self.labels)} classes)"
            )

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

        # Validate that all required parameters are present
        missing_params = []
        if self.vox_size is None:
            missing_params.append("VOX_SIZE")
        if self.image_size is None:
            missing_params.append("IMG_SIZE")
        if self.orientation is None:
            missing_params.append("ORIENTATION")

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

        # Store conformed image
        self._conformed_img = img

        # Extract data and zoom from conformed image
        orig_data = np.asanyarray(img.dataobj)
        zoom = img.header.get_zooms()

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

        # Use conformed data directly - conforming already ensures correct orientation
        # (matching training configuration from checkpoint)
        shape = orig_data.shape + (self.get_num_classes(),)
        pred_prob = torch.zeros(shape, **kwargs)

        # Inference and view aggregation
        for plane, model in self.models.items():
            LOGGER.info(f"Run {plane} prediction")
            self.set_model(plane)
            # pred_prob is updated inplace to conserve memory
            pred_prob = model.run(
                pred_prob, image_f, orig_data, _zoom, out=pred_prob
            )

        # Get hard predictions
        pred_classes = torch.argmax(pred_prob, 3)
        del pred_prob

        # Map to FreeSurfer label space (skip for binary models - output is already 0/1)
        if not self.is_binary and self.labels is not None:
            pred_classes = data_utils.map_label2aparc_aseg(
                pred_classes, self.labels
            )

        # Return numpy array
        pred_classes = pred_classes.cpu().numpy()


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

