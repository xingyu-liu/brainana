#!/usr/bin/env python3
"""
Test script for FastSurfer surface reconstruction pipeline.

Tests the pipeline with a real subject directory.
"""

import os
import sys
from pathlib import Path

# Add src/ to path for fastsurfer_surfrecon package (scripts/ -> fastsurfer_surfrecon -> src)
_src = Path(__file__).resolve().parent.parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from fastsurfer_surfrecon.config import ReconSurfConfig, AtlasConfig, ProcessingConfig
from fastsurfer_surfrecon.pipeline import ReconSurfPipeline
from fastsurfer_surfrecon.utils.logging import setup_logging

# %%
# Test subject
result_dir = Path("/mnt/DataDrive3/xliu/prep_test/brainana_test/preproc/surf_recon/sub-032309m")

subjects_dir = result_dir.parent
subject_id = result_dir.name

# Setup logging
setup_logging()

# Create configuration - load defaults from default.yaml, then override specific values
# t1_input and segmentation are optional - we just verify files exist in mri/
config = ReconSurfConfig.with_defaults(
    subject_id=subject_id,
    subjects_dir=subjects_dir,
    atlas={"name": "ARM2"},
    processing={
        "parallel_hemis": True,
        "skip_cc": True,  # Non-human
        "skip_talairach": True,  # Non-human
        "hires": "auto",  # Auto-detect from voxel size
    },
    verbose=2,  # DEBUG
)

# Run pipeline
print("=" * 80)
print("Starting Pipeline Test")
print("=" * 80)
print()

try:
    pipeline = ReconSurfPipeline(config)
    pipeline.run()
    print()
    print("=" * 80)
    print("Pipeline Test Completed Successfully!")
    print("=" * 80)
except Exception as e:
    print()
    print("=" * 80)
    print(f"Pipeline Test Failed: {e}")
    print("=" * 80)
    import traceback
    traceback.print_exc()
    sys.exit(1)

