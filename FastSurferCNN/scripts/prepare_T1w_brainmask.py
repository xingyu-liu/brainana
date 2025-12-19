'''
generate the T1w brainmask from the T1w file using seg-ARM2 model
'''

# %%
# import
import json
import logging
import shutil
from pathlib import Path
from tempfile import mkdtemp

from FastSurferCNN.inference.segmentation import run_segmentation

# %%
dataset_root = Path('/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/training_data/T1w_seg-brainmask')
image_dir = dataset_root / 'images'
label_dir = dataset_root / 'labels'
sample_list_file = dataset_root / 'sample_list.json'

label_suffix = "brainmask"

overwrite = False

# %% 
modal = "anat"
weight_axial, weight_coronal, weight_sagittal = 0.4, 0.4, 0.2
use_mixed_model = False
enable_crop_2round = False
fix_roi_wm = False
fix_wm_islands = False
create_hemimask = False

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
    # Ensure label directory exists
    label_dir.mkdir(parents=True, exist_ok=True)
    
    # Read sample list
    if not sample_list_file.exists():
        logger.error(f"Sample list file not found: {sample_list_file}")
        return
    
    logger.info(f"Reading sample list from: {sample_list_file}")
    with open(sample_list_file, 'r') as f:
        sample_list = json.load(f)
    
    # Get image list
    if 'images' in sample_list:
        image_paths = sample_list['images']
        image_paths = sorted(image_paths)
    else:
        logger.error("Sample list JSON must contain 'images' key")
        return
    
    logger.info(f"Found {len(image_paths)} images to process")
    
    # Process each image
    successful = 0
    failed = 0
    
    for i, image_path_str in enumerate(image_paths, 1):
        image_path = image_dir / f"{image_path_str}.nii.gz"
        
        # Check if image exists
        if not image_path.exists():
            logger.warning(f"[{i}/{len(image_paths)}] Image not found, skipping: {image_path}")
            failed += 1
            continue
        
        # Generate output filename: image_name + label_suffix + .nii.gz
        # e.g., site-xxx_sub-yyy_T1w.nii.gz -> site-xxx_sub-yyy_T1w_brainmask.nii.gz
        output_path = label_dir / f"{image_path_str}_{label_suffix}.nii.gz"
        
        # Skip if output already exists
        if output_path.exists() and not overwrite:
            logger.info(f"[{i}/{len(image_paths)}] Output already exists, skipping: {output_path.name}")
            successful += 1
            continue
        
        logger.info(f"[{i}/{len(image_paths)}] Processing: {image_path.name}")
        
        # Create temporary output directory for run_segmentation
        temp_output_dir = Path(mkdtemp(prefix='segment_'))
        
        try:
            # Run segmentation
            result = run_segmentation(
                input_image=str(image_path),
                modal=modal,
                output_dir=str(temp_output_dir),
                device_id='auto',
                logger=logger,
                output_data_format='nifti',
                enable_crop_2round=enable_crop_2round,
                plane_weight_coronal=weight_coronal,
                plane_weight_axial=weight_axial,
                plane_weight_sagittal=weight_sagittal,
                use_mixed_model=use_mixed_model,
                fix_roi_wm=fix_roi_wm,
                fix_wm_islands=fix_wm_islands,
                create_hemimask=create_hemimask,
            )
            
            # Get brain mask path from result
            brain_mask_path = result.get('brain_mask')
            if not brain_mask_path or not Path(brain_mask_path).exists():
                logger.error(f"[{i}/{len(image_paths)}] Brain mask not generated for: {image_path.name}")
                failed += 1
                continue
            
            # Copy brain mask to final location
            shutil.copy2(brain_mask_path, output_path)
            logger.info(f"[{i}/{len(image_paths)}] Successfully saved: {output_path.name}")
            successful += 1
            
        except Exception as e:
            logger.error(f"[{i}/{len(image_paths)}] Failed to process {image_path.name}: {e}", exc_info=True)
            failed += 1
        finally:
            # Clean up temporary directory
            if temp_output_dir.exists():
                shutil.rmtree(temp_output_dir)
    
    # Summary
    logger.info("=" * 80)
    logger.info(f"Processing complete: {successful} successful, {failed} failed out of {len(image_paths)} total")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()