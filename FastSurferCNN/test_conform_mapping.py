#!/usr/bin/env python3
"""
Debug the vox2vox mapping to see why brain is lost
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import prepare_mgh_header, conformed_vox_img_size

# Test label (easier to see 0/1 values)
label_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/labels")
test_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")
base_name = test_image.name.replace('.nii.gz', '')
label_matches = list(label_dir.glob(f"{base_name}_*.nii.gz"))
test_label = label_matches[0] if label_matches else None

print("=" * 80)
print("VOX2VOX MAPPING DEBUG")
print("=" * 80)

# Load label
img = nib.load(test_label)
data = np.asarray(img.dataobj)

print(f"\nInput label:")
print(f"  Shape: {img.shape}")
print(f"  Voxel size: {img.header.get_zooms()[:3]}")
print(f"  Affine:\n{img.affine}")

# Find brain bounding box
brain_coords = np.where(data > 0)
if len(brain_coords[0]) > 0:
    bbox = {
        'x': (int(np.min(brain_coords[0])), int(np.max(brain_coords[0]))),
        'y': (int(np.min(brain_coords[1])), int(np.max(brain_coords[1]))),
        'z': (int(np.min(brain_coords[2])), int(np.max(brain_coords[2]))),
    }
    brain_center_vox = np.array([
        np.mean(brain_coords[0]),
        np.mean(brain_coords[1]),
        np.mean(brain_coords[2])
    ])
    print(f"  Brain bounding box (voxel coords): {bbox}")
    print(f"  Brain center (voxel coords): {brain_center_vox}")
    
    # Convert brain center to world coords
    brain_center_world = img.affine.dot(np.hstack((brain_center_vox, [1.0])))[:3]
    print(f"  Brain center (world coords): {brain_center_world}")

# Now simulate what conform() does
print("\n" + "=" * 80)
print("SIMULATING CONFORM() - LIA orientation, auto size")
print("=" * 80)

vox_img = conformed_vox_img_size(img, "min", "auto", threshold_1mm=0.95)
print(f"\nTarget voxel size: {vox_img[0]}")
print(f"Target image size: {vox_img[1]}")

h1 = prepare_mgh_header(img, *vox_img, "lia")
target_affine = h1.get_affine()
target_shape = h1.get_data_shape()[:3]

print(f"\nTarget shape: {target_shape}")
print(f"Target affine:\n{target_affine}")

# Calculate vox2vox transformation
vox2vox = np.linalg.inv(target_affine) @ img.affine
print(f"\nVox2vox transformation:\n{vox2vox}")

# Now check where the brain center maps to in the output
output_center = np.array(target_shape) / 2.0
print(f"\nOutput volume center (voxel coords): {output_center}")

# Map brain center from input to output
brain_center_in_output = np.linalg.inv(vox2vox).dot(np.hstack((brain_center_vox, [1.0])))[:3]
print(f"Brain center maps to output voxel: {brain_center_in_output}")
print(f"Output volume bounds: [0, 0, 0] to {target_shape}")

# Check if brain center is within output bounds
within_bounds = np.all((brain_center_in_output >= 0) & (brain_center_in_output < target_shape))
print(f"Brain center within output bounds: {within_bounds}")

if not within_bounds:
    print(f"\n⚠️  PROBLEM: Brain center is OUTSIDE output volume!")
    for i, (coord, size) in enumerate(zip(brain_center_in_output, target_shape)):
        if coord < 0:
            print(f"  Dimension {i}: {coord:.1f} < 0 (outside on low end)")
        elif coord >= size:
            print(f"  Dimension {i}: {coord:.1f} >= {size} (outside on high end)")

# Check all brain voxel corners
print(f"\nChecking if brain bounding box fits in output:")
brain_corners = [
    [bbox['x'][0], bbox['y'][0], bbox['z'][0], 1],  # min corner
    [bbox['x'][1], bbox['y'][1], bbox['z'][1], 1],  # max corner
]

for corner_name, corner_vox in zip(["Min corner", "Max corner"], brain_corners):
    corner_output = np.linalg.inv(vox2vox).dot(corner_vox)[:3]
    within = np.all((corner_output >= 0) & (corner_output < target_shape))
    print(f"  {corner_name} {corner_vox[:3]} -> {corner_output} (within bounds: {within})")

print("\n" + "=" * 80)
print("DIAGNOSIS")
print("=" * 80)
print("""
If the brain voxels map to coordinates outside [0, size-1] in the output,
then scipy.ndimage.affine_transform() will fill them with zeros.

This is why you're losing the brain data!

The problem is that conform() preserves the world-space center from the input,
but your EPI data has a non-standard center that doesn't align well with
the LIA-oriented output volume.
""")

