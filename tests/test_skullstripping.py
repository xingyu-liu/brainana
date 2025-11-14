#!/usr/bin/env python3
"""
Simple test script for skullstripping function
"""

from macacaMRINN.inference.prediction import skullstripping

def main():
    # Test parameters
    input_image = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/EPI/site-caltech_sub-032184_ses-001_task-movie_run-3_EPI.nii.gz'
    modal = 'func'
    output_path = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/training_output/test/EPI/test.nii.gz'
    
    print(f"Starting skullstripping...")
    print(f"Input: {input_image}")
    print(f"Modal: {modal}")
    print(f"Output: {output_path}")
    
    try:
        result = skullstripping(input_image, modal, output_path)
        print(f"Skullstripping completed successfully!")
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
