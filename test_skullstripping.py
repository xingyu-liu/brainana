#!/usr/bin/env python3
"""
Test script for skullstripping function.
"""

import logging
from pathlib import Path
from FastSurferCNN.inference.skullstripping import skullstripping

# Get the FastSurferCNN root directory (where pretrained_model folder is located)
# This should point to the directory containing the pretrained_model folder
FASTSURFER_ROOT = Path(__file__).parent / "FastSurferCNN"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# Test parameters
input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_2pass_seg.nii.gz"
modal = "anat"
output_path = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test.nii.gz"

def main():
    logger.info("=" * 80)
    logger.info("Testing skullstripping function")
    logger.info("=" * 80)
    logger.info(f"Input image: {input_image}")
    logger.info(f"Modal: {modal}")
    logger.info(f"Output path: {output_path}")
    logger.info("=" * 80)
    
    # Check if input file exists
    if not Path(input_image).exists():
        logger.error(f"Input image not found: {input_image}")
        return
    
    try:
        # Run skullstripping with config specifying base_dir
        config = {
            'base_dir': str(FASTSURFER_ROOT)
        }
        
        result = skullstripping(
            input_image=input_image,
            modal=modal,
            output_path=output_path,
            device_id='auto',
            logger=logger,
            config=config
        )
        
        logger.info("=" * 80)
        logger.info("Skullstripping completed successfully!")
        logger.info(f"Result: {result}")
        logger.info("=" * 80)
        
        # Verify output file exists
        output_file = Path(output_path)
        if output_file.exists():
            logger.info(f"Output file created: {output_path}")
            logger.info(f"File size: {output_file.stat().st_size} bytes")
        else:
            logger.error(f"Output file not found: {output_path}")
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()

