'''apply its own affine xfm on the image and save the result as a new image,
to correct the tilted image to upright orientation'''

#%%
import os
import numpy as np
import nibabel as nib
from scipy.ndimage import affine_transform

# %%
input_f = '/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_reorient_upright/sub-baby31/ses-240710/anat/sub-baby31_ses-240710_run-2_T1w_v2.nii.gz'
output_f = input_f.replace('.nii.gz', '_v3.nii.gz')
order = 3

# %%
# Validate input file exists
if not os.path.exists(input_f):
    raise FileNotFoundError(f"Input file not found: {input_f}")

# Ensure output directory exists
output_dir = os.path.dirname(output_f)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

# Load the image
print(f"Loading image: {input_f}")
img = nib.load(input_f)
data = img.get_fdata()
affine = img.affine
header = img.header

print(f"Original shape: {data.shape}")
print(f"Original affine:\n{affine}")

# %%
# Extract voxel sizes from affine matrix (norms of column vectors)
# This works correctly even when the image is tilted/rotated
voxel_sizes = np.sqrt(np.sum(affine[:3, :3] ** 2, axis=0))
print(f"Voxel sizes: {voxel_sizes}")

# Create upright affine (identity rotation, diagonal scaling)
# This will "bake in" the current affine transformation
upright_affine = np.eye(4)
upright_affine[:3, :3] = np.diag(voxel_sizes)
upright_affine[:3, 3] = 0  # Will be adjusted after calculating bounding box

# Calculate the transformation from original space to upright space
# vox2vox transformation: from original voxel space to target voxel space
vox2vox = np.linalg.inv(upright_affine) @ affine

print(f"Target upright affine:\n{upright_affine}")
print(f"Voxel-to-voxel transformation:\n{vox2vox}")

# %%
# Calculate target shape based on the bounding box of the original image
# We need to ensure full coverage after rotation, so we'll transform all corners
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

# Transform corners to world space, then to target voxel space
corners_world = affine @ corners_vox
corners_target_vox = np.linalg.inv(upright_affine) @ corners_world

# Find bounding box in target space
# The 8 corners already give us the exact bounding box of the rotated image
min_corner = np.min(corners_target_vox[:3], axis=1)
max_corner = np.max(corners_target_vox[:3], axis=1)

# Add minimal padding only for interpolation edge cases and rounding errors
# The rotation effects are already accounted for by the corner transformation
voxel_padding = 2  # Small fixed padding (2 voxels) for interpolation safety

min_corner = min_corner - voxel_padding
max_corner = max_corner + voxel_padding

# Calculate target shape - this is the minimum size needed to cover all rotated data
target_shape = np.ceil(max_corner - min_corner).astype(int)
print(f"Target shape: {target_shape} (original: {shape})")
print(f"Size change: {target_shape / shape}")

# Adjust affine translation to account for the new origin
upright_affine[:3, 3] = upright_affine[:3, :3] @ min_corner

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
print(f"Offset: {offset}")
resampled_data = affine_transform(
    data,
    transform_matrix,
    offset=offset,
    output_shape=target_shape,
    order=order,  # linear interpolation
    mode='constant',
    cval=0.0,
    prefilter=True
)

print(f"Resampled shape: {resampled_data.shape}")
print(f"Resampled data range: [{resampled_data.min():.2f}, {resampled_data.max():.2f}]")

# %%
# Create new image with corrected affine
new_img = nib.Nifti1Image(resampled_data.astype(data.dtype), upright_affine, header)
new_img.header.set_xyzt_units('mm', 'sec')

# Save the result
print(f"Saving corrected image: {output_f}")
nib.save(new_img, output_f)
print(f"Done! Output saved to: {output_f}")

# %%