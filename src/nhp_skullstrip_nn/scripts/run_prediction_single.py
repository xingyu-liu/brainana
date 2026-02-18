#!/usr/bin/env python3
"""
Single file prediction script for processing one NIfTI file.
"""

# %%
import os
import sys
from pathlib import Path

# Add src/ to path for nhp_mri_prep package (scripts/ -> nhp_mri_prep -> src)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from nhp_skullstrip_nn.inference.prediction import predict_volumes
from nhp_skullstrip_nn.utils.gpu import get_device
from nhp_skullstrip_nn.utils.log import setup_logging
from nhp_skullstrip_nn.model import ModelLoader

# %%
# anat
input_f = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat/sub-032116_ses-001_run-1_T1w.nii.gz'
model_f = '/home/star/github/brainana/src/nhp_skullstrip_nn/pretrained_model/T1w_brainmask.pth'

# # func
# model_f = '/home/star/github/brainana/src/nhp_skullstrip_nn/pretrained_model/EPI_brainmask.pth'
# input_f = '/mnt/DataDrive3/xliu/prep_test/brainana_test/surf_recon/sub-032_ses-02weeks_reuse/mri/func.nii.gz'

# Output: replace .nii.gz with _mask.nii.gz
output_f = input_f.replace('.nii.gz', '_mask.nii.gz')

# %%
# Setup logging
logger = setup_logging('nhp_skullstrip_nn.single_prediction')

# Remove logger name from output format
import logging
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
for handler in logger.handlers:
    handler.setFormatter(formatter)

# Get device
device = get_device()
logger.info(f"Using device: {device}")

# Convert device to device_id format for ModelLoader
if device.type == 'cuda':
    device_id = device.index if device.index is not None else 0
else:
    device_id = -1

# Load model
logger.info(f"Loading model from: {model_f}")
model = ModelLoader.load_model_from_file(
    model_path=model_f,
    device_id=device_id,
    config=None,
    logger=logger
)
logger.info("✓ Model loaded successfully")

# Create output directory if it doesn't exist
Path(output_f).parent.mkdir(parents=True, exist_ok=True)

# %%
# Run prediction on the single file
input_file = Path(input_f)
output_file = Path(output_f)

logger.info(f"Input:  {input_file}")
logger.info(f"Output: {output_file}")

try:
    result = predict_volumes(
        model=model,
        input_image=str(input_file),
        output_path=str(output_file),
        plot_QC_snaps=True,
        save_prob_map=False,
        verbose=True
    )
    logger.info(f"✓ Successfully processed: {input_file.name}")
    logger.info(f"  Output saved to: {output_file}")

except Exception as e:
    logger.error(f"✗ Failed to process {input_file.name}: {e}")
    import traceback
    logger.error(traceback.format_exc())

logger.info("Prediction completed!")