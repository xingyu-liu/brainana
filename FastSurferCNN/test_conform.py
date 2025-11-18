#!/usr/bin/env python3
"""
Standalone script to test conform() function on EPI data
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import conform

# Test image and output directory
test_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")
label_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/labels")
# Extract base name (remove .nii.gz extension)
base_name = test_image.name.replace('.nii.gz', '')
label_pattern = f"{base_name}_*.nii.gz"
label_matches = list(label_dir.glob(label_pattern))
test_label = label_matches[0] if label_matches else None

output_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/test")
output_dir.mkdir(exist_ok=True, parents=True)

print("=" * 80)
print("CONFORM() FUNCTION TEST")
print("=" * 80)

# Load raw image
print(f"\n1. Loading raw image: {test_image.name}")
raw_img = nib.load(test_image)
print(f"   Shape: {raw_img.shape}")
print(f"   Voxel size: {raw_img.header.get_zooms()[:3]}")
print(f"   Data type: {raw_img.get_data_dtype()}")
print(f"   Affine:\n{raw_img.affine}")

# Save raw image info
raw_data = np.asarray(raw_img.dataobj)
print(f"   Data range: [{np.min(raw_data)}, {np.max(raw_data)}]")
print(f"   Non-zero voxels: {np.sum(raw_data > 0)}/{raw_data.size}")

# Load raw label if exists
if test_label:
    print(f"\n2. Loading raw label: {test_label.name}")
    raw_label = nib.load(test_label)
    print(f"   Shape: {raw_label.shape}")
    print(f"   Voxel size: {raw_label.header.get_zooms()[:3]}")
    print(f"   Data type: {raw_label.get_data_dtype()}")
    print(f"   Affine:\n{raw_label.affine}")
    
    raw_label_data = np.asarray(raw_label.dataobj)
    print(f"   Unique values: {np.unique(raw_label_data)}")
    print(f"   Non-zero voxels: {np.sum(raw_label_data > 0)}/{raw_label_data.size}")
    
    # Check if affines match
    affine_match = np.allclose(raw_img.affine, raw_label.affine, atol=1e-3)
    print(f"   Affine matches image: {affine_match}")
    if not affine_match:
        print(f"   ⚠️  WARNING: Image and label affines don't match!")

print("\n" + "=" * 80)
print("TESTING CONFORM() WITH DIFFERENT PARAMETERS")
print("=" * 80)

# Test 1: LIA orientation + auto size (current config)
print("\n--- Test 1: ORIENTATION='lia', IMG_SIZE='auto', VOX_SIZE='min' ---")
try:
    conformed_1 = conform(
        raw_img,
        order=1,
        orientation="lia",
        img_size="fov",
        vox_size="min",
        threshold_1mm=0.95,
        dtype=np.uint8,
        rescale=255,
    )
    print(f"✓ Success!")
    print(f"  Output shape: {conformed_1.shape}")
    print(f"  Output voxel size: {conformed_1.header.get_zooms()[:3]}")
    print(f"  Output affine:\n{conformed_1.affine}")
    
    conf_data_1 = np.asarray(conformed_1.dataobj)
    print(f"  Data range: [{np.min(conf_data_1)}, {np.max(conf_data_1)}]")
    print(f"  Non-zero voxels: {np.sum(conf_data_1 > 0)}/{conf_data_1.size}")
    
    nib.save(conformed_1, output_dir / "test1_lia_auto_min.nii.gz")
    print(f"  Saved to: {output_dir / 'test1_lia_auto_min.nii.gz'}")
    
    # Test label with same parameters
    if test_label:
        conformed_label_1 = conform(
            raw_label,
            order=0,  # nearest neighbor for labels
            orientation="lia",
            img_size="auto",
            vox_size="min",
            threshold_1mm=0.95,
            dtype=np.int16,
            rescale=None,
        )
        conf_label_data_1 = np.asarray(conformed_label_1.dataobj)
        print(f"  Label unique values: {np.unique(conf_label_data_1)}")
        print(f"  Label non-zero voxels: {np.sum(conf_label_data_1 > 0)}/{conf_label_data_1.size}")
        nib.save(conformed_label_1, output_dir / "test1_label_lia_auto_min.nii.gz")
        print(f"  Label saved to: {output_dir / 'test1_label_lia_auto_min.nii.gz'}")
        
except Exception as e:
    print(f"✗ Failed: {e}")

# # Test 2: Native orientation + auto size
# print("\n--- Test 2: ORIENTATION='native', IMG_SIZE='auto', VOX_SIZE='min' ---")
# try:
#     conformed_2 = conform(
#         raw_img,
#         order=1,
#         orientation="native",
#         img_size="auto",
#         vox_size="min",
#         threshold_1mm=0.95,
#         dtype=np.uint8,
#         rescale=255,
#     )
#     print(f"✓ Success!")
#     print(f"  Output shape: {conformed_2.shape}")
#     print(f"  Output voxel size: {conformed_2.header.get_zooms()[:3]}")
#     print(f"  Output affine:\n{conformed_2.affine}")
    
#     conf_data_2 = np.asarray(conformed_2.dataobj)
#     print(f"  Data range: [{np.min(conf_data_2)}, {np.max(conf_data_2)}]")
#     print(f"  Non-zero voxels: {np.sum(conf_data_2 > 0)}/{conf_data_2.size}")
    
#     nib.save(conformed_2, output_dir / "test2_native_auto_min.nii.gz")
#     print(f"  Saved to: {output_dir / 'test2_native_auto_min.nii.gz'}")
    
#     # Test label with same parameters
#     if test_label:
#         conformed_label_2 = conform(
#             raw_label,
#             order=0,
#             orientation="native",
#             img_size="auto",
#             vox_size="min",
#             threshold_1mm=0.95,
#             dtype=np.int16,
#             rescale=None,
#         )
#         conf_label_data_2 = np.asarray(conformed_label_2.dataobj)
#         print(f"  Label unique values: {np.unique(conf_label_data_2)}")
#         print(f"  Label non-zero voxels: {np.sum(conf_label_data_2 > 0)}/{conf_label_data_2.size}")
#         nib.save(conformed_label_2, output_dir / "test2_label_native_auto_min.nii.gz")
#         print(f"  Label saved to: {output_dir / 'test2_label_native_auto_min.nii.gz'}")
        
# except Exception as e:
#     print(f"✗ Failed: {e}")

# # Test 3: Native orientation + fixed 256 size
# print("\n--- Test 3: ORIENTATION='native', IMG_SIZE=256, VOX_SIZE='min' ---")
# try:
#     conformed_3 = conform(
#         raw_img,
#         order=1,
#         orientation="native",
#         img_size=256,
#         vox_size="min",
#         threshold_1mm=0.95,
#         dtype=np.uint8,
#         rescale=255,
#     )
#     print(f"✓ Success!")
#     print(f"  Output shape: {conformed_3.shape}")
#     print(f"  Output voxel size: {conformed_3.header.get_zooms()[:3]}")
#     print(f"  Output affine:\n{conformed_3.affine}")
    
#     conf_data_3 = np.asarray(conformed_3.dataobj)
#     print(f"  Data range: [{np.min(conf_data_3)}, {np.max(conf_data_3)}]")
#     print(f"  Non-zero voxels: {np.sum(conf_data_3 > 0)}/{conf_data_3.size}")
    
#     nib.save(conformed_3, output_dir / "test3_native_256_min.nii.gz")
#     print(f"  Saved to: {output_dir / 'test3_native_256_min.nii.gz'}")
    
#     # Test label with same parameters
#     if test_label:
#         conformed_label_3 = conform(
#             raw_label,
#             order=0,
#             orientation="native",
#             img_size=256,
#             vox_size="min",
#             threshold_1mm=0.95,
#             dtype=np.int16,
#             rescale=None,
#         )
#         conf_label_data_3 = np.asarray(conformed_label_3.dataobj)
#         print(f"  Label unique values: {np.unique(conf_label_data_3)}")
#         print(f"  Label non-zero voxels: {np.sum(conf_label_data_3 > 0)}/{conf_label_data_3.size}")
#         nib.save(conformed_label_3, output_dir / "test3_label_native_256_min.nii.gz")
#         print(f"  Label saved to: {output_dir / 'test3_label_native_256_min.nii.gz'}")
        
# except Exception as e:
#     print(f"✗ Failed: {e}")

# # Test 4: LIA orientation + fixed 256 size
# print("\n--- Test 4: ORIENTATION='lia', IMG_SIZE=256, VOX_SIZE='min' ---")
# try:
#     conformed_4 = conform(
#         raw_img,
#         order=1,
#         orientation="lia",
#         img_size=256,
#         vox_size="min",
#         threshold_1mm=0.95,
#         dtype=np.uint8,
#         rescale=255,
#     )
#     print(f"✓ Success!")
#     print(f"  Output shape: {conformed_4.shape}")
#     print(f"  Output voxel size: {conformed_4.header.get_zooms()[:3]}")
#     print(f"  Output affine:\n{conformed_4.affine}")
    
#     conf_data_4 = np.asarray(conformed_4.dataobj)
#     print(f"  Data range: [{np.min(conf_data_4)}, {np.max(conf_data_4)}]")
#     print(f"  Non-zero voxels: {np.sum(conf_data_4 > 0)}/{conf_data_4.size}")
    
#     nib.save(conformed_4, output_dir / "test4_lia_256_min.nii.gz")
#     print(f"  Saved to: {output_dir / 'test4_lia_256_min.nii.gz'}")
    
#     # Test label with same parameters
#     if test_label:
#         conformed_label_4 = conform(
#             raw_label,
#             order=0,
#             orientation="lia",
#             img_size=256,
#             vox_size="min",
#             threshold_1mm=0.95,
#             dtype=np.int16,
#             rescale=None,
#         )
#         conf_label_data_4 = np.asarray(conformed_label_4.dataobj)
#         print(f"  Label unique values: {np.unique(conf_label_data_4)}")
#         print(f"  Label non-zero voxels: {np.sum(conf_label_data_4 > 0)}/{conf_label_data_4.size}")
#         nib.save(conformed_label_4, output_dir / "test4_label_lia_256_min.nii.gz")
#         print(f"  Label saved to: {output_dir / 'test4_label_lia_256_min.nii.gz'}")
        
# except Exception as e:
#     print(f"✗ Failed: {e}")

# Also save raw files for comparison
print("\n" + "=" * 80)
print("Saving raw files for comparison...")
nib.save(raw_img, output_dir / "raw_image.nii.gz")
print(f"  Saved: {output_dir / 'raw_image.nii.gz'}")
if test_label:
    nib.save(raw_label, output_dir / "raw_label.nii.gz")
    print(f"  Saved: {output_dir / 'raw_label.nii.gz'}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"All outputs saved to: {output_dir}")
print("\nFiles created:")
print("  - raw_image.nii.gz (original)")
if test_label:
    print("  - raw_label.nii.gz (original)")
print("  - test1_lia_auto_min.nii.gz (current config)")
if test_label:
    print("  - test1_label_lia_auto_min.nii.gz (current config)")
print("  - test2_native_auto_min.nii.gz")
if test_label:
    print("  - test2_label_native_auto_min.nii.gz")
print("  - test3_native_256_min.nii.gz")
if test_label:
    print("  - test3_label_native_256_min.nii.gz")
print("  - test4_lia_256_min.nii.gz")
if test_label:
    print("  - test4_label_lia_256_min.nii.gz")
print("\nInspect these files with your imaging viewer to see what's happening!")
print("=" * 80)

