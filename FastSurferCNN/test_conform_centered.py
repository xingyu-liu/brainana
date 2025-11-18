#!/usr/bin/env python3
"""
Test conform with forced centering at origin
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import conform

# Test image
test_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")
label_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/labels")
base_name = test_image.name.replace('.nii.gz', '')
label_matches = list(label_dir.glob(f"{base_name}_*.nii.gz"))
test_label = label_matches[0] if label_matches else None

output_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/test")

print("=" * 80)
print("CENTERED CONFORM TEST")
print("=" * 80)

# Load raw files
print(f"\nLoading: {test_image.name}")
raw_img = nib.load(test_image)
print(f"  Shape: {raw_img.shape}")
print(f"  Affine:\n{raw_img.affine}")

# Calculate current center in world space
img_center_vox = np.array(raw_img.shape[:3]) / 2.0
img_center_world = raw_img.affine.dot(np.hstack((img_center_vox, [1.0])))[:3]
print(f"  Center in world space: {img_center_world}")

if test_label:
    print(f"\nLoading: {test_label.name}")
    raw_label = nib.load(test_label)
    print(f"  Shape: {raw_label.shape}")
    raw_label_data = np.asarray(raw_label.dataobj)
    print(f"  Unique values: {np.unique(raw_label_data)}")
    print(f"  Non-zero: {np.sum(raw_label_data > 0)}/{raw_label_data.size}")

# Strategy: Adjust the affine to center the brain at origin BEFORE conforming
print("\n" + "=" * 80)
print("STRATEGY: Recenter image affine to origin before conform")
print("=" * 80)

# Create a new affine that centers the image at origin
# Keep the same orientation and voxel size, but shift the origin
recentered_affine = raw_img.affine.copy()
# Set translation to center the image at origin
# New translation = -(rotation * center_voxels)
rotation = raw_img.affine[:3, :3]
center_offset = rotation.dot(img_center_vox)
recentered_affine[:3, 3] = -center_offset

print(f"\nOriginal affine:\n{raw_img.affine}")
print(f"\nRecentered affine:\n{recentered_affine}")

# Create new image with recentered affine
recentered_img = nib.Nifti1Image(np.asarray(raw_img.dataobj), recentered_affine, raw_img.header)
if test_label:
    recentered_label = nib.Nifti1Image(np.asarray(raw_label.dataobj), recentered_affine, raw_label.header)

# Now conform with the recentered image
print("\n--- Test: LIA orientation, auto size, recentered affine ---")
conformed_img = conform(
    recentered_img,
    order=1,
    orientation="lia",
    img_size="auto",
    vox_size="min",
    threshold_1mm=0.95,
    dtype=np.uint8,
    rescale=255,
)

print(f"✓ Conformed!")
print(f"  Output shape: {conformed_img.shape}")
print(f"  Output affine:\n{conformed_img.affine}")

conf_data = np.asarray(conformed_img.dataobj)
print(f"  Data range: [{np.min(conf_data)}, {np.max(conf_data)}]")
print(f"  Non-zero voxels: {np.sum(conf_data > 0)}/{conf_data.size}")

nib.save(conformed_img, output_dir / "test_recentered_image.nii.gz")
print(f"  Saved: {output_dir / 'test_recentered_image.nii.gz'}")

if test_label:
    conformed_label = conform(
        recentered_label,
        order=0,
        orientation="lia",
        img_size="auto",
        vox_size="min",
        threshold_1mm=0.95,
        dtype=np.int16,
        rescale=None,
    )
    conf_label_data = np.asarray(conformed_label.dataobj)
    print(f"  Label unique values: {np.unique(conf_label_data)}")
    print(f"  Label non-zero: {np.sum(conf_label_data > 0)}/{conf_label_data.size}")
    nib.save(conformed_label, output_dir / "test_recentered_label.nii.gz")
    print(f"  Label saved: {output_dir / 'test_recentered_label.nii.gz'}")

print("\n" + "=" * 80)
print("Check test_recentered_*.nii.gz to see if brain is now centered!")
print("=" * 80)

