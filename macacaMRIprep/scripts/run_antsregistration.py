# %%
import os
from pathlib import Path
from macacaMRIprep.operations.registration import ants_register
import logging

# %%
moving_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_UNC_v1_wd/a1/8d5f78f4b081cf0440e335028f98c9/sub-032_ses-06months_T2w.nii.gz'
fixed_f = '/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/dataset_UNC_v1_wd/a1/8d5f78f4b081cf0440e335028f98c9/sub-032_ses-06months_T1w.nii.gz'
xfm_type = 'rigid'

output_f = moving_f.replace('.nii.gz', f'_{xfm_type}.nii.gz')

# %%
# Set up working directory and output prefix
working_dir = os.path.dirname(output_f)
output_prefix = os.path.splitext(os.path.splitext(os.path.basename(output_f))[0])[0]  # Remove .nii.gz extensions


# setup logging so that it prints to the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Running ANTs registration:")
logger.info(f"  Moving image: {moving_f}")
logger.info(f"  Fixed image: {fixed_f}")
logger.info(f"  Working directory: {working_dir}")
logger.info(f"  Output prefix: {output_prefix}")
logger.info(f"  XFM type: {xfm_type}")

# Run ANTs registration
results = ants_register(
    fixedf=fixed_f,
    movingf=moving_f,
    working_dir=working_dir,
    output_prefix=output_prefix,
    xfm_type=xfm_type,
    logger=logger
)
