#!/usr/bin/env python3
"""
Test script for FastSurfer surface reconstruction pipeline.

Tests the pipeline with a real subject directory.
"""

import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastsurfer_recon.config import ReconSurfConfig, AtlasConfig, ProcessingConfig
from fastsurfer_recon.pipeline import ReconSurfPipeline
from fastsurfer_recon.utils.logging import setup_logging

# Test subject
subject_root = Path("/mnt/DataDrive3/xliu/monkey_training_groundtruth/FastSurferCNN_training/test_surfrecon")
subject_dir = subject_root / "NMT2Sym_separate" / "sub-NMT2Sym_v2"
subjects_dir = subject_dir.parent
subject_id = subject_dir.name

skip_topology_fix = False
if skip_topology_fix:
    subject_id = f"{subject_id}_nofix"
else:
    subject_id = f"{subject_id}_fix"

n_threads = 24

# Setup logging
setup_logging()

# Create configuration
# t1_input and segmentation are optional - we just verify files exist in mri/
config = ReconSurfConfig(
    subject_id=subject_id,
    subjects_dir=subjects_dir,
    atlas=AtlasConfig(name="ARM2"),
    processing=ProcessingConfig(
        threads=n_threads,
        parallel_hemis=True,
        skip_cc=True,  # Non-human
        skip_talairach=True,  # Non-human
        skip_topology_fix=skip_topology_fix,
        hires="auto",  # Auto-detect from voxel size
    ),
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

