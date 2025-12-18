'''Apply a given affine transformation to an image and save the result as a new image.'''

#%%
import os
import numpy as np
import nibabel as nib
import subprocess

# %%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat/anat_freddie'
input_f = os.path.join(data_dir, 'input.nii.gz')
template_f = os.path.join(data_dir, 'template_padded.nii.gz')
xfm_f = os.path.join(data_dir, 'scanner2T1w.mat')

interpolation_order = 3
force_isotropic = True

if force_isotropic:
    output_f = input_f.replace('.nii.gz', '_registered_iso.nii.gz')
else:
    output_f = input_f.replace('.nii.gz', '_registered_aniso.nii.gz')

# %%
# Validate input file exists
if not os.path.exists(input_f):
    raise FileNotFoundError(f"Input file not found: {input_f}")
if not os.path.exists(template_f):
    raise FileNotFoundError(f"Template file not found: {template_f}")
if not os.path.exists(xfm_f):
    raise FileNotFoundError(f"xfm file not found: {xfm_f}")

# Ensure output directory exists
output_dir = os.path.dirname(output_f)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

# %% Load the original affine and determine the target voxel sizes
print(f"Loading image: {input_f}")
img = nib.load(input_f)
original_affine = img.affine

original_voxel_sizes = np.sqrt(np.sum(original_affine[:3, :3] ** 2, axis=0))
print(f"Original voxel sizes: {np.array2string(original_voxel_sizes, precision=4, suppress_small=True)} mm")

if force_isotropic:
    # Resample to isotropic using minimum voxel size to ensure uniform resolution
    # This prevents loss of resolution in some areas and gain in others after transformation
    # Round to 2 decimals for target voxel size (small uniform scale change is acceptable)
    target_voxel_size = np.round(np.min(original_voxel_sizes), 2)
    target_voxel_sizes = np.full((3,), target_voxel_size)
else:
    target_voxel_sizes = np.round(original_voxel_sizes, 2)

print(f"Target voxel sizes: {target_voxel_sizes} mm")

# %%
# resample template to the same resolution as the input
# by 3dresample -dxyz with target_voxel_sizes
template_resampled_f = template_f.replace('.nii.gz', '_res-inputcomformed.nii.gz')

if os.path.exists(template_resampled_f):
    # remove the file
    os.remove(template_resampled_f)
    print(f"Removed existing template resampled file: {template_resampled_f}")

cmd = [
    '3dresample',
    '-dxyz', str(target_voxel_sizes[0]), str(target_voxel_sizes[1]), str(target_voxel_sizes[2]),
    '-input', template_f,
    '-prefix', template_resampled_f
]
print(f"Running 3dresample to resample template to the same resolution as the input...")
print(f"Command: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
print(f"Done! Template resampled to: {template_resampled_f}")

# %% 
# apply the affine transformation to the input image to the resampled template
# Use flirt -applyxfm since we have a FLIRT transform (.mat file)
cmd = [
    'flirt',
    '-in', input_f,
    '-ref', template_resampled_f,
    '-out', output_f,
    '-applyxfm',
    '-init', xfm_f,
    '-interp', 'trilinear'
]
print(f"Running flirt to apply the affine transformation to the input image to the resampled template...")
print(f"Command: {' '.join(cmd)}")
subprocess.run(cmd, check=True)
print(f"Done! Output saved to: {output_f}")
