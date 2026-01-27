"""
Quality Control Module for macacaMRIprep

This module provides comprehensive quality control tools for MRI preprocessing:

1. **Visual Quality Control Snapshots**
   - Motion parameter visualization
   - Brain extraction assessment overlays  
   - Registration quality check overlays
   - Bias correction assessment overlays

2. **Comprehensive HTML Reports**
   - Professional, interactive quality control reports
   - Quantitative quality metrics with color-coded assessments
   - Embedded high-quality visualization snapshots

3. **Automated Quality Assessment**
   - Motion analysis with framewise displacement calculations
   - Brain coverage and extraction quality metrics
   - Registration transform validation

All outputs are optimized for clinical and research quality assessment workflows.

## Usage

Use the specific QC functions for clear, purposeful quality control:

```python
from macacaMRIprep.quality_control import (
    create_motion_correction_qc,
    create_skullstripping_qc,
    create_registration_qc,
    create_bias_correction_qc
)

# Generate motion correction QC
motion_qc = create_motion_correction_qc(
    motion_params="motion.par",
    save_f="figures/sub-01_desc-motion_bold.png",
    input_file="func.nii.gz"
)

# Generate skull stripping QC (specify modality)
anat_skull_qc = create_skullstripping_qc(
    underlay_file="anat_orig.nii.gz",
    mask_file="anat_brain_mask.nii.gz",
    save_f="figures/sub-01_desc-skullstrip_T1w.png",
    modality="anat"
)

func_skull_qc = create_skullstripping_qc(
    underlay_file="func_orig.nii.gz",
    mask_file="func_brain_mask.nii.gz",
    save_f="figures/sub-01_desc-skullstrip_bold.png",
    modality="func"
)

# Generate registration QC (specify modality explicitly)
func_reg_qc = create_registration_qc(
    image_file="func_registered.nii.gz",
    template_file="template.nii.gz",
    save_f="figures/sub-01_desc-func2template_bold.png",
    modality="func2template"
)

anat_reg_qc = create_registration_qc(
    image_file="anat_registered.nii.gz",
    template_file="template.nii.gz",
    save_f="figures/sub-01_desc-anat2template_T1w.png",
    modality="anat2template"
)

# Generate bias correction QC (specify modality)
func_bias_qc = create_bias_correction_qc(
    image_original="func_orig.nii.gz",
    image_corrected="func_bias_corrected.nii.gz",
    save_f="figures/sub-01_desc-biascorrect_bold.png",
    modality="func"
)

anat_bias_qc = create_bias_correction_qc(
    image_original="anat_orig.nii.gz",
    image_corrected="anat_bias_corrected.nii.gz",
    save_f="figures/sub-01_desc-biascorrect_T1w.png",
    modality="anat"
)

# Generate comprehensive QC report  
from macacaMRIprep.quality_control import generate_qc_report

# Option 1: With explicit snapshot paths
report_outputs = generate_qc_report(
    snapshot_dir="path/to/figures",
    report_path="output_dir/sub-01_report.html",
    config=config,
    logger=logger,
    snapshot_paths=all_qc_outputs,  # Explicit snapshots
    pipeline_state=pipeline_state
)

# Option 2: Auto-discover snapshots from directory
report_outputs = generate_qc_report(
    snapshot_dir="path/to/figures",
    report_path="output_dir/sub-01_report.html",
    config=config,
    logger=logger,
    snapshot_paths=None,  # Auto-discover
    pipeline_state=pipeline_state
)
```
"""

from .snapshots import (
    create_motion_correction_qc,
    create_skullstripping_qc,
    create_registration_qc,
    create_bias_correction_qc,
    create_t1wt2w_combined_qc,
    create_conform_qc,
    create_atlas_segmentation_qc,
    create_surf_recon_tissue_seg_qc,
    create_cortical_surf_and_measures_qc
)

from .reports import generate_qc_report

from ..quality_control.mri_plotting import (
    create_overlay_grid_3xN, 
    create_motion_plot
)

__all__ = [
    # Visualization functions
    'create_overlay_grid_3xN',
    'create_motion_plot',
    
    # QC functions
    'create_motion_correction_qc',
    'create_skullstripping_qc',
    'create_registration_qc',
    'create_bias_correction_qc',
    'create_conform_qc',
    'create_atlas_segmentation_qc',
    'create_surf_recon_tissue_seg_qc',
    'create_cortical_surf_and_measures_qc',
    
    # Report functions
    'generate_qc_report',
] 