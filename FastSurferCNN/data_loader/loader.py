# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
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
import yacs.config
from torch.utils.data import DataLoader
from torchvision import transforms

from FastSurferCNN.data_loader import dataset as dset
from FastSurferCNN.data_loader.augmentation import AddGaussianNoise, ToTensor, ZeroPad2D
from FastSurferCNN.utils import logging

logger = logging.getLogger(__name__)


def get_dataloader(cfg: yacs.config.CfgNode, mode: str):
    """
    Create the dataset and pytorch data loader.

    Parameters
    ----------
    cfg : yacs.config.CfgNode
        Configuration node.
    mode : str
        Loading data for train, val and test mode.

    Returns
    -------
    torch.utils.data.DataLoader
        Dataloader with given configs and mode.
    """
    assert mode in ["train", "val"], f"dataloader mode is incorrect {mode}"

    padding_size = cfg.DATA.PADDED_SIZE

    if mode == "train":

        if "None" in cfg.DATA.AUG:
            tfs = [ZeroPad2D((padding_size, padding_size)), ToTensor()]
            # old transform
            if "Gaussian" in cfg.DATA.AUG:
                tfs.append(AddGaussianNoise(mean=0, std=0.1))

            data_path = cfg.DATA.PATH_HDF5_TRAIN
            shuffle = True

            logger.info(
                f"Loading {mode.capitalize()} data ... from {data_path}. Using standard Aug"
            )

            dataset = dset.MultiScaleDatasetVal(data_path, cfg, transforms.Compose(tfs))
        else:

            import torchio as tio
            # Elastic
            elastic = tio.RandomElasticDeformation(
                num_control_points=7,
                max_displacement=(20, 20, 0),
                locked_borders=2,
                image_interpolation="linear",
                include=["img", "label", "weight"],
            )
            # Scales
            scaling = tio.RandomAffine(
                scales=(0.8, 1.15),
                degrees=0,
                translation=(0, 0, 0),
                isotropic=True,  # If True, scaling factor along all dimensions is the same
                center="image",
                default_pad_value="minimum",
                image_interpolation="linear",
                include=["img", "label", "weight"],
            )

            # Rotation
            rot = tio.RandomAffine(
                scales=(1.0, 1.0),
                degrees=10,
                translation=(0, 0, 0),
                isotropic=True,  # If True, scaling factor along all dimensions is the same
                center="image",
                default_pad_value="minimum",
                image_interpolation="linear",
                include=["img", "label", "weight"],
            )

            # Translation
            tl = tio.RandomAffine(
                scales=(1.0, 1.0),
                degrees=0,
                translation=(15.0, 15.0, 0),
                isotropic=True,  # If True, scaling factor along all dimensions is the same
                center="image",
                default_pad_value="minimum",
                image_interpolation="linear",
                include=["img", "label", "weight"],
            )

            # Random Anisotropy (Downsample image along an axis, then upsample back to initial space
            ra = tio.transforms.RandomAnisotropy(
                axes=(0, 1),
                downsampling=(1.1, 1.5),
                image_interpolation="linear",
                include=["img"],
            )

            # Bias Field
            bias_field = tio.transforms.RandomBiasField(
                coefficients=0.5, order=3, include=["img"]
            )

            # Gamma
            random_gamma = tio.transforms.RandomGamma(
                log_gamma=(-0.1, 0.1), include=["img"]
            )

            #

            all_augs = {
                "Elastic": elastic,
                "Scaling": scaling,
                "Rotation": rot,
                "Translation": tl,
                "RAnisotropy": ra,
                "BiasField": bias_field,
                "RGamma": random_gamma,
            }

            all_tfs = {all_augs[aug]: 0.8 for aug in cfg.DATA.AUG if aug != "Gaussian"}
            gaussian_noise = True if "Gaussian" in cfg.DATA.AUG else False

            transform = tio.Compose(
                [tio.Compose(all_tfs, p=0.8)], include=["img", "label", "weight"]
            )

            data_path = cfg.DATA.PATH_HDF5_TRAIN
            shuffle = True

            logger.info(
                f"Loading {mode.capitalize()} data ... from {data_path}. Using torchio Aug"
            )

            dataset = dset.MultiScaleDataset(data_path, cfg, gaussian_noise, transform)

    elif mode == "val":
        data_path = cfg.DATA.PATH_HDF5_VAL
        shuffle = False
        transform = transforms.Compose(
            [
                ZeroPad2D((padding_size, padding_size)),
                ToTensor(),
            ]
        )

        logger.info(f"Loading {mode.capitalize()} data ... from {data_path}")

        dataset = dset.MultiScaleDatasetVal(data_path, cfg, transform)

    # Validate that dataset is not empty
    if len(dataset) == 0:
        error_msg = (
            f"ERROR: Dataset is empty (0 samples found)!\n"
            f"  Mode: {mode}\n"
            f"  HDF5 path: {data_path}\n"
            f"  Plane: {cfg.DATA.PLANE}\n"
            f"  Expected sizes: {cfg.DATA.SIZES}\n\n"
            f"Possible causes:\n"
            f"  1. HDF5 file was created but no subjects were processed\n"
            f"  2. All subjects were filtered out during HDF5 creation\n"
            f"  3. HDF5 file structure doesn't match expected sizes\n"
            f"  4. Data split file filtered out all subjects\n\n"
            f"Please check:\n"
            f"  - Run step2_create_hdf5.py with --split_type {mode} to generate data\n"
            f"  - Verify subjects exist in the data directory\n"
            f"  - Check data_split.json if using train/val split\n"
            f"  - Inspect HDF5 file structure: h5dump -H {data_path} | head -50"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    dataloader = DataLoader(
        dataset,
        batch_size=cfg.TRAIN.BATCH_SIZE,
        num_workers=cfg.TRAIN.NUM_WORKERS,
        shuffle=shuffle,
        pin_memory=True,
    )
    return dataloader
