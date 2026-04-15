# %%
import nibabel as nib
import numpy as np
from pathlib import Path
import shutil
from scipy import ndimage as ndi

# %%
subject_dir = Path("/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/surf_recon/sub-032310_fixclaustrum")
brain_f = subject_dir / "mri" / "brain.finalsurfs.mgz"
arm6_f = subject_dir / "mri" / "atlas-ARM6_fs.nii.gz"
seg_f = subject_dir / "mri" / "aparc.ARM2atlas+aseg.orig.mgz"

claustrum_f = subject_dir / "mri" / "claustrum_mask.nii.gz"

# %%
# use ARM6 atlas to grab the claustrum roi, and intersect with the seg file ones.
arm6_claustrum_dict = {504:1, 1504:2}
seg_claustrum_dict = {502:1, 1502:2}

# load the arm6 atlas data
arm6_data = nib.load(arm6_f).get_fdata().astype(np.int16)
claustrum_mask = np.zeros_like(arm6_data)
for key, value in arm6_claustrum_dict.items():
    claustrum_mask[arm6_data == key] = value

# morphological operations to clean up the claustrum mask: dilation of 1 voxel per label
structure = ndi.generate_binary_structure(rank=3, connectivity=1)
claustrum_mask_dilated = np.zeros_like(claustrum_mask)
for value in np.unique(claustrum_mask):
    if value == 0:
        continue
    label_mask = claustrum_mask == value
    dilated_label = ndi.binary_dilation(label_mask, structure=structure, iterations=1)
    claustrum_mask_dilated[dilated_label] = value
claustrum_mask = claustrum_mask_dilated

# load the seg data
seg_data = nib.load(seg_f).get_fdata().astype(np.int16)
seg_claustrum_mask = np.zeros_like(seg_data)
for key, value in seg_claustrum_dict.items():
    seg_claustrum_mask[seg_data == key] = value

# intersect each claustrum label independently with seg labels
claustrum_mask_intersection = np.zeros_like(claustrum_mask, dtype=np.int16)
for value in set(arm6_claustrum_dict.values()) & set(seg_claustrum_dict.values()):
    intersection = (claustrum_mask == value) & (seg_claustrum_mask == value)
    claustrum_mask_intersection[intersection] = value
claustrum_mask = claustrum_mask_intersection

# # save the claustrum mask
# nib.save(nib.Nifti1Image(claustrum_mask, nib.load(arm6_f).affine), claustrum_f)

# %% fill the claustrum to normalized wm value 
# 1. load the claustrum mask
brain_f_reader = nib.load(brain_f)
brain_data = brain_f_reader.get_fdata()

map_dict = {1:110, 2:110}

# 2. fill the claustrum to normalized wm value
brain_data_new = brain_data.copy()
for key, value in map_dict.items():
    brain_data_new[claustrum_mask == key] = value

# 3. copy the brain f to _orig.mgz use shutil.copy
shutil.copy(brain_f, str(brain_f).replace('.mgz', '_orig.mgz'))

# 4. save the brain f
nib.save(nib.MGHImage(brain_data_new, brain_f_reader.affine, brain_f_reader.header), 
    brain_f)
