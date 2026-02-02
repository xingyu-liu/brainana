#!/usr/bin/env python3
"""
Test script for skullstripping function.
"""

import sys
import logging
from pathlib import Path

# Add src/ to path for fastsurfer_nn imports (scripts/ -> fastsurfer_nn -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from fastsurfer_nn.inference.segmentation import run_segmentation

# %%
# # # anat 
# input_dir = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/test_prediction/anat"
# input_image = f"{input_dir}/anat_marge_upright.nii.gz"
input_image = "/mnt/DataDrive3/xliu/prep_test/banana_test/surf_recon/sub-032_ses-03months_reuse/others/T1wT2wCI.nii.gz"

# surfrecon_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/fastsurfer_nn_training/test_surfrecon'
# input_image = f'{surfrecon_dir}/NMT2Sym_res-05_T1w.nii.gz'
# output_dir = f'{surfrecon_dir}/NMT2Sym_ras'
# input_image = f'{surfrecon_dir}/site-arcaro_sub-baby1_ses-anat_T1w.nii.gz'
# output_dir = f'{surfrecon_dir}/arcaro_baby1'
# input_image = f'{surfrecon_dir}/tpl-NMT2Sym_res-05_T1w_brain.nii.gz'
# output_dir = f'{surfrecon_dir}/NMT2Sym_brain_v2'
# input_image = f'{surfrecon_dir}/test_anat_2pass_seg.nii.gz'

output_dir = input_image.split('.nii')[0]

modal = "anat"
weight_axial, weight_coronal, weight_sagittal = 0.4, 0.4, 0.2
use_mixed_model = False
if use_mixed_model:
    weight_axial, weight_coronal, weight_sagittal = 1/3, 1/3, 1/3
enable_crop_2round = False

fix_roi_wm = False
roi_name = "V1"  # Use "V1" for ARM2 atlas (primary_visual_cortex). For other atlases, check ColorLUT for correct ROI name.
wm_thr = 0.5

if fix_roi_wm:
    output_dir = output_dir + f"_fix{roi_name}"

# # ------------------------------------------------------------
# # # func
# # input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/fastsurfer_nn_training/test_prediction_output/test_func.nii.gz"
# input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/fastsurfer_nn_training/test_prediction_output/test_func_res-2.nii.gz"
# output_dir = input_image.split('.nii')[0]

# modal = "func"
# data_format = "nifti"
# weight_axial, weight_coronal, weight_sagittal = 0.4, 0.4, 0.2
# use_mixed_model = False
# enable_crop_2round = False

# fix_roi_wm = False
# roi_name = None  # Not used when fix_roi_wm=False
# wm_thr = None  # Default threshold value

# other parameters
registration_threads = 8  # Number of threads for ANTs registration (default: 8, from config). Note: ANTs shows N+1 threads (N workers + 1 main)
save_debug_intermediates = False
if use_mixed_model:
    output_dir = output_dir + "_mixed"
else:
    output_dir = output_dir + "_separate"

# %%
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# %%
def main():
    logger.info("=" * 80)
    logger.info("Test: testing skullstripping function")
    logger.info("=" * 80)
    logger.info(f"Test: input_image={input_image}")
    logger.info(f"Test: modal={modal}")
    logger.info(f"Test: output_dir={output_dir}")
    logger.info(f"Test: use_mixed_model={use_mixed_model}")
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
            enable_crop_2round=enable_crop_2round,
            plane_weight_coronal=weight_coronal,
            plane_weight_axial=weight_axial,
            plane_weight_sagittal=weight_sagittal,
            use_mixed_model=use_mixed_model,
            fix_roi_wm=fix_roi_wm,
            roi_name=roi_name,
            wm_thr=wm_thr,
            save_debug_intermediates=save_debug_intermediates,
            registration_threads=registration_threads,
        )
        
        logger.info("=" * 80)
        logger.info("Test: skullstripping completed successfully")
        logger.info(f"Test: result={result}")
        logger.info("=" * 80)
        
        # Verify output file exists
        # Skip non-file-path keys like 'atlas_name' and 'input_image'
        skip_keys = {'atlas_name', 'input_image'}
        for key, value in result.items():
            if key in skip_keys:
                logger.info(f"Test: {key}={value} (metadata, skipping file check)")
                continue
            if value is not None:
                output_file = Path(value)
                if output_file.exists():
                    logger.info(f"Test: output file created={key}: {value}")
                else:
                    logger.error(f"Test: output file not found: {key}: {value}")
            
    except Exception as e:
        logger.error(f"Test: failed with error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()

