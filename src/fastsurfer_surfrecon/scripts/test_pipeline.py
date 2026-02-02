#!/usr/bin/env python3
"""
Test script for FastSurfer surface reconstruction pipeline.

Tests the pipeline with a real subject directory.
"""

import os
import sys
from pathlib import Path

# Set environment variables BEFORE importing any modules that use numpy/scipy/lapy
# This is critical because these libraries check environment variables at import time
# and may initialize their threading settings then. Setting them early ensures they
# respect the thread limits.
n_threads = 8

# Add fastsurfer_surfrecon/ to path for fastsurfer_recon imports (scripts/ -> fastsurfer_surfrecon)
_fs_surfrecon_dir = Path(__file__).resolve().parent.parent
if str(_fs_surfrecon_dir) not in sys.path:
    sys.path.insert(0, str(_fs_surfrecon_dir))

from fastsurfer_recon.config import ReconSurfConfig, AtlasConfig, ProcessingConfig
from fastsurfer_recon.pipeline import ReconSurfPipeline
from fastsurfer_recon.utils.logging import setup_logging

# %%
# Test subject
subject_root = Path("/mnt/DataDrive3/xliu/prep_test/banana_test/preproc/histology_test/surf")
subject_dir = subject_root / "sub-histology"
# subject_dir = subject_root / "arcaro_baby1_fixV1_separate" / "sub-baby1"

subjects_dir = subject_dir.parent
subject_id = subject_dir.name

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
        "threads": n_threads,
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

