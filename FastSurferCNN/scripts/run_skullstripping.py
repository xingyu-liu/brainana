#!/usr/bin/env python3
"""
Test script for skullstripping function.
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

from FastSurferCNN.inference.skullstripping import skullstripping

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# # anat 
# input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_anat_2pass_seg.nii.gz"
# output_dir = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_skullstripping_anat"
# modal = "anat"
# data_format = "nifti"
# weight_coronal, weight_axial, weight_sagittal = 0.4, 0.4, 0.2

# func
input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_func_big.nii.gz"
output_dir = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_skullstripping_func"
modal = "func"
data_format = "nifti"
weight_coronal, weight_axial, weight_sagittal = 0.4, 0.4, 0.2

# %%
def main():
    logger.info("=" * 80)
    logger.info("Test: testing skullstripping function")
    logger.info("=" * 80)
    logger.info(f"Test: input_image={input_image}")
    logger.info(f"Test: modal={modal}")
    logger.info(f"Test: output_dir={output_dir}")
    logger.info("=" * 80)
    
    # Check if input file exists
    if not Path(input_image).exists():
        logger.error(f"Test: input image not found: {input_image}")
        return
    
    try:

        result = skullstripping(
            input_image=input_image,
            modal=modal,
            output_dir=output_dir,
            device_id='auto',
            logger=logger,
            config=None,
            output_data_format=data_format,
            enable_crop_2round=True,
            plane_weight_coronal=weight_coronal,
            plane_weight_axial=weight_axial,
            plane_weight_sagittal=weight_sagittal,
        )
        
        logger.info("=" * 80)
        logger.info("Test: skullstripping completed successfully")
        logger.info(f"Test: result={result}")
        logger.info("=" * 80)
        
        # Verify output file exists
        output_file = Path(result['brain_mask'])
        if output_file.exists():
            logger.info(f"Test: output file created={result['brain_mask']}, size={output_file.stat().st_size} bytes")
        else:
            logger.error(f"Test: output file not found: {result['brain_mask']}")
            
    except Exception as e:
        logger.error(f"Test: failed with error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()

