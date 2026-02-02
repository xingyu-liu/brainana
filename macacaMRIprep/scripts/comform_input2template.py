# %%
import os
import sys
import numpy as np
import nibabel as nib
from pathlib import Path
import subprocess

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from NHPskullstripNN.inference.prediction import skullstripping

#%%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat/anat_marge_upright_conform'

input_f = os.path.join(data_dir, 'input.nii.gz')
mask_f = os.path.join(data_dir, 'mask.nii.gz')
brain_f = os.path.join(data_dir, 'brain.nii.gz')
conformed_f = os.path.join(data_dir, 'conformed.nii.gz')

padding_percentage = 0.2
template_f = os.path.join(data_dir, 'template.nii.gz')

xfm_f = os.path.join(data_dir, 'scanner2T1w.mat')

# %%
# Validate input files exist
if not os.path.exists(input_f):
    raise FileNotFoundError(f"Input file not found: {input_f}")
if not os.path.exists(template_f):
    raise FileNotFoundError(f"Template file not found: {template_f}")

# Ensure output directory exists
output_dir = os.path.dirname(mask_f) if os.path.dirname(mask_f) else data_dir
if not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    print(f"Created output directory: {output_dir}")

# %%
# 1. pad the template to ensure the input image is fully contained within the template
# Load the template image
print(f"Loading template: {template_f}")
img = nib.load(template_f)
data = img.get_fdata()
affine = img.affine.copy()
header = img.header.copy()

# Handle 4D images: if image has 4 dimensions, average the last dimension
# This aligns with how NHPskullstripNN handles 4D data
if data.ndim == 4:
    print(f"Warning: 4D image detected (shape: {data.shape}). Averaging the last dimension.")
    data = np.mean(data, axis=-1)
    print(f"Converted to 3D shape: {data.shape}")

original_shape = data.shape[:3]
print(f"Original shape: {original_shape}")

# Calculate padding amounts for each dimension
# padding_percentage is applied on each side, so total padding is 2 * padding_percentage
pad_amounts = (np.array(original_shape) * padding_percentage).astype(int)
print(f"Padding amounts (per side): {pad_amounts}")

# Calculate new shape
new_shape = original_shape + 2 * pad_amounts
print(f"New shape: {new_shape}")

# Pad the data with zeros
# numpy.pad format: ((before_1, after_1), (before_2, after_2), (before_3, after_3), ...)
pad_width = tuple((pad, pad) for pad in pad_amounts)
# If data has more than 3 dimensions, pad only the first 3
if len(data.shape) > 3:
    pad_width = pad_width + ((0, 0),) * (len(data.shape) - 3)
    
padded_data = np.pad(data, pad_width, mode='constant', constant_values=0)
print(f"Padded data shape: {padded_data.shape}")

# Update the affine matrix to account for padding
# When we pad on the left/top/front, the origin shifts by -pad_amounts in voxel space
# In world space, this shift is: affine[:3, :3] @ (-pad_amounts)
# So the new translation is: original_translation + affine[:3, :3] @ (-pad_amounts)
pad_shift_voxel = -pad_amounts.astype(float)
pad_shift_world = affine[:3, :3] @ pad_shift_voxel

print(f"Padding shift in voxel space: {pad_shift_voxel}")
print(f"Padding shift in world space: {pad_shift_world}")

# Update the affine translation
new_affine = affine.copy()
new_affine[:3, 3] = affine[:3, 3] + pad_shift_world

print(f"Original affine translation: {affine[:3, 3]}")
print(f"New affine translation: {new_affine[:3, 3]}")

# Create new image with padded data and updated affine
new_img = nib.Nifti1Image(padded_data.astype(data.dtype), new_affine, header)
new_img.header.set_xyzt_units('mm', 'sec')

# Save the result
zeropadded_f = template_f.replace('.nii.gz', '_padded.nii.gz')
print(f"Saving zero-padded template: {zeropadded_f}")
nib.save(new_img, zeropadded_f)

# Validate the saved file exists
if not os.path.exists(zeropadded_f):
    raise RuntimeError(f"Failed to save zero-padded template: {zeropadded_f}")
print(f"Done! Zero-padded template saved successfully.")

# update the template_f
template_f = zeropadded_f
print(f"Updated template_f: {template_f}")

# %%
# 2. skullstripping the input image
# skullstripping with NHPskullstripNN
print(f"Starting skullstripping for: {input_f}")
try:
    result = skullstripping(
        input_image=input_f,
        modal='anat',  # Use 'anat' for T1w, 'func' for EPI
        output_path=mask_f,
        device_id='auto'
    )
    print(f"Mask saved to: {result['brain_mask']}")
    
    # Validate mask file exists
    mask_output = result.get('brain_mask', mask_f)
    if not os.path.exists(mask_output):
        raise RuntimeError(f"Skullstripping failed: mask file not found at {mask_output}")
except Exception as e:
    print(f"Error during skullstripping: {e}")
    sys.exit(1)

# apply mask to input
print(f"Applying mask to input image...")
cmd = ['fslmaths', input_f, '-mas', mask_f, brain_f]
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    # Validate brain-extracted file exists
    if not os.path.exists(brain_f):
        raise RuntimeError(f"Failed to create brain-extracted image: {brain_f}")
    print(f"Brain-extracted image saved to: {brain_f}")
except subprocess.CalledProcessError as e:
    print(f"Error applying mask: {e.stderr}")
    sys.exit(1)
except Exception as e:
    print(f"Error validating brain-extracted image: {e}")
    sys.exit(1)

# %%
# 3. do xfm registration from input to template
cmd = [
    'flirt',
    '-in', brain_f,
    '-ref', template_f,
    '-dof', '6',
    '-searchrx', '-180', '180',
    '-searchry', '-180', '180',
    '-searchrz', '-180', '180',
    '-omat', xfm_f
]
print(f"Running FLIRT registration...")
print(f"Command: {' '.join(cmd)}")
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    # Validate transformation matrix exists
    if not os.path.exists(xfm_f):
        raise RuntimeError(f"Failed to create transformation matrix: {xfm_f}")
    print(f"Done! Transformation matrix saved to: {xfm_f}")
except subprocess.CalledProcessError as e:
    print(f"Error during FLIRT registration: {e.stderr}")
    sys.exit(1)
except Exception as e:
    print(f"Error validating transformation matrix: {e}")
    sys.exit(1)

# %%
# 4. apply the affine transformation to the input image to the resampled template
# to best preserve the image quality, we resample the template to the min resolution as the input (force isotropic)

# 4.1 resample the template to the same resolution as the input
# Load the original affine and determine the target voxel sizes
print(f"Loading image: {input_f}")
img = nib.load(input_f)
original_affine = img.affine

original_voxel_sizes = np.sqrt(np.sum(original_affine[:3, :3] ** 2, axis=0))
print(f"Original voxel sizes: {np.array2string(original_voxel_sizes, precision=4, suppress_small=True)} mm")

# Resample to isotropic using minimum voxel size to ensure uniform resolution
# This prevents loss of resolution in some areas and gain in others after transformation
# Round to 2 decimals for target voxel size (small uniform scale change is acceptable)
target_voxel_size = np.round(np.min(original_voxel_sizes), 2)
if target_voxel_size <= 0:
    raise ValueError(f"Invalid target voxel size: {target_voxel_size} mm")
target_voxel_sizes = np.full((3,), target_voxel_size)

print(f"Target voxel sizes: {target_voxel_sizes} mm")

# resample template to the same resolution as the input
# by 3dresample -dxyz with target_voxel_sizes
template_resampled_f = template_f.replace('.nii.gz', '_res-input.nii.gz')

if os.path.exists(template_resampled_f):
    # remove the file
    os.remove(template_resampled_f)
    print(f"Removed existing template resampled file: {template_resampled_f}")

cmd = [
    '3dresample',
    '-dxyz', str(target_voxel_sizes[0]), str(target_voxel_sizes[1]), str(target_voxel_sizes[2]),
    '-input', template_f,
    '-prefix', template_resampled_f,
    '-rmode', 'Cu'
]
print(f"Running 3dresample to resample template to the same resolution as the input...")
print(f"Command: {' '.join(cmd)}")
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    # Validate resampled template exists
    if not os.path.exists(template_resampled_f):
        raise RuntimeError(f"Failed to create resampled template: {template_resampled_f}")
    print(f"Done! Template resampled to: {template_resampled_f}")
except subprocess.CalledProcessError as e:
    print(f"Error during template resampling: {e.stderr}")
    sys.exit(1)
except Exception as e:
    print(f"Error validating resampled template: {e}")
    sys.exit(1)

# update the template_f
template_f = template_resampled_f
print(f"Updated template_f: {template_f}")

# %% 
# 4.2 apply the affine transformation to the input image to the resampled template
# Use flirt -applyxfm since we have a FLIRT transform (.mat file)
cmd = [
    'flirt',
    '-in', input_f,
    '-ref', template_f,
    '-out', conformed_f,
    '-applyxfm',
    '-init', xfm_f,
    '-interp', 'trilinear'
]
print(f"Running flirt to apply the affine transformation to the input image to the resampled template...")
print(f"Command: {' '.join(cmd)}")
try:
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    # Validate registered output exists
    if not os.path.exists(conformed_f):
        raise RuntimeError(f"Failed to create registered image: {conformed_f}")
    print(f"Done! Output saved to: {conformed_f}")
except subprocess.CalledProcessError as e:
    print(f"Error during affine transformation application: {e.stderr}")
    sys.exit(1)
except Exception as e:
    print(f"Error validating registered image: {e}")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"Pipeline completed successfully!")
print(f"Final registered image: {conformed_f}")
print(f"{'='*60}")
