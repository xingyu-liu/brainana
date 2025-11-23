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
from numbers import Number, Real
from typing import Any

import numpy as np
import numpy.typing as npt
import torch


##
# Transformations for evaluation
##
class ToTensorTest:
    """
    Convert np.ndarrays in sample to Tensors.

    Methods
    -------
    __call__
        Converts image.
    """
    
    def __init__(self, rescale: float = 255.0):
        """
        Initialize ToTensorTest.
        
        Parameters
        ----------
        rescale : float
            Maximum value to normalize by (default: 255.0)
        """
        self.rescale = rescale

    def __call__(self, img: npt.NDArray) -> np.ndarray:
        """
        Convert the image to float within range [0, 1] and make it torch compatible.

        Parameters
        ----------
        img : npt.NDArray
            Image to be converted.

        Returns
        -------
        img : np.ndarray
            Conformed image.
        """
        img = img.astype(np.float32)

        # Normalize HDF5 data from [0, rescale] to [0, 1] range
        # Uses RESCALE value from config (typically 255.0)
        img = np.clip(img / self.rescale, a_min=0.0, a_max=1.0)

        # swap color axis because
        # numpy image: H x W x C
        # torch image: C X H X W
        img = img.transpose((2, 0, 1))

        return img


##
# Transformations for training
##
class ToTensor:
    """
    Convert ndarrays in sample to Tensors.
    
    Methods
    -------
    __call__
        Convert image.
    """
    
    def __init__(self, rescale: float = 255.0):
        """
        Initialize ToTensor.
        
        Parameters
        ----------
        rescale : float
            Maximum value to normalize by (default: 255.0)
        """
        self.rescale = rescale

    def __call__(self, sample: npt.NDArray) -> dict[str, Any]:
        """
        Convert the image to float within range [0, 1] and make it torch compatible.

        Parameters
        ----------
        sample : npt.NDArray
            Sample image.

        Returns
        -------
        Dict[str, Any]
            Converted image.
        """
        img, label, weight, sf = (
            sample["img"],
            sample["label"],
            sample["weight"],
            sample["scale_factor"],
        )
        
        img = img.astype(np.float32)

        # Normalize HDF5 data from [0, rescale] to [0, 1] range
        # Uses RESCALE value from config (typically 255.0)
        img = np.clip(img / self.rescale, a_min=0.0, a_max=1.0)

        # swap color axis because
        # numpy image: H x W x C
        # torch image: C X H X W
        img = img.transpose((2, 0, 1))

        return {
            "img": torch.from_numpy(img),
            "label": torch.from_numpy(label),
            "weight": torch.from_numpy(weight),
            "scale_factor": torch.from_numpy(sf),
        }


class Pad2D:
    """
    Pad image(s) to target size. Supports both edge padding and zero padding.
    
    Unified padding transform that works for both:
    - Single images (inference): takes npt.NDArray, returns np.ndarray
    - Sample dicts (training): takes dict with "img", "label", "weight", returns dict
    
    Edge padding replicates edge pixels (better for boundary performance).
    Zero padding fills with zeros.

    Attributes
    ----------
    output_size : Union[Number, Tuple[Number, Number]]
        Size of the output image either as Number or tuple of two Number.
    mode : str
        Padding mode: 'edge' (replicates edge pixels) or 'zero' (fills with zeros).
        Defaults to 'edge'.
    pos : str, Optional
        Position to put the input. Default = 'top_left'.

    Methods
    -------
    __call__
        Pads image(s) with specified mode.
    """
    def __init__(
            self,
            output_size: Number | tuple[Number, Number],
            mode: str = 'edge',
            pos: None | str = 'top_left'
    ):
        """
        Initialize padding transform.

        Parameters
        ----------
        output_size : Union[Number, Tuple[Number, Number]]
            Size of the output image either as Number or tuple of two Number.
        mode : str, default='edge'
            Padding mode: 'edge' (replicates edge pixels) or 'zero' (fills with zeros).
        pos : str, Optional
            Position to put the input. Default = 'top_left'.
        """
        from FastSurferCNN.data_loader.data_utils import pad_to_size
        if isinstance(output_size, Number):
            output_size = (int(output_size),) * 2
        self.output_size = output_size
        if mode not in ['edge', 'zero']:
            raise ValueError(f"mode must be 'edge' or 'zero', got '{mode}'")
        self.mode = mode
        self.pos = pos
        self._pad_to_size = pad_to_size

    def __call__(self, input_data: npt.NDArray | dict[str, Any]) -> np.ndarray | dict[str, Any]:
        """
        Pad image(s) with specified mode.

        Parameters
        ----------
        input_data : npt.NDArray or dict[str, Any]
            Either a single image array (inference) or a dict with "img", "label", "weight" keys (training).

        Returns
        -------
        np.ndarray or dict[str, Any]
            Padded image(s) with same type as input.
        """
        # Handle single image (inference case)
        if isinstance(input_data, np.ndarray):
            return self._pad_to_size(input_data, self.output_size, mode=self.mode, pos=self.pos)
        
        # Handle sample dict (training case)
        if isinstance(input_data, dict):
            img, label, weight, sf = (
                input_data["img"],
                input_data["label"],
                input_data["weight"],
                input_data["scale_factor"],
            )
            
            img = self._pad_to_size(img, self.output_size, mode=self.mode, pos=self.pos)
            label = self._pad_to_size(label, self.output_size, mode=self.mode, pos=self.pos)
            weight = self._pad_to_size(weight, self.output_size, mode=self.mode, pos=self.pos)

            return {"img": img, "label": label, "weight": weight, "scale_factor": sf}
        
        raise TypeError(f"Pad2D expects np.ndarray or dict, got {type(input_data)}")


class AddGaussianNoise:
    """
    Add gaussian noise to sample.

    Attributes
    ----------
    std
        Standard deviation.
    mean
        Gaussian mean.

    Methods
    -------
    __call__
        Adds noise to scale factor.
    """
    def __init__(self, mean: Real = 0, std: Real = 0.1):
        """
        Construct object.

        Parameters
        ----------
        mean : Real
            Standard deviation. Default = 0.
        std : Real
            Gaussian mean. Default = 0.1.
        """
        self.std = std
        self.mean = mean

    def __call__(self, sample: dict[str, Real]) -> dict[str, Real]:
        """
        Add gaussian noise to scalefactor.

        Parameters
        ----------
        sample : Dict[str, Real]
            Sample data to add noise.

        Returns
        -------
        Dict[str, Real]
            Sample with noise.
        """
        img, label, weight, sf = (
            sample["img"],
            sample["label"],
            sample["weight"],
            sample["scale_factor"],
        )
        # change 1 to sf.size() for isotropic scale factors (now same noise change added to both dims)
        sf = sf + torch.randn(1) * self.std + self.mean
        return {"img": img, "label": label, "weight": weight, "scale_factor": sf}


class AugmentationPadImage:
    """
    Pad Image with symmetric padding on all sides for augmentation.
    
    This is different from Pad2D which pads to a target size. This class adds
    symmetric padding (same amount on all sides) which is useful for augmentation
    operations that need border space.

    Attributes
    ----------
    pad_size : int or tuple
        Padding size. If int, applies same padding to all sides.
    pad_type : str
        Padding mode ('edge', 'zero', etc.)

    Methods
    -------
    __call__
        Adds symmetric padding to img, label, and weight.
    """
    def __init__(
            self,
            pad_size: int | tuple[tuple[int, int], tuple[int, int]] = 16,
            pad_type: str = "edge"
    ):
        """
        Construct object.

        Parameters
        ----------
        pad_size : int or tuple
            Padding size. If int, applies same padding to all sides.
            If tuple, should be ((top, bottom), (left, right)) format.
        pad_type : str, default="edge"
            Padding mode ('edge', 'zero', etc.)
        """
        if isinstance(pad_size, int):
            # Symmetric padding: same amount on all sides
            # Do not pad along the channel dimension
            self.pad_size_image = ((pad_size, pad_size), (pad_size, pad_size), (0, 0))
            self.pad_size_mask = ((pad_size, pad_size), (pad_size, pad_size))
        else:
            # Custom padding tuple
            self.pad_size_image = pad_size + ((0, 0),)  # Add channel dimension
            self.pad_size_mask = pad_size

        self.pad_type = pad_type

    def __call__(self, sample: dict[str, Number]):
        """
        Add symmetric padding to sample image, label and weight.

        Parameters
        ----------
        sample : Dict[str, Number]
            Sample image and data.

        Returns
        -------
        Dict[str, Number]
            Sample with padded image, label, and weight.
        """
        img, label, weight, sf = (
            sample["img"],
            sample["label"],
            sample["weight"],
            sample["scale_factor"],
        )

        # Use np.pad directly for symmetric padding (different from pad_to_size which pads to target size)
        img = np.pad(img, self.pad_size_image, self.pad_type)
        label = np.pad(label, self.pad_size_mask, self.pad_type)
        weight = np.pad(weight, self.pad_size_mask, self.pad_type)

        return {"img": img, "label": label, "weight": weight, "scale_factor": sf}


class AugmentationRandomCrop:
    """
    Randomly Crop Image to given size.
    """

    def __init__(self, output_size: int | tuple, crop_type: str = 'Random'):
        """Construct object.

        Attributes
        ----------
        output_size
            Size of the output image either an integer or a tuple.
        crop_type
        The type of crop to be performed.
        """
        assert isinstance(output_size, int | tuple)

        if isinstance(output_size, int):
            self.output_size = (output_size, output_size)

        else:
            self.output_size = output_size

        self.crop_type = crop_type

    def __call__(self, sample: dict[str, Number]) -> dict[str, Number]:
        """
        Crops the augmentation.

        Attributes
        ----------
        sample : Dict[str, Number]
            Sample image with data.

        Returns
        -------
        Dict[str, Number]
            Cropped sample image.
        """
        img, label, weight, sf = (
            sample["img"],
            sample["label"],
            sample["weight"],
            sample["scale_factor"],
        )

        h, w, _ = img.shape

        if self.crop_type == "Center":
            top = (h - self.output_size[0]) // 2
            left = (w - self.output_size[1]) // 2

        else:
            top = np.random.randint(0, h - self.output_size[0])
            left = np.random.randint(0, w - self.output_size[1])

        bottom = top + self.output_size[0]
        right = left + self.output_size[1]

        # print(img.shape)
        img = img[top:bottom, left:right, :]
        label = label[top:bottom, left:right]
        weight = weight[top:bottom, left:right]

        return {"img": img, "label": label, "weight": weight, "scale_factor": sf}

