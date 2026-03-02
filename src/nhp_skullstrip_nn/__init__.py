"""
nhp_skullstrip_nn: NHP brain extraction using deep learning (brainana package).

A focused deep learning framework for automatic brain extraction from macaque/NHP MRI scans.
Adapted from NHP-BrainExtraction (DeepBet): https://github.com/HumanBrainED/NHP-BrainExtraction
(Wang et al. 2021, NeuroImage 235:118001).
"""

# Import main modules
from . import data
from . import model
from . import train
from . import utils
from . import inference

# Import key classes for easy access
from .model import UNet2d
from .data import VolumeDataset
from .inference import predict_volumes
from .config import TrainingConfig, InferenceConfig
from .utils import get_device, setup_logging, get_logger

__all__ = [
    'data',
    'model', 
    'train',
    'utils',
    'inference',
    'UNet2d',
    'VolumeDataset',
    'predict_volumes',
    'TrainingConfig',
    'InferenceConfig',
    'get_device',
    'setup_logging',
    'get_logger'
]
