# Copyright 2022 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
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
Constants for FastSurferCNN.

This module contains shared constants used across the FastSurferCNN package.
"""

from pathlib import Path

# FastSurfer root directory (parent of FastSurferCNN package)
FASTSURFER_ROOT = Path(__file__).parents[2]
PRETRAINED_MODEL_DIR = FASTSURFER_ROOT / "FastSurferCNN" / "pretrained_model"
TEMPLATE_DIR = FASTSURFER_ROOT / "templatezoo"

# Brain mask creation parameters
MASK_DILATION_SIZE_MM = 2.0  # Dilation size in millimeters for mask creation
ROUNDS_OF_MORPHOLOGICAL_OPERATIONS = 3  # Number of rounds for morphological operations

# Two-pass refinement parameters
TWO_PASS_BRAIN_RATIO_THRESHOLD = 1/8  # Trigger refinement if brain occupies < 12.5% of FOV
TWO_PASS_CROP_MARGIN = 0.08  # 8% margin around brain bounding box

# Large image threshold for memory optimization
LARGE_IMAGE_THRESHOLD = 384  # Disable padding for images larger than this to avoid OOM

