# %%
import os
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt

# %%
root_dir = '/mnt/DataDrive3/xliu/prep_test/banana_test/surf_recon/sub-032_ses-02weeks_reuse/mri'
mask_f = os.path.join(root_dir, 'mask.nii.gz')
T1w_f = os.path.join(root_dir, 'T1.nii.gz')
T2w_f = os.path.join(root_dir, 'T2.nii.gz')

numerator_label = 'T1w'
if numerator_label == 'T1w':
    dominator_label = 'T2w'
else:
    dominator_label = 'T1w'

# %%
# get the T1w/T2w ratio only for the masked area
mask = nib.load(mask_f).get_fdata().astype(int)
T1w = nib.load(T1w_f).get_fdata()
T2w = nib.load(T2w_f).get_fdata()

if numerator_label == 'T1w':
    numerator = T1w
    denominator = T2w
else:
    numerator = T2w
    denominator = T1w

# handle the case where denominator is 0
denominator[denominator == 0] = 1e-6
ratio = numerator / denominator *100
ratio[mask == 0] = 0

# %% 
# normalize the T1wT2wRatio to the T1w intensity range (masked area)
# with the same 50 and 95 percentile as the T1w intensity
percentile_pct = [5, 95]
numerator_intensity_low, numerator_intensity_high = np.percentile(numerator[mask != 0], percentile_pct)
ratio_low, ratio_high = np.percentile(ratio[mask != 0], percentile_pct)

ratio_normalized = (ratio - ratio_low) * (numerator_intensity_high - numerator_intensity_low) / (ratio_high - ratio_low) + numerator_intensity_low

# %%
# clip the +3 IQR values 
q1 = np.percentile(ratio_normalized[mask != 0], 25)
q3 = np.percentile(ratio_normalized[mask != 0], 75)
iqr = q3 - q1
ratio_normalized[mask != 0] = np.clip(ratio_normalized[mask != 0], 0, q3 + 2*iqr)

# %% plot
data2plot = ratio_normalized

plt.hist(data2plot[mask != 0], bins=100)
plt.show()

# %%
# stitch the mask == 0 part of T1 to T1wT2wRatio_normalized
ratio_normalized[mask == 0] = numerator[mask == 0]
ratio_normalized[ratio_normalized < 0] = 0

# %%
# save the T1wT2wRatio_normalized
output_f = os.path.join(root_dir, f'{numerator_label}{dominator_label}Ratio.nii.gz')
img = nib.Nifti1Image(ratio_normalized, nib.load(T1w_f).affine, nib.load(T1w_f).header)
img.to_filename(output_f, dtype=np.float32)

# %%
