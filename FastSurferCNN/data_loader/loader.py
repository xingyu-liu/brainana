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
import torchio as tio
from torch.utils.data import DataLoader
from torchvision import transforms

from FastSurferCNN.data_loader import dataset as dset
from FastSurferCNN.data_loader.data_transforms import AddGaussianNoise, ToTensor, Pad2D
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
            rescale = cfg.DATA.PREPROCESSING.RESCALE
            tfs = [Pad2D((padding_size, padding_size), mode='edge'), ToTensor(rescale=rescale)]
            # old transform
            if "Gaussian" in cfg.DATA.AUG:
                tfs.append(AddGaussianNoise(mean=0, std=0.1))

            data_path = cfg.DATA.PATH_HDF5_TRAIN
            shuffle = True

            logger.info(
                f"DataLoader: loading {mode} data from {data_path} (using standard augmentation)"
            )

            dataset = dset.MultiScaleDatasetVal(data_path, cfg, transforms.Compose(tfs))
        else:
            # Elastic - Optimized: reduced control points from 7 to 5 for better performance
            # Note: With locked_borders=2, torchio requires at least 5 control points
            # Can be configured via cfg.DATA.AUG_ELASTIC if needed
            if hasattr(cfg.DATA, 'AUG_ELASTIC'):
                elastic_num_points = getattr(cfg.DATA.AUG_ELASTIC, 'NUM_CONTROL_POINTS', 5)
                elastic_max_disp = getattr(cfg.DATA.AUG_ELASTIC, 'MAX_DISPLACEMENT', (20, 20, 0))
            else:
                elastic_num_points = 5  # Minimum required with locked_borders=2
                elastic_max_disp = (20, 20, 0)
            elastic = tio.RandomElasticDeformation(
                num_control_points=elastic_num_points,
                max_displacement=elastic_max_disp,
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

            # Rotation - randomly samples from (-15, +15) degrees for each sample
            rot = tio.RandomAffine(
                scales=(1.0, 1.0),
                degrees=15,  # Random rotation between -15 and +15 degrees
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
            # Optimized: reduced downsampling range from (1.1, 1.5) to (1.1, 1.3) for better performance
            ra = tio.transforms.RandomAnisotropy(
                axes=(0, 1),
                downsampling=(1.1, 1.3),  # Reduced from (1.1, 1.5) - less aggressive = faster
                image_interpolation="linear",
                include=["img"],
            )

            # Bias Field - randomly samples coefficients from (0.3, 0.7) range for each sample
            # Optimized: reduced order from 3 to 2 for better performance (order 2 is usually sufficient)
            bias_field = tio.transforms.RandomBiasField(
                coefficients=(0.3, 0.7), order=2, include=["img"]  # Reduced from order=3 to order=2
            )

            # Gamma
            random_gamma = tio.transforms.RandomGamma(
                log_gamma=(-0.1, 0.1), include=["img"]
            )

            all_augs = {
                "Elastic": elastic,
                "Scaling": scaling,
                "Rotation": rot,
                "Translation": tl,
                "RAnisotropy": ra,
                "BiasField": bias_field,
                "RGamma": random_gamma,
            }

            # Get individual probabilities from config, default to 0.8 if not specified
            default_prob = 0.8
            aug_probs = {}
            if hasattr(cfg.DATA, 'AUG_PROBABILITIES'):
                try:
                    # Convert CfgNode to dict if needed
                    aug_probs_dict = cfg.DATA.AUG_PROBABILITIES
                    if hasattr(aug_probs_dict, '__dict__'):
                        aug_probs = {k: getattr(aug_probs_dict, k) for k in dir(aug_probs_dict) if not k.startswith('_')}
                    else:
                        aug_probs = dict(aug_probs_dict) if aug_probs_dict else {}
                except Exception:
                    aug_probs = {}
            
            # Separate transforms by computational cost for optimal ordering
            # Cheap transforms first (fail-fast), expensive transforms last
            cheap_geometric = ["Rotation", "Scaling", "Translation"]  # Fast: simple affine transforms
            expensive_geometric = ["Elastic", "RAnisotropy"]  # Slow: complex deformations
            intensity = ["BiasField", "RGamma"]  # Medium: intensity modifications
            
            cheap_tfs = {}
            expensive_tfs = {}
            intensity_tfs = {}
            
            for aug in cfg.DATA.AUG:
                if aug == "Gaussian":
                    continue
                if aug not in all_augs:
                    logger.warning(f"Augmentation '{aug}' not found in available augmentations. Skipping.")
                    continue
                
                prob = aug_probs.get(aug, default_prob)
                
                # Skip transforms with 0.0 probability to avoid overhead
                if prob <= 0.0:
                    continue
                
                # Categorize by computational cost
                if aug in cheap_geometric:
                    cheap_tfs[all_augs[aug]] = prob
                elif aug in expensive_geometric:
                    expensive_tfs[all_augs[aug]] = prob
                elif aug in intensity:
                    intensity_tfs[all_augs[aug]] = prob
                else:
                    # Default to cheap for unknown augs
                    cheap_tfs[all_augs[aug]] = prob
            
            gaussian_noise = True if "Gaussian" in cfg.DATA.AUG else False
            
            # Compose transforms in order: cheap → expensive → intensity
            # This ordering allows cheap transforms to fail-fast and reduces overall computation
            # Each transform in the dict has its own probability, so we use p=1.0 for the Compose
            # and let individual transforms handle their probabilities
            transform_list = []
            if cheap_tfs:
                transform_list.append(tio.Compose(cheap_tfs, p=1.0))
            if expensive_tfs:
                transform_list.append(tio.Compose(expensive_tfs, p=1.0))
            if intensity_tfs:
                transform_list.append(tio.Compose(intensity_tfs, p=1.0))
            
            if transform_list:
                transform = tio.Compose(transform_list, include=["img", "label", "weight"])
            else:
                # If no transforms selected, create an identity transform
                transform = tio.Compose([], include=["img", "label", "weight"])

            data_path = cfg.DATA.PATH_HDF5_TRAIN
            shuffle = True

            logger.info(
                f"DataLoader: loading {mode} data from {data_path} (using torchio augmentation)"
            )

            dataset = dset.MultiScaleDataset(data_path, cfg, gaussian_noise, transform)

    elif mode == "val":
        data_path = cfg.DATA.PATH_HDF5_VAL
        shuffle = False
        rescale = cfg.DATA.PREPROCESSING.RESCALE
        transform = transforms.Compose(
            [
                Pad2D((padding_size, padding_size), mode='edge'),
                ToTensor(rescale=rescale),
            ]
        )

        logger.info(f"DataLoader: loading {mode} data from {data_path}")

        dataset = dset.MultiScaleDatasetVal(data_path, cfg, transform)

    # Validate that dataset is not empty
    if len(dataset) == 0:
        error_msg = (
            f"DataLoader: dataset is empty (0 samples found)\n"
            f"  mode={mode}\n"
            f"  hdf5_path={data_path}\n"
            f"  plane={cfg.DATA.PLANE}\n"
            f"  expected_sizes={cfg.DATA.SIZES}\n\n"
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

    # Use DATA_LOADER.NUM_WORKERS directly (no fallback)
    num_workers = cfg.DATA_LOADER.NUM_WORKERS
    
    # Use DATA_LOADER.PIN_MEMORY (default to True if not specified)
    pin_memory = getattr(cfg.DATA_LOADER, 'PIN_MEMORY', True)
    
    # Get prefetch_factor from config (default to 4 for better GPU utilization)
    prefetch_factor = getattr(cfg.DATA_LOADER, 'PREFETCH_FACTOR', 4)
    
    dataloader = DataLoader(
        dataset,
        batch_size=cfg.TRAIN.BATCH_SIZE,
        num_workers=num_workers,
        shuffle=shuffle,
        pin_memory=pin_memory,
        prefetch_factor=prefetch_factor,  # Configurable prefetch factor (default: 4)
        persistent_workers=True if num_workers > 0 else False,  # Keep workers alive between epochs
    )
    return dataloader
