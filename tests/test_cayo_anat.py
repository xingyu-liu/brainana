# %%
"""
[OUTDATED] Test script for BIDS dataset processing using nhp_mri_prep.

NOTE: This test file references the old workflow classes (AnatomicalProcessor) which no longer exist.
The project now uses Nextflow for orchestration. See README_NEXTFLOW.md for current usage.

This script demonstrates how to process entire BIDS datasets using
the BIDSDatasetProcessor class.

IMPORTANT NOTE ABOUT PARALLEL PROCESSING:
========================================
Parallel processing works at the JOB level, where each job represents 
a subject-session combination. Key points:

1. Each job = one subject-session combination (e.g., sub-001_ses-001)
2. Parallel processing distributes jobs across multiple processes
3. If you only have 1 job (1 subject, 1 session), n_procs > 1 won't help
4. To see parallel benefits, you need multiple jobs (multiple subjects/sessions)

Examples:
- 1 subject, 1 session → 1 job → no parallel benefit
- 3 subjects, 1 session → 3 jobs → can use up to 3 processes  
- 1 subject, 3 sessions → 3 jobs → can use up to 3 processes
- 3 subjects, 2 sessions → 6 jobs → can use up to 6 processes

Best practice: n_procs ≤ number of jobs
"""

import os
import sys
from pathlib import Path
import logging

from nhp_mri_prep.workflow.anat2template import AnatomicalProcessor
from nhp_mri_prep.config import get_config
from nhp_mri_prep.utils import setup_logging, get_logger
from nhp_mri_prep.environment import check_environment
from nhp_mri_prep.quality_control.reports import generate_qc_report
import multiprocessing

# %%
def test_bids_dataset_processing_anatomical_only():
    """Test processing only anatomical data from the BIDS dataset with parallel processing."""
    # Get the test data directory
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    dataset_root = os.path.join(test_dir, "cayo")
    output_dir = dataset_root + "_derivatives"

    anat_file = os.path.join(dataset_root, "0B9.nii.gz")

    print(f"\n=== TESTING ANATOMICAL-ONLY PROCESSING WITH PARALLEL PROCESSING ===")
    print(f"Anat file: {anat_file}")
    print(f"Output dir: {output_dir}")

    # Get default configuration
    config = get_config()
    
    # Update configuration for testing
    config.update({
        "template": {
            "output_space": "NMT2SymPRIMEDE:res-05:hemi-lh:brainWoCerebellumBrainstem",
        },
        "anat": {
            "bias_correction": {
                "enabled": False,
            },
            "skullstripping": {
                "enabled": False
            }
        },
        "registration": {
            "anat2template_xfm_type": "syn"
        }
    })

    # Check environment variables
    check_environment(skullstripping=config.get("anat", {}).get("skullstripping", {}).get("enabled"))

    # Setup logging
    setup_logging(level=logging.INFO)
    logger = get_logger(__name__)

    try:
        
        anat_workflow = AnatomicalProcessor(
            anat_file=anat_file,
            output_dir=str(str(output_dir) + "/output"),
            working_dir=str(str(output_dir) + "/working_dir"),
            template_spec=config.get("template", {}).get("output_space"),
            config=config,
            logger=logger,
        )
        
        anat_result = anat_workflow.run()
        logger.info(f"Anatomical processing completed for T1w file {anat_file}")

        # generate report 
        generate_qc_report(
            snapshot_dir=str(str(output_dir) + "/working_dir" + "/figures"),
            report_path=str(str(output_dir) + "/report.html"),
            config=config,
            logger=logger,
        )

    except Exception as e:
        logger.error(f"Anatomical processing failed for T1w file {anat_file}: {e}")
        raise e

# %%