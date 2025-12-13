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

# IMPORTS
import os
import time
from collections.abc import Callable, Sequence
from typing import Optional

import h5py
import numpy as np
import numpy.typing as npt
import torch
import torchio as tio
import yacs.config
from torch.utils.data import Dataset

from FastSurferCNN.data_loader import data_utils as data_ultils
from FastSurferCNN.utils import logging

logger = logging.getLogger(__name__)


# Operator to load imaged for inference
class MultiScaleOrigDataThickSlices(Dataset):
    """
    Load MRI-Image and process it to correct format for network inference.
    """

    zoom : npt.NDArray[float]

    def __init__(
            self,
            orig_data: npt.NDArray,
            orig_zoom: npt.NDArray[float] | Sequence[float],
            cfg: yacs.config.CfgNode,
            transforms: Callable[[npt.NDArray[float]], npt.NDArray[float]] | None = None,
    ):
        """
        Construct object.

        Parameters
        ----------
        orig_data : npt.NDArray
            Original Data.
        orig_zoom : npt.NDArray
            Original zoom factors.
        cfg : yacs.config.CfgNode
            Configuration Node.
        transforms : callable[[npt.NDArray[float]], npt.NDArray[float]], optional
            Transforms for the image, defaults to no transformation.
        """
        orig_max = orig_data.max()
        assert orig_max > 0.8, f"Multi Dataset - orig fail, max removed {orig_max}"
        self.plane = cfg.DATA.PLANE
        self.slice_thickness = cfg.MODEL.NUM_CHANNELS // 2
        self.base_res = 1.0

        # Handle mixed plane mode - should not reach here with "mixed", but safety check
        if self.plane == "mixed":
            raise ValueError(
                "MultiScaleOrigDataThickSlices received PLANE='mixed'. "
                "For mixed-plane models, plane should be set to specific plane (axial/coronal/sagittal) "
                "before creating dataset. This is handled automatically in Inference.run()."
            )

        # Get orientation from config (default to 'lia' for backward compatibility)
        orientation = getattr(cfg.DATA.PREPROCESSING, 'ORIENTATION', 'lia')
        
        # Use orientation-aware transform for any plane
        orig_data = data_ultils.transform_for_plane(orig_data, self.plane, orientation)
        zoom_indices = data_ultils.get_zoom_indices_for_plane(self.plane, orientation)
        self.zoom = np.asarray(orig_zoom)[list(zoom_indices)]
        logger.info(f"Dataset: loading {self.plane} plane with voxelsize {self.zoom} (orientation: {orientation})")

        # Create thick slices
        orig_thick = data_ultils.get_thick_slices(orig_data, self.slice_thickness)
        orig_thick = np.transpose(orig_thick, (2, 0, 1, 3))
        self.images = orig_thick
        self.count = self.images.shape[0]
        self.transforms = transforms

    def _get_scale_factor(self) -> npt.NDArray[float]:
        """
        Get scaling factor to match original resolution of input image to final resolution of FastSurfer base network.

        Input resolution is taken from voxel size in image header.

        Returns
        -------
        npt.NDArray[float]
            Scale factor along x and y dimension.
        """
        # Safeguard against division by zero or invalid zoom values
        zoom = np.asarray(self.zoom)
        # Replace zero or very small values with base_res to get scale factor of 1.0
        zoom = np.where(np.abs(zoom) < 1e-6, self.base_res, zoom)
        scale = self.base_res / zoom

        return scale

    def __getitem__(self, index: int) -> dict:
        """
        Return a single image and its scale factor.

        Parameters
        ----------
        index : int
            Index of image to get.

        Returns
        -------
        dict
            Dictionary of image and scale factor.
        """
        img = self.images[index]

        scale_factor = self._get_scale_factor()
        if self.transforms is not None:
            img = self.transforms(img)

        return {"image": img, "scale_factor": scale_factor}

    def __len__(self) -> int:
        """
        Return length.

        Returns
        -------
        int
            Count.
        """
        return self.count


# Base class for HDF5-based datasets with shared file handling
class HDF5DatasetBase(Dataset):
    """
    Base class for HDF5-based datasets with optimized file handling.
    Provides shared methods for opening and managing HDF5 file handles.
    """
    
    def _get_hdf5_file(self):
        """
        Get persistent HDF5 file handle (opened lazily on first access).
        The file remains open for the lifetime of the dataset to avoid repeated open/close operations.
        Each worker process gets its own dataset instance, so this is safe for multiprocessing.
        """
        if self._hdf5_file is None:
            # Optimized cache settings for read-heavy workloads with slow network storage
            # With single worker, we can use a very large cache to minimize I/O
            # rdcc_nbytes: cache size in bytes (8GB for large datasets on network storage)
            # rdcc_nslots: number of hash table slots (larger = less collisions)
            # rdcc_w0: write policy (0.0 = no write caching, pure read cache)
            # Note: Large cache helps when I/O is slow (network mounts)
            self._hdf5_file = h5py.File(
                self.dataset_path, 
                "r", 
                rdcc_nbytes=8*1024**3,  # Increased to 8GB cache for network storage
                rdcc_nslots=100000,      # More slots for better cache hit rate
                rdcc_w0=0.0               # Pure read cache (no write caching)
            )
        return self._hdf5_file
    
    def _open_hdf5_file(self):
        """
        Legacy method for backward compatibility.
        Now returns the persistent file handle instead of creating a new one.
        """
        return self._get_hdf5_file()
    
    def get_subject_names(self):
        """
        Get subject names from the HDF5 dataset.

        Returns
        -------
        list
            List of subject names.
        """
        # Load subject names lazily when requested
        subjects = []
        hf = self._get_hdf5_file()
        for size, idx in self.dataset_indices:
            subject = hf[f"{size}"]["subject"][idx]
            if isinstance(subject, bytes):
                subject = subject.decode('utf-8')
            subjects.append(subject)
        return subjects
    
    def _scan_hdf5_indices(self, dataset_path: str, cfg: yacs.config.CfgNode):
        """
        Scan HDF5 file to build dataset indices without loading all data.
        Shared initialization logic for both training and validation datasets.
        
        Parameters
        ----------
        dataset_path : str
            Path to the HDF5 file
        cfg : yacs.config.CfgNode
            Configuration node with DATA.SIZES
        """
        self.dataset_indices = []  # List of (size, index) tuples
        self.count = 0
        
        # Open file in reading mode to get metadata only
        with h5py.File(dataset_path, "r") as hf:
            for size in cfg.DATA.SIZES:
                try:
                    logger.info(f"Dataset: scanning size {size}...")
                    # Only get the length, don't load data
                    num_samples = len(hf[f"{size}"]["orig_dataset"])
                    logger.info(f"Dataset: found {num_samples} slices for size {size}")
                    
                    # Store indices for lazy loading
                    for idx in range(num_samples):
                        self.dataset_indices.append((size, idx))
                    
                    self.count += num_samples

                except KeyError:
                    logger.warning(
                        f"Dataset: key error, size {size} does not exist in HDF5 file"
                    )
                    continue

        if self.count == 0:
            logger.error(
                f"WARNING: No samples found in HDF5 file!\n"
                f"  File: {dataset_path}\n"
                f"  Plane: {cfg.DATA.PLANE}\n"
                f"  Expected sizes: {cfg.DATA.SIZES}\n"
                f"  This will cause training to fail. Please check:\n"
                f"    1. HDF5 file was created successfully\n"
                f"    2. Subjects were processed during HDF5 creation\n"
                f"    3. HDF5 file structure matches expected sizes\n"
                f"    4. Data split file includes subjects for this split"
            )
    
    def __del__(self):
        """Cleanup: close HDF5 file if it was opened."""
        if self._hdf5_file is not None:
            try:
                self._hdf5_file.close()
            except Exception:
                pass  # Ignore errors during cleanup


# Operator to load hdf5-file for training
class MultiScaleDataset(HDF5DatasetBase):
    """
    Class for loading aseg file with augmentations (transforms).
    """

    def __init__(
            self,
            dataset_path: str,
            cfg: yacs.config.CfgNode,
            gn_noise: bool = False,
            transforms: Optional = None
    ):
        """
        Construct object.

        Parameters
        ----------
        dataset_path : str
            Path to the dataset.
        cfg : yacs.config.CfgNode
            Configuration node.
        gn_noise : bool
            Whether to add gaussian noise (Default value = False).
        transforms : Optional
            Transformer to apply to the image (Default value = None).
        """
        self.max_size = cfg.DATA.PADDED_SIZE
        self.base_res = 1.0
        self.rescale = cfg.DATA.PREPROCESSING.RESCALE
        self.gn_noise = gn_noise
        self.dataset_path = dataset_path
        self.transforms = transforms

        # Persistent HDF5 file handle (opened lazily, kept open for lifetime of dataset)
        # Each worker process gets its own dataset instance, so this is safe for multiprocessing
        self._hdf5_file = None

        # Scan HDF5 file to build indices (shared method from base class)
        self._scan_hdf5_indices(dataset_path, cfg)

    def _get_scale_factor(
            self,
            img_zoom: torch.Tensor,
            scale_aug: torch.Tensor
    ) -> npt.NDArray[float]:
        """
        Get scaling factor to match original resolution of input image to final resolution of FastSurfer base network.

        Input resolution is taken from voxel size in image header.


        Parameters
        ----------
        img_zoom : torch.Tensor
            Image zoom factor.
        scale_aug : torch.Tensor
            Scale augmentation factor.

        Returns
        -------
        npt.NDArray[float]
            Scale factor along x and y dimension.
        """
        if torch.all(scale_aug > 0):
            img_zoom *= 1 / scale_aug

        # Safeguard against division by zero or invalid zoom values
        # Replace zero or very small values with base_res to get scale factor of 1.0
        img_zoom = torch.where(torch.abs(img_zoom) < 1e-6, torch.tensor(self.base_res), img_zoom)
        
        scale = self.base_res / img_zoom

        if self.gn_noise:
            scale += torch.randn(1) * 0.1 + 0  # needs to be changed to torch.tensor stuff
            scale = torch.clamp(scale, min=0.1)

        return scale

    def _pad(
            self,
            image: npt.NDArray
    ) ->  np.ndarray:
        """
        Pad the image with edge values (replicates edge pixels) instead of zeros.
        This helps the model perform better at boundaries by avoiding artificial zero-padded edges.

        Parameters
        ----------
        image : npt.NDArray
            Image to pad.

        Returns
        -------
        padded_image
            Padded image.
        """
        from FastSurferCNN.data_loader.data_utils import pad_to_size
        
        # Use unified padding function with edge mode (handles cropping internally if needed)
        return pad_to_size(image, self.max_size, mode='edge', pos='top_left')

    def unify_imgs(
            self,
            img: npt.NDArray,
            label: npt.NDArray,
            weight: npt.NDArray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Pad img, label and weight.

        Parameters
        ----------
        img : npt.NDArray
            Image to unify.
        label : npt.NDArray
            Labels of the image.
        weight : npt.NDArray
            Weights of the image.

        Returns
        -------
        np.ndarray
            Img.
        np.ndarray
            Label.
        np.ndarray
            Weight.
        """
        img = self._pad(img)
        label = self._pad(label)
        weight = self._pad(weight)

        return img, label, weight

    def __getitem__(self, index):
        """
        Retrieve processed data at the specified index.

        Parameters
        ----------
        index : int
            Index to retrieve data for.

        Returns
        -------
        dict
            Dictionary containing torch tensors for image, label, weight, and scale factor.
        """
        import time
        total_start = time.time()
        
        # Lazy load data from HDF5 file using persistent handle
        size, idx = self.dataset_indices[index]
        
        # Time HDF5 loading
        # Optimized: Access all datasets from same group to minimize file seeks
        hdf5_start = time.time()
        hf = self._get_hdf5_file()
        size_group = hf[f"{size}"]
        # Read all arrays in sequence to minimize I/O overhead
        image = size_group["orig_dataset"][idx]
        label = size_group["aseg_dataset"][idx]
        weight = size_group["weight_dataset"][idx]
        zoom = size_group["zoom_dataset"][idx]
        hdf5_time = time.time() - hdf5_start
        
        # Time padding
        pad_start = time.time()
        padded_img, padded_label, padded_weight = self.unify_imgs(
            image, label, weight
        )
        pad_time = time.time() - pad_start
        
        img = np.expand_dims(padded_img.transpose((2, 0, 1)), axis=3)
        label = padded_label[np.newaxis, :, :, np.newaxis]
        weight = padded_weight[np.newaxis, :, :, np.newaxis]

        subject = tio.Subject(
            {
                "img": tio.ScalarImage(tensor=img),
                "label": tio.LabelMap(tensor=label),
                "weight": tio.LabelMap(tensor=weight),
            }
        )

        zoom_aug = torch.as_tensor([0.0, 0.0])

        if self.transforms is not None:
            # Time augmentation
            aug_start = time.time()
            tx_sample = self.transforms(subject)  # this returns data as torch.tensors
            aug_time = time.time() - aug_start
        else:
            aug_time = 0.0
            tx_sample = subject

        total_time = time.time() - total_start
        
        # Log slow samples with detailed breakdown - these block the batch!
        # Lowered threshold to 1.0s to catch moderately slow samples that still cause issues
        if total_time > 5.0:
            logger.warning(
                f"⚠️  SLOW SAMPLE: {total_time:.2f}s total for sample {index} "
                f"(size={size}, idx={idx})\n"
                f"   Breakdown: HDF5={hdf5_time:.3f}s, Padding={pad_time:.3f}s, "
                f"Augmentation={aug_time:.3f}s\n"
            )
        # Log moderately slow augmentations (lowered threshold)
        elif aug_time > 2.0:
            logger.info(
                f"Slow augmentation: {aug_time:.3f}s for sample {index} "
                f"(size={size}, idx={idx})"
            )

        if self.transforms is not None:
            img = torch.squeeze(tx_sample["img"].data).float()
            label = torch.squeeze(tx_sample["label"].data).byte()
            weight = torch.squeeze(tx_sample["weight"].data).float()

            # get updated scalefactor, in case of scaling, not ideal - fails if scales is not in dict
            rep_tf = tx_sample.get_composed_history()
            if rep_tf:
                zoom_aug += torch.as_tensor(
                    rep_tf[0]._get_reproducing_arguments()["scales"]
                )[:-1]

            # Normalize HDF5 data from [0, rescale] to [0, 1] range
            # Uses RESCALE value from config (typically 255.0)
            img = torch.clamp(img / self.rescale, min=0.0, max=1.0)
        else:
            # No transforms - convert directly
            img = torch.from_numpy(img).float()
            label = torch.from_numpy(label).byte()
            weight = torch.from_numpy(weight).float()
            img = torch.clamp(img / self.rescale, min=0.0, max=1.0)

        scale_factor = self._get_scale_factor(
            torch.from_numpy(zoom), scale_aug=zoom_aug
        )

        return {
            "image": img,
            "label": label,
            "weight": weight,
            "scale_factor": scale_factor,
        }

    def __len__(self):
        """
        Return count.
        """
        return self.count


# Operator to load hdf5-file for validation
class MultiScaleDatasetVal(HDF5DatasetBase):
    """
    Class for loading aseg file with augmentations (transforms).
    """
    def __init__(self, dataset_path, cfg, transforms=None):

        self.max_size = cfg.DATA.PADDED_SIZE
        self.base_res = 1.0
        self.dataset_path = dataset_path
        self.transforms = transforms

        # Persistent HDF5 file handle (opened lazily, kept open for lifetime of dataset)
        # Each worker process gets its own dataset instance, so this is safe for multiprocessing
        self._hdf5_file = None

        # Scan HDF5 file to build indices (shared method from base class)
        self._scan_hdf5_indices(dataset_path, cfg)

    def _get_scale_factor(self, img_zoom):
        """
        Get scaling factor to match original resolution of input image to final resolution of FastSurfer base network.

        Input resolution is taken from voxel size in image header.
        
        Parameters
        ----------
        img_zoom : np.ndarray
            Voxel sizes of the image.

        Returns
        -------
        np.ndarray : numpy.typing.NDArray[float]
            Scale factor along x and y dimension.
        """
        # Safeguard against division by zero or invalid zoom values
        img_zoom = np.asarray(img_zoom)
        # Replace zero or very small values with base_res to get scale factor of 1.0
        img_zoom = np.where(np.abs(img_zoom) < 1e-6, self.base_res, img_zoom)
        scale = self.base_res / img_zoom
        return scale

    def __getitem__(self, index):
        """
        Get item.
        """
        # Lazy load data from HDF5 file using persistent handle
        size, idx = self.dataset_indices[index]
        
        # Use persistent file handle (no context manager - file stays open)
        # Optimized: Access all datasets from same group to minimize file seeks
        hf = self._get_hdf5_file()
        size_group = hf[f"{size}"]
        # Read all arrays in sequence to minimize I/O overhead
        img = size_group["orig_dataset"][idx]
        label = size_group["aseg_dataset"][idx]
        weight = size_group["weight_dataset"][idx]
        zoom = size_group["zoom_dataset"][idx]
        
        scale_factor = self._get_scale_factor(zoom)

        if self.transforms is not None:
            tx_sample = self.transforms(
                {
                    "img": img,
                    "label": label,
                    "weight": weight,
                    "scale_factor": scale_factor,
                }
            )

            img = tx_sample["img"]
            label = tx_sample["label"]
            weight = tx_sample["weight"]
            scale_factor = tx_sample["scale_factor"]

        return {
            "image": img,
            "label": label,
            "weight": weight,
            "scale_factor": scale_factor,
        }

    def __len__(self):
        """
        Get count.
        """
        return self.count
