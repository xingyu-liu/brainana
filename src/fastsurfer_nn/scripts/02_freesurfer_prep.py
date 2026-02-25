#!/usr/bin/env python3
"""
Simple test script for FreeSurfer post-processing function.
"""

import sys
from pathlib import Path

# Add src/ to path for fastsurfer_nn imports (scripts/ -> fastsurfer_nn -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from fastsurfer_nn.postprocessing.prepping_for_surfrecon import postprocess_for_freesurfer
from fastsurfer_nn.utils.checkpoint import extract_atlas_metadata
from fastsurfer_nn.utils.constants import REPO_ROOT

# %%
# Test paths
common_dir = '/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/surf_recon/sub-032290/mri'
skullstripped_dir = f'{common_dir}'
output_dir = f'{skullstripped_dir}/test'

t1w_f = f'{skullstripped_dir}/T1w.nii.gz'
seg_f = f'{skullstripped_dir}/segmentation.nii.gz'
mask_f = f'{skullstripped_dir}/mask.nii.gz'

# Checkpoint to extract atlas name from
ckpt_f = '/home/star/github/brainana/src/fastsurfer_nn/pretrained_model/T1w_seg-ARM2_coronal.pkl'

# Extract LUT path from checkpoint
checkpoint_path = Path(ckpt_f)
metadata = extract_atlas_metadata(checkpoint_path)
atlas_name = metadata.get("atlas_name") if metadata else None

if atlas_name is None:
    print(f"Error: Could not extract atlas name from checkpoint: {ckpt_f}")
    sys.exit(1)

# Construct LUT path
fastsurfercnn_dir = REPO_ROOT / "src" / "fastsurfer_nn"
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

