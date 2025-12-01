#!/usr/bin/env python3
"""Test script for MRI plotting with anatomical labels."""

import sys
from pathlib import Path

# Add the macacaMRIprep package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from macacaMRIprep.quality_control.mri_plotting import create_grid_mri_image
except ImportError:
    # Fallback: direct import if package structure is different
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mri_plotting", 
        Path(__file__).parent / "macacaMRIprep" / "quality_control" / "mri_plotting.py"
    )
    mri_plotting = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mri_plotting)
    create_grid_mri_image = mri_plotting.create_grid_mri_image

# Input and output paths
input_nii = '/mnt/DataDrive3/xliu/prep_test/banana_test/princeton_newdata/preproc_fastSurferCNN_reorient/sub-freddie/ses-anat/anat/sub-freddie_ses-anat_desc-preproc_T1w.nii.gz'
# input_nii = '/mnt/DataDrive3/xliu/prep_test/banana_test/princeton_newdata/bids/sub-freddie/ses-anat/anat/sub-freddie_ses-anat_run-1_T1w.nii.gz'
# input_nii = "/mnt/DataDrive3/xliu/prep_test/banana_test/princeton_newdata/raw/freddie/freddie_112525-1113-251125_NHP_T1_MPRAGE_0.5mm3_20251125111330_2.nii"
output_png = input_nii.replace(".nii.gz", ".png").replace(".nii", ".png")

# Create the plot
print(f"Loading NIfTI file: {input_nii}")
fig = create_grid_mri_image(
    underlay_data=input_nii,
    num_cols=7,
    perspectives=["axial", "sagittal", "coronal"],
    title="T1 MPRAGE - Anatomical Orientation Test"
)

# Save the figure
print(f"Saving plot to: {output_png}")
fig.savefig(output_png, dpi=150, bbox_inches='tight', facecolor='black')
print("Plot saved successfully!")

# Close the figure to free memory
import matplotlib.pyplot as plt
plt.close(fig)

