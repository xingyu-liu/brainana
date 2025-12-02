#!/usr/bin/env python3
"""
Test script for skullstripping function.
"""

import sys
import argparse
import logging
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

from FastSurferCNN.inference.skullstripping import skullstrip_fastsurfercnn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# %%
# # anat 
# input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_anat_2pass_seg.nii.gz"
# output_dir = input_image.split('.nii')[0]

surfrecon_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_surfrecon'
# input_image = f'{surfrecon_dir}/NMT2Sym_res-05_T1w.nii.gz'
# output_dir = f'{surfrecon_dir}/NMT2Sym'
input_image = f'{surfrecon_dir}/site-arcaro_sub-baby1_ses-anat_T1w.nii.gz'
output_dir = f'{surfrecon_dir}/arcaro_baby1'
# # # input_image = f'{surfrecon_dir}/tpl-NMT2Sym_res-05_T1w_brain.nii.gz'
# # # output_dir = f'{surfrecon_dir}/NMT2Sym_brain_v2'
# # input_image = f'{surfrecon_dir}/test_anat_2pass_seg.nii.gz'
# # output_dir = f'{surfrecon_dir}/test_anat_2pass_seg_skullstripping'

modal = "anat"
data_format = "nifti"
weight_coronal, weight_axial, weight_sagittal = 0.4, 0.4, 0.2
use_mixed_model = False
enable_crop_2round = True

fix_roi_wm = False
if fix_roi_wm:
    roi_name = "V1"  # Use "V1" for ARM2 atlas (primary_visual_cortex). For other atlases, check ColorLUT for correct ROI name.
    if fix_roi_wm:
        output_dir = output_dir + f"_fix{roi_name}"
    tpl_seg_f = f"/home/star/github/banana/macacaMRIprep/templates/atlas-ARM_level-2_space-NMT2Sym_res-05.nii.gz"
    tpl_T1w_f = f"/home/star/github/banana/macacaMRIprep/templates/tpl-NMT2Sym_res-05_T1w_brain.nii.gz"
    tpl_roi_wm_f = f"/home/star/github/banana/macacaMRIprep/templates/tpl-NMT2Sym_res-05_T1w_WM_{roi_name}.nii.gz"
    wm_thr = 0.5

# # func
# input_image = "/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_prediction_output/test_func.nii.gz"
# output_dir = input_image.split('.nii')[0]

# modal = "func"
# data_format = "nifti"
# weight_coronal, weight_axial, weight_sagittal = 0.4, 0.4, 0.2
# use_mixed_model = False  # Set to True to use mixed-plane model instead of separate plane models
# enable_crop_2round = False
# fix_roi_wm = False

if use_mixed_model:
    output_dir = output_dir + "_mixed"
else:
    output_dir = output_dir + "_separate"

# %%
def main():
    parser = argparse.ArgumentParser(description="Run skullstripping on an input image")
    parser.add_argument(
        "--input_image",
        type=str,
        default=input_image,
        help="Path to input image (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=output_dir,
        help="Path to output directory (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--modal",
        type=str,
        choices=["anat", "func"],
        default=modal,
        help="Modality: 'anat' or 'func' (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--data_format",
        type=str,
        choices=["mgz", "nifti"],
        default=data_format,
        help="Output data format: 'mgz' or 'nifti' (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--plane_weight_coronal",
        type=float,
        default=weight_coronal,
        help="Weight for coronal plane in multi-view prediction (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--plane_weight_axial",
        type=float,
        default=weight_axial,
        help="Weight for axial plane in multi-view prediction (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--plane_weight_sagittal",
        type=float,
        default=weight_sagittal,
        help="Weight for sagittal plane in multi-view prediction (default: hardcoded value in script)"
    )
    parser.add_argument(
        "--use_mixed_model",
        action="store_true",
        default=use_mixed_model,
        help="Use mixed-plane model checkpoint instead of separate plane models. "
             "The mixed checkpoint should be named {modal}_seg-{atlas}_mixed.pkl "
             "(e.g., EPI_seg-brainmask_mixed.pkl)"
    )
    parser.add_argument(
        "--enable_crop_2round",
        action="store_true",
        default=enable_crop_2round,
        help=f"Enable two-pass refinement (default: {enable_crop_2round}, set via hardcoded value in script)"
    )
    parser.add_argument(
        "--fix_roi_wm",
        action="store_true",
        default=fix_roi_wm,
        help=f"Fix ROI white matter (default: {fix_roi_wm}, set via hardcoded value in script)"
    )
    parser.add_argument(
        "--roi_name",
        type=str,
        default=None,
        help="ROI name (optional, only needed if --fix_roi_wm is set)"
    )
    parser.add_argument(
        "--tpl_seg_f",
        type=str,
        default=None,
        help="Path to template segmentation file (optional, only needed if --fix_roi_wm is set)"
    )
    parser.add_argument(
        "--tpl_T1w_f",
        type=str,
        default=None,
        help="Path to template T1w file (optional, only needed if --fix_roi_wm is set)"
    )
    parser.add_argument(
        "--tpl_roi_wm_f",
        type=str,
        default=None,
        help="Path to template WM probability map (optional, only needed if --fix_roi_wm is set)"
    )
    parser.add_argument(
        "--wm_thr",
        type=float,
        default=None,
        help="Threshold for WM probability map (optional, only needed if --fix_roi_wm is set)"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Test: testing skullstripping function")
    logger.info("=" * 80)
    logger.info(f"Test: input_image={args.input_image}")
    logger.info(f"Test: modal={args.modal}")
    logger.info(f"Test: output_dir={args.output_dir}")
    logger.info(f"Test: use_mixed_model={args.use_mixed_model}")
    logger.info("=" * 80)
    
    # Check if input file exists
    if not Path(args.input_image).exists():
        logger.error(f"Test: input image not found: {args.input_image}")
        return
    
    try:

        result = skullstrip_fastsurfercnn(
            input_image=args.input_image,
            modal=args.modal,
            output_dir=args.output_dir,
            device_id='auto',
            logger=logger,
            config=None,
            output_data_format=args.data_format,
            enable_crop_2round=args.enable_crop_2round,
            plane_weight_coronal=args.plane_weight_coronal,
            plane_weight_axial=args.plane_weight_axial,
            plane_weight_sagittal=args.plane_weight_sagittal,
            use_mixed_model=args.use_mixed_model,
            fix_roi_wm=args.fix_roi_wm,
            roi_name=args.roi_name,
            tpl_seg_f=args.tpl_seg_f,
            tpl_T1w_f=args.tpl_T1w_f,
            tpl_roi_wm_f=args.tpl_roi_wm_f,
            wm_thr=args.wm_thr,
        )
        
        logger.info("=" * 80)
        logger.info("Test: skullstripping completed successfully")
        logger.info(f"Test: result={result}")
        logger.info("=" * 80)
        
        # Verify output file exists
        for key, value in result.items():
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

