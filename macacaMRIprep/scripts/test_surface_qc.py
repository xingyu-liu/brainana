#!/usr/bin/env python3
"""
Test script for surface QC functions.

Tests both create_surf_recon_tissue_seg_qc and create_cortical_surf_and_measures_qc
on a real FreeSurfer subject directory.
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path to import macacaMRIprep modules
script_dir = Path(__file__).parent.resolve()
parent_dir = script_dir.parent.resolve()  # This is macacaMRIprep/
package_parent = parent_dir.parent.resolve()  # This is banana/
if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))

from macacaMRIprep.quality_control.snapshots import (
    create_surf_recon_tissue_seg_qc,
    create_cortical_surf_and_measures_qc
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test directory
fs_subject_dir = Path("/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/surf_recon/sub-NMT2Sym")
output_dir = fs_subject_dir / "tmp"
output_dir.mkdir(parents=True, exist_ok=True)

def main():
    """Test both surface QC functions."""
    
    print("=" * 80)
    print("Testing Surface QC Functions")
    print("=" * 80)
    print(f"FreeSurfer subject directory: {fs_subject_dir}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Test 1: Surface reconstruction tissue segmentation QC
    print("-" * 80)
    print("Test 1: Surface Reconstruction Tissue Segmentation QC")
    print("-" * 80)
    try:
        surf_seg_output = output_dir / "test_surf_recon_tissue_seg.png"
        result = create_surf_recon_tissue_seg_qc(
            fs_subject_dir=str(fs_subject_dir),
            save_f=str(surf_seg_output),
            modality="anat",
            logger=logger
        )
        
        if result:
            print(f"✓ Success! Output saved to: {surf_seg_output}")
            print(f"  Result keys: {list(result.keys())}")
        else:
            print("✗ Failed: Function returned empty dictionary")
    except Exception as e:
        print(f"✗ Failed with exception: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # Test 2: Cortical surface and measures QC
    print("-" * 80)
    print("Test 2: Cortical Surface and Measures QC")
    print("-" * 80)
    try:
        cortical_surf_output = output_dir / "test_cortical_surf_and_measures.png"
        result = create_cortical_surf_and_measures_qc(
            fs_subject_dir=str(fs_subject_dir),
            save_f=str(cortical_surf_output),
            atlas_name="ARM2atlas",
            modality="anat",
            logger=logger
        )
        
        if result:
            print(f"✓ Success! Output saved to: {cortical_surf_output}")
            print(f"  Result keys: {list(result.keys())}")
        else:
            print("✗ Failed: Function returned empty dictionary")
    except Exception as e:
        print(f"✗ Failed with exception: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 80)
    print("Testing complete!")
    print("=" * 80)

if __name__ == "__main__":
    main()

