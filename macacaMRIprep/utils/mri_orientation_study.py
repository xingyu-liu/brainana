# %%
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt
import os

# %%
data_dir = '/mnt/DataDrive3/xliu/prep_test/validate_orientation_test'
modal = 'anat'

data_true_f = os.path.join(data_dir, f'{modal}_true.nii.gz')
data_wrong_f = os.path.join(data_dir, f'{modal}_wrong.nii.gz')

# %% fake some data
data_true = nib.load(data_true_f)
affine_true = data_true.affine

# 1. flip the orientation
affine = affine_true.copy()
# it only has 3 axes, for each axis, it can be flipped or not, so flip_axis is a 3 tuple of 0 or 1
flip_axis = np.random.randint(0, 2, 3)
# make sure at least one axis is flipped
while np.sum(flip_axis) == 0:
    flip_axis = np.random.randint(0, 2, 3)

# 2. Reorder rows to mess up the orientation label
new_order = np.random.permutation(3)
# make sure the new order is not the same as the original order
while np.array_equal(new_order, np.arange(3)):
    new_order = np.random.permutation(3)
affine = affine[list(new_order) + [3]]

data_wrong = nib.Nifti1Image(data_true.get_fdata(), affine, header=data_true.header)
nib.save(data_wrong, data_wrong_f)

# %%