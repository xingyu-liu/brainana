#!/usr/bin/env python3
"""
Simple test script for skullstripping function using FastSurferCNN
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent))

from FastSurferCNN.inference.segmentation import run_segmentation

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    # Test parameters
    input_image = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/EPI/site-caltech_sub-032184_ses-001_task-movie_run-3_EPI.nii.gz'
    modal = 'func'
    # FastSurferCNN uses output_dir (directory) instead of output_path (file)
    output_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/EPI/test_skullstripping_fscnn'
    
    # FastSurferCNN configuration
    config = {
        'batch_size': 1,
        'threads': 8
    }
    
    logger.info("=" * 80)
    logger.info("Test: testing FastSurferCNN segmentation function")
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
        result = run_segmentation(
            input_image=input_image,
            modal=modal,
            output_dir=output_dir,
            device_id='auto',
            logger=logger,
            output_data_format='nifti',
            enable_crop_2round=True,
            plane_weight_coronal=0,
            plane_weight_axial=0.6,
            plane_weight_sagittal=0.4,
            use_mixed_model=False,
        )
        
        logger.info("=" * 80)
        logger.info("Test: segmentation completed successfully!")
        logger.info(f"Test: result={result}")
        logger.info("=" * 80)
        
        # Verify output file exists
        brain_mask_path = result.get('brain_mask')
        if brain_mask_path and Path(brain_mask_path).exists():
            logger.info(f"Test: brain mask created at: {brain_mask_path}")
            logger.info(f"Test: file size={Path(brain_mask_path).stat().st_size} bytes")
        else:
            logger.error(f"Test: brain mask not found at: {brain_mask_path}")
            
    except Exception as e:
        logger.error(f"Test: failed with error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
