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
import time
from collections.abc import Callable, Sequence
from typing import Optional

import h5py
import numpy as np
import numpy.typing as npt
import torch
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

        if self.plane == "sagittal":
            orig_data = data_ultils.transform_sagittal(orig_data)
            self.zoom = np.asarray(orig_zoom)[[2, 1]]
            logger.info(f"Loading Sagittal with input voxelsize {self.zoom}")

        elif self.plane == "axial":
            orig_data = data_ultils.transform_axial(orig_data)
            self.zoom = np.asarray(orig_zoom)[[2, 0]]
            logger.info(f"Loading Axial with input voxelsize {self.zoom}")

        else:
            self.zoom = np.asarray(orig_zoom)[[0, 1]]
            logger.info(f"Loading Coronal with input voxelsize {self.zoom}")

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


# Operator to load hdf5-file for training
class MultiScaleDataset(Dataset):
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

        # Store dataset metadata (indices and sizes) without loading all data
        self.dataset_indices = []  # List of (size, index) tuples
        self.count = 0

        # Open file in reading mode to get metadata only
        start = time.time()
        with h5py.File(dataset_path, "r") as hf:
            for size in cfg.DATA.SIZES:
                try:
                    logger.info(f"Scanning size {size}...")
                    # Only get the length, don't load data
                    num_samples = len(hf[f"{size}"]["orig_dataset"])
                    logger.info(f"Found {num_samples} slices for size {size}")
                    
                    # Store indices for lazy loading
                    for idx in range(num_samples):
                        self.dataset_indices.append((size, idx))
                    
                    self.count += num_samples

                except KeyError:
                    logger.warning(
                        f"KeyError: Unable to open object (object {size} does not exist)"
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
            else:
                logger.info(
                    f"Successfully indexed {self.count} samples from {dataset_path} with plane {cfg.DATA.PLANE} " \
                    f"in {time.time() - start:.3f} seconds (using lazy loading)"
                )

    def _open_hdf5_file(self):
        """Open HDF5 file for reading (used for lazy loading)."""
        return h5py.File(self.dataset_path, "r", rdcc_nbytes=1024**3, rdcc_nslots=10000)
    
    def get_subject_names(self):
        """
        Get the subject name.

        Returns
        -------
        list
            List of subject names.
        """
        # Load subject names lazily when requested
        subjects = []
        with self._open_hdf5_file() as hf:
            for size, idx in self.dataset_indices:
                subject = hf[f"{size}"]["subject"][idx]
                if isinstance(subject, bytes):
                    subject = subject.decode('utf-8')
                subjects.append(subject)
        return subjects

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
        Pad the image with zeros.

        Parameters
        ----------
        image : npt.NDArray
            Image to pad.

        Returns
        -------
        padded_image
            Padded image.
        """
        if len(image.shape) == 2:
            h, w = image.shape
            padded_img = np.zeros((self.max_size, self.max_size), dtype=image.dtype)
        else:
            h, w, c = image.shape
            padded_img = np.zeros((self.max_size, self.max_size, c), dtype=image.dtype)

        if self.max_size < h:
            sub = h - self.max_size
            padded_img = image[0 : h - sub, 0 : w - sub]
        else:
            padded_img[0:h, 0:w] = image

        return padded_img

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
        # Lazy load data from HDF5 file
        size, idx = self.dataset_indices[index]
        
        with self._open_hdf5_file() as hf:
            image = hf[f"{size}"]["orig_dataset"][idx]
            label = hf[f"{size}"]["aseg_dataset"][idx]
            weight = hf[f"{size}"]["weight_dataset"][idx]
            zoom = hf[f"{size}"]["zoom_dataset"][idx]
        
        padded_img, padded_label, padded_weight = self.unify_imgs(
            image, label, weight
        )
        img = np.expand_dims(padded_img.transpose((2, 0, 1)), axis=3)
        label = padded_label[np.newaxis, :, :, np.newaxis]
        weight = padded_weight[np.newaxis, :, :, np.newaxis]

        import torchio as tio
        subject = tio.Subject(
            {
                "img": tio.ScalarImage(tensor=img),
                "label": tio.LabelMap(tensor=label),
                "weight": tio.LabelMap(tensor=weight),
            }
        )

        zoom_aug = torch.as_tensor([0.0, 0.0])

        if self.transforms is not None:
            tx_sample = self.transforms(subject)  # this returns data as torch.tensors

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
class MultiScaleDatasetVal(Dataset):
    """
    Class for loading aseg file with augmentations (transforms).
    """
    def __init__(self, dataset_path, cfg, transforms=None):

        self.max_size = cfg.DATA.PADDED_SIZE
        self.base_res = 1.0
        self.dataset_path = dataset_path
        self.transforms = transforms

        # Store dataset metadata (indices and sizes) without loading all data
        self.dataset_indices = []  # List of (size, index) tuples
        self.count = 0

        # Open file in reading mode to get metadata only
        start = time.time()
        with h5py.File(dataset_path, "r") as hf:
            for size in cfg.DATA.SIZES:
                try:
                    logger.info(f"Scanning size {size}...")
                    # Only get the length, don't load data
                    num_samples = len(hf[f"{size}"]["orig_dataset"])
                    logger.info(f"Found {num_samples} slices for size {size}")
                    
                    # Store indices for lazy loading
                    for idx in range(num_samples):
                        self.dataset_indices.append((size, idx))
                    
                    self.count += num_samples

                except KeyError:
                    logger.warning(
                        f"KeyError: Unable to open object (object {size} does not exist)"
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
        else:
            logger.info(
                f"Successfully indexed {self.count} samples from {dataset_path} with plane {cfg.DATA.PLANE} " \
                f"in {time.time() - start:.3f} seconds (using lazy loading)"
            )

    def _open_hdf5_file(self):
        """Open HDF5 file for reading (used for lazy loading)."""
        return h5py.File(self.dataset_path, "r", rdcc_nbytes=1024**3, rdcc_nslots=10000)
    
    def get_subject_names(self):
        """
        Get subject names.
        """
        # Load subject names lazily when requested
        subjects = []
        with self._open_hdf5_file() as hf:
            for size, idx in self.dataset_indices:
                subject = hf[f"{size}"]["subject"][idx]
                if isinstance(subject, bytes):
                    subject = subject.decode('utf-8')
                subjects.append(subject)
        return subjects

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
        # Lazy load data from HDF5 file
        size, idx = self.dataset_indices[index]
        
        with self._open_hdf5_file() as hf:
            img = hf[f"{size}"]["orig_dataset"][idx]
            label = hf[f"{size}"]["aseg_dataset"][idx]
            weight = hf[f"{size}"]["weight_dataset"][idx]
            zoom = hf[f"{size}"]["zoom_dataset"][idx]
        
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
