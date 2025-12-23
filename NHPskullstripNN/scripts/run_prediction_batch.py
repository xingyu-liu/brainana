#!/usr/bin/env python3
"""
Batch prediction script for processing multiple NIfTI files.
"""

# %%
import os
from pathlib import Path
from NHPskullstripNN.inference.prediction import predict_volumes
from NHPskullstripNN.config import TrainingConfig
from NHPskullstripNN.utils.gpu import get_device
from NHPskullstripNN.utils.log import setup_logging
from NHPskullstripNN.model import ModelLoader

# # %%
# # anat
# test_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat'
# # model_f = '/home/star/github/banana/NHPskullstripNN/pretrained_model/T1w_brainmask.pth'
# model_f = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/NHPskullstripNN_training/training_output/T1w_seg-brainmask_v2/checkpoints/best_model.pth'
# model_name = 'v2'

# func
test_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/func'
model_f = '/home/star/github/banana/NHPskullstripNN/pretrained_model/EPI_brainmask.pth'
# model_f = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/NHPskullstripNN_training/training_output/EPI_seg-brainmask_v1/checkpoints/best_model.pth'
model_name = 'v3'

output_dir = test_dir + f'/{model_name}'

# %%
# Setup logging
logger = setup_logging('NHPskullstripNN.batch_prediction')

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
Path(output_dir).mkdir(parents=True, exist_ok=True)
logger.info(f"Output directory: {output_dir}")

# List all .nii.gz files in the test_dir
test_path = Path(test_dir)
nii_files = list(test_path.glob('*.nii.gz'))
logger.info(f"Found {len(nii_files)} NIfTI files to process")

if len(nii_files) == 0:
    logger.warning(f"No .nii.gz files found in {test_dir}")
else:
    # Process each file
    for idx, input_file in enumerate(nii_files, 1):
        print(f"\n{'='*60}")
        logger.info(f"Processing file {idx}/{len(nii_files)}: {input_file.name}")
        print(f"{'='*60}")
        
        # Create output path (same name as input, in output_dir)
        output_file = Path(output_dir) / input_file.name
        
        try:
            # Run prediction
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
            continue

print(f"\n{'='*60}")
logger.info("Batch prediction completed!")
print(f"{'='*60}")