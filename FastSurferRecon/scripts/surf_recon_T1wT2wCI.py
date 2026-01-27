# %%
import os
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# %%
root_dir = '/mnt/DataDrive3/xliu/prep_test/banana_test/surf_recon/sub-032_ses-03months_reuse/others'
seg_f = os.path.join(root_dir, 'aparc.ARM2atlas+aseg.orig.nii.gz')
seg_lut_f = seg_f.replace('.nii.gz', '.tsv')
T1w_f = os.path.join(root_dir, 'T1.nii.gz')
T2w_f = os.path.join(root_dir, 'T2.nii.gz')

# %%
# load seg
seg = nib.load(seg_f).get_fdata().astype(int)
T1w = nib.load(T1w_f).get_fdata()
T2w = nib.load(T2w_f).get_fdata()

seg_lut = pd.read_csv(seg_lut_f, sep='\t')

# %%
# get gray matter intensity from T1w image using seg
# mask should be keys with "region" column == 'cortex'
GM_values = seg_lut[seg_lut['region'] == 'cortex']['ID'].values
GM_mask = np.isin(seg, GM_values).astype(bool)

# %%
# get gray matter intensity from T1w and T2w image using seg
T1w_GM_intensity = T1w[GM_mask].mean()
T2w_GM_intensity = T2w[GM_mask].mean()

# compute scaled T2w with T1w_GM_intensity / T2w_GM_intensity * T2w
sT2w = T1w_GM_intensity / T2w_GM_intensity * T2w

# %% plot
data2plot = sT2w

plt.hist(data2plot[GM_mask], bins=100)
plt.show()

# %%
# compute CI from: (T1w−sT2w)/(T1w+sT2w)
combined_image = (T1w - sT2w) / (T1w + sT2w)
combined_image = np.nan_to_num(combined_image)

# %%
# save 
output_f = os.path.join(root_dir, 'T1wT2wCI.nii.gz')
img = nib.Nifti1Image(combined_image, nib.load(T1w_f).affine, nib.load(T1w_f).header)
img.to_filename(output_f, dtype=np.float32)

# %%
