#!/usr/bin/env python3
"""
Simple test script for FreeSurfer post-processing function.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

from FastSurferCNN.postprocessing.prepping_for_surfrecon import postprocess_for_freesurfer
from FastSurferCNN.utils.checkpoint import extract_atlas_metadata
from FastSurferCNN.utils.constants import FASTSURFER_ROOT

# %%
# Test paths
common_dir = '/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_surfrecon'
skullstripped_dir = f'{common_dir}/arcaro_baby1_fixV1_separate'
output_dir = f'{skullstripped_dir}/sub-baby1'

t1w_f = f'{skullstripped_dir}/input.nii.gz'
seg_f = f'{skullstripped_dir}/segmentation.nii.gz'
mask_f = f'{skullstripped_dir}/mask.nii.gz'

# Checkpoint to extract atlas name from
ckpt_f = '/home/star/github/banana/FastSurferCNN/pretrained_model/T1w_seg-ARM2_coronal.pkl'

# Extract LUT path from checkpoint
checkpoint_path = Path(ckpt_f)
metadata = extract_atlas_metadata(checkpoint_path)
atlas_name = metadata.get("atlas_name") if metadata else None

if atlas_name is None:
    print(f"Error: Could not extract atlas name from checkpoint: {ckpt_f}")
    sys.exit(1)

# Construct LUT path
fastsurfercnn_dir = FASTSURFER_ROOT / "FastSurferCNN"
atlas_dir = fastsurfercnn_dir / f"atlas/atlas-{atlas_name}"
lut_path = atlas_dir / f"{atlas_name}_ColorLUT.tsv"

if not lut_path.exists():
    print(f"Error: ColorLUT not found at {lut_path}")
    sys.exit(1)

print(f"Using LUT: {lut_path}")
print(f"Atlas: {atlas_name}")

# Run post-processing
result = postprocess_for_freesurfer(
    t1w_image=t1w_f,
    segmentation=seg_f,
    mask=mask_f,
    lut_path=lut_path,
    subject_dir=output_dir,
)

if result == 0:
    print("\n✓ Post-processing completed successfully!")
    sys.exit(0)
else:
    print(f"\n✗ Post-processing failed: {result}")
    sys.exit(1)

