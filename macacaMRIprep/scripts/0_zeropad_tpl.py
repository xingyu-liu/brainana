# %%
import os
import sys
import numpy as np
import nibabel as nib

#%%
data_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat/anat_freddie_conform'
template_f = os.path.join(data_dir, 'template.nii.gz')
zeropadded_f = os.path.join(data_dir, 'template_padded.nii.gz')
# percentage of padding on each side
padding_percentage = 0.2


# %%
# Load the template image
print(f"Loading template: {template_f}")
img = nib.load(template_f)
data = img.get_fdata()
affine = img.affine.copy()
header = img.header.copy()

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
print(f"Saving zero-padded template: {zeropadded_f}")
nib.save(new_img, zeropadded_f)
print(f"Done!")
