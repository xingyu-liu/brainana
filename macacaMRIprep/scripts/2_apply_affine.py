'''Apply a given affine transformation to an image and save the result as a new image.'''

#%%
import os
import numpy as np
import nibabel as nib
from scipy.ndimage import affine_transform

# %%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_freddie_mixed'
input_f = os.path.join(data_dir, 'input.nii.gz')
affine_f = os.path.join(data_dir, 'test.mat')

interpolation_order = 3
force_isotropic = False
force_affine2ref = True

if force_isotropic:
    output_f = input_f.replace('.nii.gz', '_py_nmt_iso.nii.gz')
else:
    output_f = input_f.replace('.nii.gz', '_py_nmt_aniso.nii.gz')
if force_affine2ref:
    ref_f = '/home/star/github/banana/templatezoo/tpl-NMT2Sym_res-05_T1w_brain.nii.gz'

# %%
# Validate input file exists
if not os.path.exists(input_f):
    raise FileNotFoundError(f"Input file not found: {input_f}")
if not os.path.exists(affine_f):
    raise FileNotFoundError(f"Affine file not found: {affine_f}")

# Ensure output directory exists
output_dir = os.path.dirname(output_f)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

# Load the image
print(f"Loading image: {input_f}")
img = nib.load(input_f)
data = img.get_fdata()
original_affine = img.affine
header = img.header

# Load the transformation matrix (xfm mat)
xfm_mat = np.loadtxt(affine_f)
if xfm_mat.shape != (4, 4):
    raise ValueError(f"Transformation matrix must be 4x4, got shape {xfm_mat.shape}")

print(f"Original shape: {data.shape}")
print(f"Original affine:\n{np.array2string(original_affine, precision=4, suppress_small=True)}")
print(f"Transformation matrix:\n{np.array2string(xfm_mat, precision=4, suppress_small=True)}")

# %%
# Apply the transformation matrix to compute the new affine
# If xfm_mat is a world-to-world transformation: new_affine = xfm_mat @ original_affine
# Extract voxel sizes from the transformed affine matrix (norms of column vectors)
# This works correctly even when the image is tilted/rotated
new_affine = xfm_mat @ original_affine
target_voxel_sizes = np.sqrt(np.sum(new_affine[:3, :3] ** 2, axis=0))
original_voxel_sizes = np.sqrt(np.sum(original_affine[:3, :3] ** 2, axis=0))
print(f"Original voxel sizes: [{original_voxel_sizes[0]:.2f}, {original_voxel_sizes[1]:.2f}, {original_voxel_sizes[2]:.2f}] mm")
print(f"Target voxel sizes: [{target_voxel_sizes[0]:.2f}, {target_voxel_sizes[1]:.2f}, {target_voxel_sizes[2]:.2f}] mm")

# Create target affine based on force_isotropic flag
target_rotation = new_affine[:3, :3]
# Normalize rotation matrix columns to get unit direction vectors
target_directions = target_rotation / (np.linalg.norm(target_rotation, axis=0, keepdims=True) + 1e-10)

if force_isotropic:
    # Resample to isotropic using minimum voxel size to ensure uniform resolution
    # This prevents loss of resolution in some areas and gain in others after transformation
    # Round to 2 decimals for target voxel size (small uniform scale change is acceptable)
    target_voxel_size = np.round(np.min(target_voxel_sizes), 2)
    print(f"Target isotropic voxel size: {target_voxel_size:.2f} mm")
    # Scale by isotropic voxel size
    target_affine = np.eye(4)
    target_affine[:3, :3] = target_directions * target_voxel_size
else:
    # Preserve original anisotropic voxel sizes
    print(f"Preserving anisotropic voxel sizes: [{target_voxel_sizes[0]:.2f}, {target_voxel_sizes[1]:.2f}, {target_voxel_sizes[2]:.2f}] mm")
    # Scale by original anisotropic voxel sizes
    target_affine = np.eye(4)
    target_affine[:3, :3] = target_directions * target_voxel_sizes
    # For compatibility with later code that uses target_voxel_size
    target_voxel_size = np.min(target_voxel_sizes)

target_affine[:3, 3] = 0  # Will be adjusted after calculating bounding box
target_affine[3, 3] = 1.0  # Homogeneous coordinate

# Calculate the transformation from original voxel space to target voxel space
# vox2vox: transforms coordinates from original voxel space to target voxel space
# Formula: target_vox = inv(target_affine) @ original_affine @ original_vox
# We'll adjust the translation after calculating the bounding box
vox2vox = np.linalg.inv(target_affine) @ original_affine

print(f"Target affine:\n{np.array2string(target_affine, precision=4, suppress_small=True)}")
print(f"Voxel-to-voxel transformation:\n{np.array2string(vox2vox, precision=4, suppress_small=True)}")

# %%
# Calculate target shape based on the bounding box of the original image
# We need to ensure full coverage after transformation, so we'll transform all corners
# and add padding to account for interpolation and rotation effects
shape = data.shape[:3]

# Get all 8 corners of the original image in voxel space (homogeneous coordinates)
corners_vox = np.array([
    [0, 0, 0, 1],
    [shape[0], 0, 0, 1],
    [0, shape[1], 0, 1],
    [0, 0, shape[2], 1],
    [shape[0], shape[1], 0, 1],
    [shape[0], 0, shape[2], 1],
    [0, shape[1], shape[2], 1],
    [shape[0], shape[1], shape[2], 1],
]).T

# Transform corners to world space using original affine, then to target voxel space
corners_world = original_affine @ corners_vox
corners_target_vox = np.linalg.inv(target_affine) @ corners_world

# Find bounding box in target space
# The 8 corners already give us the exact bounding box of the transformed image
min_corner = np.min(corners_target_vox[:3], axis=1)
max_corner = np.max(corners_target_vox[:3], axis=1)

# Add minimal padding only for interpolation edge cases and rounding errors
# The transformation effects are already accounted for by the corner transformation
voxel_padding = 2  # Small fixed padding (2 voxels) for interpolation safety

min_corner = min_corner - voxel_padding
max_corner = max_corner + voxel_padding

# Calculate target shape - this is the minimum size needed to cover all transformed data
target_shape = np.ceil(max_corner - min_corner).astype(int)
print(f"Target shape: {target_shape} (original: {shape})")
size_change = target_shape / shape
print(f"Size change: [{size_change[0]:.2f}, {size_change[1]:.2f}, {size_change[2]:.2f}]")

# Adjust affine translation to account for the new origin
target_affine[:3, 3] = target_affine[:3, :3] @ min_corner

# %%
# Resample the image using affine_transform
# scipy.ndimage.affine_transform uses pull-back: for each output voxel,
# it finds the corresponding input voxel using the inverse transformation
# Formula: output[out_coords] = input[inverse_transform(out_coords)]
# 
# Transformation: out_vox = vox2vox @ in_vox
# For output array index out_idx: out_vox = out_idx + min_corner
# So: in_vox = inv(vox2vox) @ (out_idx + min_corner)
#     in_vox = inv(vox2vox)[:3, :3] @ out_idx + inv(vox2vox)[:3, 3] + inv(vox2vox)[:3, :3] @ min_corner
inv_vox2vox = np.linalg.inv(vox2vox)
transform_matrix = inv_vox2vox[:3, :3]
# Offset = translation part + adjustment for min_corner
offset = inv_vox2vox[:3, 3] + transform_matrix @ min_corner

print(f"Resampling image...")
print(f"Transform matrix shape: {transform_matrix.shape}")
print(f"Offset: [{offset[0]:.2f}, {offset[1]:.2f}, {offset[2]:.2f}]")
resampled_data = affine_transform(
    data,
    transform_matrix,
    offset=offset,
    output_shape=target_shape,
    order=interpolation_order ,
    mode='constant',
    cval=0.0,
    prefilter=True
)

print(f"Resampled shape: {resampled_data.shape}")
print(f"Resampled data range: [{resampled_data.min():.2f}, {resampled_data.max():.2f}]")

# %%
# Create final affine for saved image
# If force_affine_ras is True, use RAS orientation; otherwise use the preserved orientation
# Note: We only change the affine matrix metadata, not the data itself
if force_affine2ref:

    print('Fixing affine to reference...')
    ref_img = nib.load(ref_f)
    ref_affine = ref_img.affine
    ref_shape = ref_img.shape[:3]
    print(f"Reference affine:\n{np.array2string(ref_affine, precision=4, suppress_small=True)}")
    print(f"Reference shape: {ref_shape}")

    # Create RAS-oriented affine with correct resolution
    # R (Right) = +X, A (Anterior) = +Y, S (Superior) = +Z
    final_affine = np.eye(4)
    if force_isotropic:
        final_affine[:3, :3] = np.diag([target_voxel_size] * 3)
    else:
        final_affine[:3, :3] = np.diag(target_voxel_sizes)

    # Align centers: calculate center of resampled data and reference in world space
    # Then adjust translation so centers align
    resampled_shape = resampled_data.shape[:3]
    resampled_center_vox = np.array([s / 2.0 for s in resampled_shape] + [1])
    resampled_center_world = target_affine @ resampled_center_vox
    
    ref_center_vox = np.array([s / 2.0 for s in ref_shape] + [1])
    ref_center_world = ref_affine @ ref_center_vox
    
    # Adjust translation so that resampled center maps to reference center
    # final_affine @ resampled_center_vox = ref_center_world
    # final_affine[:3, :3] @ resampled_center_vox[:3] + final_affine[:3, 3] = ref_center_world[:3]
    # Therefore: final_affine[:3, 3] = ref_center_world[:3] - final_affine[:3, :3] @ resampled_center_vox[:3]
    final_affine[:3, 3] = ref_center_world[:3] - final_affine[:3, :3] @ resampled_center_vox[:3]
    
    print(f"Resampled center (world): [{resampled_center_world[0]:.4f}, {resampled_center_world[1]:.4f}, {resampled_center_world[2]:.4f}]")
    print(f"Reference center (world): [{ref_center_world[0]:.4f}, {ref_center_world[1]:.4f}, {ref_center_world[2]:.4f}]")
    print(f"Updating affine metadata to align centers with reference (data unchanged)")
else:
    final_affine = target_affine
affine_type = "isotropic" if force_isotropic else "anisotropic"
print(f"Final affine ({affine_type}):\n{np.array2string(final_affine, precision=4, suppress_small=True)}")

final_data = resampled_data

# Create new image with final affine
new_img = nib.Nifti1Image(final_data.astype(data.dtype), final_affine, header)
new_img.header.set_xyzt_units('mm', 'sec')

# Save the result
print(f"Saving transformed image: {output_f}")
nib.save(new_img, output_f)
print(f"Done! Output saved to: {output_f}")

# %%
