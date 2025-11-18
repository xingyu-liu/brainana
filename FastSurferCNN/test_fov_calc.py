#!/usr/bin/env python3
"""
Check what FOV-based size would be for EPI
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import conformed_vox_img_size

epi_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")

img = nib.load(epi_image)

print("EPI Image:")
print(f"  Shape: {img.shape}")
print(f"  Voxel size: {img.header.get_zooms()[:3]}")
fov = np.array(img.header.get_zooms()[:3]) * np.array(img.shape[:3])
print(f"  FOV (mm): {fov}")

# Test what size would be calculated
vox_img = conformed_vox_img_size(img, "min", "auto", threshold_1mm=0.95)
print(f"\nWith 'auto' and 1mm threshold:")
print(f"  Target voxel size: {vox_img[0]}")
print(f"  Target image size: {vox_img[1]}")

# What if we use "fov" instead of "auto"?
vox_img_fov = conformed_vox_img_size(img, "min", "fov", threshold_1mm=0.95)
print(f"\nWith 'fov' instead of 'auto':")
print(f"  Target voxel size: {vox_img_fov[0]}")
print(f"  Target image size: {vox_img_fov[1]}")

# Manual calculation
target_vox = 1.0
fov_based_size = np.ceil(fov / target_vox).astype(int)
print(f"\nManual FOV-based calculation:")
print(f"  FOV / 1.0mm = {fov_based_size}")

# What size would work? Need to fit brain at center
# Brain center in world: [1.01, 5.28, 36.37] mm
# If we center at origin, brain extends from -48 to +48 mm in each direction
# So we need at least 96mm = 96 voxels at 1mm
print(f"\nTo fit brain (FOV 96mm) at 1mm:")
print(f"  Minimum size needed: 96 voxels")
print(f"  But 'auto' forces: 256 voxels (too large, causes misalignment)")

