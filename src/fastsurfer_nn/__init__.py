# Copyright 2023 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
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
fastsurfer_nn - Fast and accurate neuroanatomical MRI segmentation.

This package provides:
- Deep learning models for brain MRI segmentation
- Training utilities for custom datasets
- Inference pipelines for prediction
- Post-processing tools
- Statistical analysis and quality control

Module Organization:
-------------------
- training/      : Training pipeline (data preparation, HDF5 creation, model training)
- inference/     : Inference and prediction
- postprocessing/: Post-segmentation processing
- seg_statistics/: Segmentation statistics and quality control
- models/        : Neural network architectures
- data_loader/   : Data loading and preprocessing
- utils/         : Utility functions and helpers
- atlas/         : Atlas management
- config/        : Configuration files
"""

# Import new module structure
from . import (
    atlas,
    config,
    data_loader,
    inference,
    models,
    postprocessing,
    seg_statistics,
    training,
    utils,
)

# Backward compatibility aliases for commonly imported modules
# These allow existing code to continue working with old import paths

# Legacy: from fastsurfer_nn.train import Trainer
# New: from fastsurfer_nn.training.trainer import Trainer
from .training import trainer as train

# Legacy: from fastsurfer_nn import inference (was a module at root)
# New: from fastsurfer_nn.inference import inference
# Note: 'inference' is already imported above as the package

# Legacy: from fastsurfer_nn.postseg_1_reduce_to_aseg import ...
# New: from fastsurfer_nn.postprocessing.reduce_to_aseg import ...
from .postprocessing import reduce_to_aseg as postseg_1_reduce_to_aseg

# Legacy: from fastsurfer_nn.quick_qc import ...
# New: from fastsurfer_nn.seg_statistics.quick_qc import ...
from .seg_statistics import quick_qc

# Legacy: from fastsurfer_nn.segstats import ...
# New: from fastsurfer_nn.seg_statistics.segstats import ...
from .seg_statistics import segstats

# Legacy: from fastsurfer_nn.run_model import ...
# New: from fastsurfer_nn.training.step3_train_model import ...
from .training import step3_train_model as run_model

__all__ = [
    # New module structure
    "training",
    "inference", 
    "postprocessing",
    "seg_statistics",
    "models",
    "data_loader",
    "utils",
    "atlas",
    "config",
    # Backward compatibility aliases
    "train",
    "run_model",
    "postseg_1_reduce_to_aseg",
    "quick_qc",
    "segstats",
]

__version__ = "2.0.0"
