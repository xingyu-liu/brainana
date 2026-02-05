# %%
import os
import sys
from pathlib import Path

# Add src/ to path for nhp_mri_prep package (scripts/ -> nhp_mri_prep -> src)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from nhp_mri_prep.operations.registration import ants_register
import logging

# %%
moving_f = '/home/star/github/atlas/macaque/NMT2/NMT2Sym/volume/tpl-NMT2Sym_res-025_T1w_brain.nii.gz'
fixed_f = '/home/star/github/atlas/macaque/D99/tpl-D99_res-025_T1w.nii.gz'
xfm_type = 'syn'

output_f = '/home/star/github/atlas/macaque/xfm/from-NMT2Sym_to-D99.nii.gz'

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
