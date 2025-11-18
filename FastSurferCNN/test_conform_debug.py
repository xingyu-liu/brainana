#!/usr/bin/env python3
"""
Debug conform - figure out what IMG_SIZE="auto" is computing
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import conformed_vox_img_size

# Test image
test_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")

print("=" * 80)
print("DEBUG: What is conformed_vox_img_size() computing?")
print("=" * 80)

# Load raw image
raw_img = nib.load(test_image)
print(f"\nInput image:")
print(f"  Shape: {raw_img.shape}")
print(f"  Voxel size: {raw_img.header.get_zooms()[:3]}")
print(f"  Affine:\n{raw_img.affine}")

# Test different parameter combinations
configs = [
    {"vox_size": "min", "img_size": "auto", "threshold_1mm": 0.95},
    {"vox_size": "min", "img_size": "auto", "threshold_1mm": None},
    {"vox_size": "min", "img_size": 256, "threshold_1mm": 0.95},
    {"vox_size": 1.0, "img_size": "auto", "threshold_1mm": 0.95},
    {"vox_size": 1.0, "img_size": 256, "threshold_1mm": None},
]

for i, config in enumerate(configs, 1):
    print(f"\n--- Config {i}: {config} ---")
    try:
        target_vox, target_img = conformed_vox_img_size(
            raw_img,
            vox_size=config["vox_size"],
            img_size=config["img_size"],
            threshold_1mm=config["threshold_1mm"],
        )
        print(f"  ✓ Target voxel size: {target_vox}")
        print(f"  ✓ Target image size: {target_img}")
        
        # Calculate the logic from line 1177
        if target_vox is not None:
            vox_is_1mm = np.allclose(target_vox, 1.0, atol=abs(1.0 - (config["threshold_1mm"] or 1.0)))
            print(f"  → Voxel size is considered 1mm: {vox_is_1mm}")
            print(f"     (threshold: {config['threshold_1mm']}, tolerance: {abs(1.0 - (config['threshold_1mm'] or 1.0))})")
        
        if config["img_size"] == "auto":
            # Show what the FOV calculation would be
            fov = np.array(raw_img.header.get_zooms()[:3]) * np.array(raw_img.shape[:3])
            print(f"  → Field of view (mm): {fov}")
            if target_vox is not None:
                fov_based_size = np.ceil(fov / target_vox)
                print(f"  → FOV-based image size: {fov_based_size}")
                final_size = np.full_like(fov_based_size, np.amax(fov_based_size), dtype=int)
                print(f"  → Final size (max of all dims): {final_size}")
                
    except Exception as e:
        print(f"  ✗ Error: {e}")

print("\n" + "=" * 80)
print("DIAGNOSIS:")
print("=" * 80)

# The key question: why is output (283, 256, 256) instead of (256, 256, 256)?
print("""
The issue: When IMG_SIZE='auto', conform() should output 256³ for 1mm data,
but we're getting non-cubic volumes like (283, 256, 256).

Possible causes:
1. The THRESHOLD_1MM logic is not working as expected
2. The voxel size check at line 1177 is failing
3. The FOV calculation is producing unexpected results
4. Something else is overriding the size

Let's check the actual conform() call to see what's happening...
""")

