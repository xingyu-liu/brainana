# %%
import os
from pathlib import Path
from macacaMRIprep.operations.registration import ants_register

# %%
moving_f = '/mnt/DataDrive2/macaque/data_raw/macaque_mri/new_livingstone_test/bids_reorient_rotated/sub-baby31/ses-240710/anat/sub-baby31_ses-240710_run-2_T1w.nii.gz'
fixed_f = '/home/star/github/atlas/macaque/NMT2Sym/volume/tpl-NMT2Sym_res-05_T1w.nii.gz'
xfm_type = 'rigid'

output_f = moving_f.replace('.nii.gz', f'_{xfm_type}.nii.gz')


# %%
# Set up working directory and output prefix
working_dir = os.path.dirname(output_f)
output_prefix = os.path.splitext(os.path.splitext(os.path.basename(output_f))[0])[0]  # Remove .nii.gz extensions

# Run ANTs registration
print(f"Running ANTs registration:")
print(f"  Moving image: {moving_f}")
print(f"  Fixed image: {fixed_f}")
print(f"  Working directory: {working_dir}")
print(f"  Output prefix: {output_prefix}")
print(f"  XFM type: {xfm_type}")

results = ants_register(
    fixedf=fixed_f,
    movingf=moving_f,
    working_dir=working_dir,
    output_prefix=output_prefix,
    xfm_type=xfm_type
)

# %%
# Print results
print("\nRegistration completed successfully!")
print(f"  Registered image: {results.get('imagef_registered')}")
print(f"  Forward transform: {results.get('forward_transform')}")
print(f"  Inverse transform: {results.get('inverse_transform')}")
print(f"  Output prefix: {results.get('output_path_prefix')}")

# %%