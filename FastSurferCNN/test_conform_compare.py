#!/usr/bin/env python3
"""
Compare conform() mapping for T1w (works) vs EPI (fails) to find the difference
"""
import sys
import numpy as np
import nibabel as nib
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.data_loader.conform import prepare_mgh_header, conformed_vox_img_size

# Test files
t1w_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/T1w_seg-ARM2/images/site-nin_sub-032223_ses-007_T1w.nii.gz")
epi_image = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/images/site-arcaro_sub-baby1_ses-120916_task-vision_run-09_EPI.nii.gz")

epi_label_dir = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/EPI_brainmask/labels")
epi_base_name = epi_image.name.replace('.nii.gz', '')
epi_label_matches = list(epi_label_dir.glob(f"{epi_base_name}_*.nii.gz"))
epi_label = epi_label_matches[0] if epi_label_matches else None

print("=" * 80)
print("COMPARING CONFORM() MAPPING: T1w (WORKS) vs EPI (FAILS)")
print("=" * 80)

def analyze_image(img_path, label_path=None, name="Image"):
    """Analyze an image's conform mapping"""
    print(f"\n{'='*80}")
    print(f"{name}: {Path(img_path).name}")
    print(f"{'='*80}")
    
    # Load image
    img = nib.load(img_path)
    data = np.asarray(img.dataobj)
    
    print(f"\n1. INPUT IMAGE PROPERTIES:")
    print(f"   Shape: {img.shape}")
    print(f"   Voxel size: {img.header.get_zooms()[:3]}")
    print(f"   Data range: [{np.min(data)}, {np.max(data)}]")
    print(f"   Non-zero voxels: {np.sum(data > 0)}/{data.size}")
    
    # Calculate center in voxel coords
    img_center_vox = np.array(img.shape[:3], dtype=float) / 2.0
    print(f"   Center (voxel coords): {img_center_vox}")
    
    # Calculate center in world coords
    img_center_world = img.affine.dot(np.hstack((img_center_vox, [1.0])))[:3]
    print(f"   Center (world coords): {img_center_world}")
    print(f"   Distance from origin: {np.linalg.norm(img_center_world):.2f} mm")
    
    # Calculate FOV
    fov = np.array(img.header.get_zooms()[:3]) * np.array(img.shape[:3])
    print(f"   Field of view (mm): {fov}")
    print(f"   FOV max dimension: {np.max(fov):.2f} mm")
    
    print(f"\n   Affine matrix:")
    print(f"   {img.affine}")
    
    # If label, analyze brain location
    if label_path and Path(label_path).exists():
        label = nib.load(label_path)
        label_data = np.asarray(label.dataobj)
        brain_coords = np.where(label_data > 0)
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
            brain_center_world = label.affine.dot(np.hstack((brain_center_vox, [1.0])))[:3]
            
            print(f"\n   LABEL (Brain) PROPERTIES:")
            print(f"   Brain bounding box (voxel): {bbox}")
            print(f"   Brain center (voxel): {brain_center_vox}")
            print(f"   Brain center (world): {brain_center_world}")
            print(f"   Brain non-zero voxels: {np.sum(label_data > 0)}/{label_data.size}")
    
    print(f"\n2. CONFORM PARAMETERS (LIA, auto, min):")
    vox_img = conformed_vox_img_size(img, "min", "auto", threshold_1mm=0.95)
    print(f"   Target voxel size: {vox_img[0]}")
    print(f"   Target image size: {vox_img[1]}")
    
    print(f"\n3. PREPARE HEADER (LIA orientation):")
    h1 = prepare_mgh_header(img, *vox_img, "lia")
    target_affine = h1.get_affine()
    target_shape = h1.get_data_shape()[:3]
    
    print(f"   Target shape: {target_shape}")
    print(f"   Target affine:")
    print(f"   {target_affine}")
    
    # Calculate vox2vox
    vox2vox = np.linalg.inv(target_affine) @ img.affine
    print(f"\n   Vox2vox transformation:")
    print(f"   {vox2vox}")
    
    # Check where image center maps to
    output_center = np.array(target_shape) / 2.0
    img_center_in_output = np.linalg.inv(vox2vox).dot(np.hstack((img_center_vox, [1.0])))[:3]
    
    print(f"\n4. MAPPING ANALYSIS:")
    print(f"   Output volume center (voxel): {output_center}")
    print(f"   Input center maps to output voxel: {img_center_in_output}")
    print(f"   Input center within output bounds: {np.all((img_center_in_output >= 0) & (img_center_in_output < target_shape))}")
    
    # Check brain center if label exists
    if label_path and Path(label_path).exists() and len(brain_coords[0]) > 0:
        brain_center_in_output = np.linalg.inv(vox2vox).dot(np.hstack((brain_center_vox, [1.0])))[:3]
        print(f"   Brain center maps to output voxel: {brain_center_in_output}")
        brain_within = np.all((brain_center_in_output >= 0) & (brain_center_in_output < target_shape))
        print(f"   Brain center within output bounds: {brain_within}")
        
        if not brain_within:
            print(f"\n   ⚠️  PROBLEM: Brain center is OUTSIDE output volume!")
            for i, (coord, size) in enumerate(zip(brain_center_in_output, target_shape)):
                if coord < 0:
                    print(f"      Dimension {i}: {coord:.1f} < 0 (outside on low end)")
                elif coord >= size:
                    print(f"      Dimension {i}: {coord:.1f} >= {size} (outside on high end)")
        
        # Check brain corners
        brain_corners = [
            [bbox['x'][0], bbox['y'][0], bbox['z'][0], 1],  # min
            [bbox['x'][1], bbox['y'][1], bbox['z'][1], 1],  # max
        ]
        print(f"\n   Brain bounding box corners in output:")
        for corner_name, corner_vox in zip(["Min", "Max"], brain_corners):
            corner_output = np.linalg.inv(vox2vox).dot(corner_vox)[:3]
            within = np.all((corner_output >= 0) & (corner_output < target_shape))
            print(f"      {corner_name} {corner_vox[:3]} -> {corner_output} (within: {within})")
    
    # Analyze the affine transformation components
    print(f"\n5. AFFINE TRANSFORMATION BREAKDOWN:")
    print(f"   Input affine rotation/scaling:")
    print(f"   {img.affine[:3, :3]}")
    print(f"   Input affine translation:")
    print(f"   {img.affine[:3, 3]}")
    print(f"   Output affine rotation/scaling:")
    print(f"   {target_affine[:3, :3]}")
    print(f"   Output affine translation:")
    print(f"   {target_affine[:3, 3]}")
    
    # Check if input is already close to LIA
    input_orientation = nib.orientations.aff2axcodes(img.affine)
    print(f"   Input orientation: {input_orientation}")
    
    return {
        'img_center_world': img_center_world,
        'img_center_in_output': img_center_in_output,
        'target_shape': target_shape,
        'vox2vox': vox2vox,
        'fov': fov,
    }

# Analyze T1w
t1w_info = analyze_image(t1w_image, None, "T1w (WORKS)")

# Analyze EPI
epi_info = analyze_image(epi_image, epi_label, "EPI (FAILS)")

# Compare
print(f"\n{'='*80}")
print("COMPARISON SUMMARY")
print(f"{'='*80}")

print(f"\n1. FIELD OF VIEW:")
print(f"   T1w FOV: {t1w_info['fov']} mm (max: {np.max(t1w_info['fov']):.1f} mm)")
print(f"   EPI FOV: {epi_info['fov']} mm (max: {np.max(epi_info['fov']):.1f} mm)")
print(f"   → T1w has {np.max(t1w_info['fov']) / np.max(epi_info['fov']):.1f}x larger FOV")

print(f"\n2. WORLD-SPACE CENTER:")
print(f"   T1w center: {t1w_info['img_center_world']} mm (distance: {np.linalg.norm(t1w_info['img_center_world']):.1f} mm)")
print(f"   EPI center: {epi_info['img_center_world']} mm (distance: {np.linalg.norm(epi_info['img_center_world']):.1f} mm)")

print(f"\n3. OUTPUT MAPPING:")
print(f"   T1w center → output: {t1w_info['img_center_in_output']}")
print(f"   EPI center → output: {epi_info['img_center_in_output']}")
print(f"   T1w within bounds: {np.all((t1w_info['img_center_in_output'] >= 0) & (t1w_info['img_center_in_output'] < t1w_info['target_shape']))}")
print(f"   EPI within bounds: {np.all((epi_info['img_center_in_output'] >= 0) & (epi_info['img_center_in_output'] < epi_info['target_shape']))}")

print(f"\n4. VOX2VOX TRANSLATION COMPONENT:")
t1w_translation = t1w_info['vox2vox'][:3, 3]
epi_translation = epi_info['vox2vox'][:3, 3]
print(f"   T1w vox2vox translation: {t1w_translation}")
print(f"   EPI vox2vox translation: {epi_translation}")
print(f"   Difference: {epi_translation - t1w_translation}")

print(f"\n{'='*80}")
print("KEY INSIGHT:")
print(f"{'='*80}")
print("""
The vox2vox translation vector determines where the input volume
maps to in the output volume. If this translation is too large,
the input data will map outside the output bounds and be filled
with zeros by scipy.ndimage.affine_transform().

Compare the translation vectors above to see what's different!
""")

