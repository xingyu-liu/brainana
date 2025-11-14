"""
macacaMRINN: Macaque Brain Extraction using Deep Learning

A simple, focused deep learning framework for automatic brain extraction from macaque MRI scans.
"""

__version__ = "1.0.0"
__author__ = "NHP-BrainExtraction_XL Team"

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
