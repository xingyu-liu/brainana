# %%
"""
Test script for BIDS dataset processing using macacaMRIprep.

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

from macacaMRIprep.workflow.bids_processor import BIDSDatasetProcessor
from macacaMRIprep.config import get_config
from macacaMRIprep.utils import setup_logging, get_logger
from macacaMRIprep.environment import check_environment
import multiprocessing

# %%
def test_bids_dataset_processing_full_newcastle():
    """Test full anatomical + functional processing from the BIDS dataset."""
    # Get the test data directory
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    dataset_dir = os.path.join(test_dir, "newcastle")
    # dataset_dir = os.path.join(test_dir, "uwmadison")
    pipeline_name = "func2anat2template"
    output_dir = dataset_dir + f"_derivatives_{pipeline_name}"

    print(f"\n=== TESTING FULL ANATOMICAL + FUNCTIONAL PROCESSING ===")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Output dir: {output_dir}")

    # Get default configuration
    config = get_config()
    
    # Update configuration for testing
    config.update({
        "general": {
            "verbose": 2,
            "overwrite": False,
            "pipeline_name": pipeline_name
        },
        "template": {
            "output_space": "NMT2Sym:res-1",
        },
        "anat": {
            "bias_correction": {
                "enabled": True,
            },
            "skullstripping": {
                "enabled": True,
                "method": "fastsurfercnn"
            }
        },
        "func": {
            "motion_correction": {
                "dof": 6,
                "cost": "mutualinfo",
                "smooth": 1.0,
                "ref_vol": 'mid',
            },
            "skullstripping": {
                "enabled": True,
                "method": "bet"
            },
        },
        "registration": {
            "func2template_xfm_type": "syn",
            "anat2template_xfm_type": "syn",
            "func2anat_xfm_type": "syn"
        }
    })

    # Check environment variables
    check_environment(config=config)

    # Setup logging
    setup_logging(level=logging.INFO)
    logger = get_logger(__name__)

    try:
        # Process only first subject and session for testing
        # Process only one functional run to save time
        processor = BIDSDatasetProcessor(
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            config=config,
            logger=logger
        )

        # Get dataset summary
        summary = processor.get_dataset_summary()
        print(f"\nDataset contains:")
        print(f"Subjects: {summary['subs']}")
        print(f"Sessions: {summary['sess']}")
        
        # Discover jobs to show parallel potential
        jobs = processor.discover_processing_jobs()
        print(f"\nDiscovered {len(jobs)} processing jobs:")
        for job in jobs:
            print(f"  - {job.job_id}")
        
        # Determine optimal number of processes
        available_cores = multiprocessing.cpu_count()
        optimal_procs = min(len(jobs), available_cores, 4)  # Don't exceed jobs, cores, or 4
        
        print(f"\nParallel processing setup:")
        print(f"  Available CPU cores: {available_cores}")
        print(f"  Processing jobs: {len(jobs)}")
        print(f"  Using processes: {optimal_procs}")
        
        # run the processor
        results = processor.run_dataset(
            run_anat=True,
            run_func=True,
            n_procs=optimal_procs    # Use parallel processing
        )
        
        # print the results
        print(f"\n=== PROCESSING RESULTS ===")
        print(f"Status: {results['status']}")
        if results['status'] == 'completed':
            print(f"Total jobs: {results['total_jobs']}")
            print(f"Completed: {results['completed_jobs']}")
            print(f"Failed: {results['failed_jobs']}")
            print(f"Duration: {results['duration_formatted']}")
            print(f"Processes used: {optimal_procs}")
        else:
            raise RuntimeError(f"Processing failed with status: {results['status']}")

    except Exception as e:
        print(f"❌ BIDS full processing test failed: {e}")
        import traceback
        traceback.print_exc()
        raise e


def test_bids_dataset_processing_full_arcaro():
    """Test full anatomical + functional processing from the BIDS dataset."""
    # Get the test data directory
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_datasets"))
    dataset_dir = os.path.join(test_dir, "arcaro")
    pipeline_name = "func2template"
    output_dir = dataset_dir + f"_derivatives_{pipeline_name}"

    print(f"\n=== TESTING FULL ANATOMICAL + FUNCTIONAL PROCESSING ===")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Output dir: {output_dir}")

    # Get default configuration
    config = get_config()
    
    # Update configuration for testing
    config.update({
        "general": {
            "verbose": 2,
            "overwrite": False,
            "pipeline_name": pipeline_name
        },
        "template": {
            "output_space": "NMT2Sym:res-1:brainWoCerebellumBrainstem",
        },
        "anat": {
            "bias_correction": {
                "enabled": True,
            },
            "skullstripping": {
                "enabled": True,
                "method": "fastsurfercnn"
            }
        },
        "func": {
            "motion_correction": {
                "dof": 6,
                "cost": "mutualinfo",
                "smooth": 1.0,
                "ref_vol": 'mid',
            },
            "skullstripping": {
                "enabled": True,
                "method": "fastsurfercnn"
            },
        },
        "registration": {
            "func2template_xfm_type": "syn",
            "anat2template_xfm_type": "syn",
            "func2anat_xfm_type": "affine"
        }
    })

    # Check environment variables
    check_environment(config=config)

    # Setup logging
    setup_logging(level=logging.INFO)
    logger = get_logger(__name__)

    try:
        # Process only first subject and session for testing
        # Process only one functional run to save time
        processor = BIDSDatasetProcessor(
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            config=config,
            logger=logger
        )

        # Get dataset summary
        summary = processor.get_dataset_summary()
        print(f"\nDataset contains:")
        print(f"Subjects: {summary['subs']}")
        print(f"Sessions: {summary['sess']}")
        
        # Discover jobs to show parallel potential
        jobs = processor.discover_processing_jobs()
        print(f"\nDiscovered {len(jobs)} processing jobs:")
        for job in jobs:
            print(f"  - {job.job_id}")
        
        # Determine optimal number of processes
        available_cores = multiprocessing.cpu_count()
        optimal_procs = min(len(jobs), available_cores, 4)  # Don't exceed jobs, cores, or 4
        
        print(f"\nParallel processing setup:")
        print(f"  Available CPU cores: {available_cores}")
        print(f"  Processing jobs: {len(jobs)}")
        print(f"  Using processes: {optimal_procs}")
        
        # run the processor
        results = processor.run_dataset(
            run_anat=True,
            run_func=True,
            n_procs=optimal_procs    # Use parallel processing
        )
        
        # print the results
        print(f"\n=== PROCESSING RESULTS ===")
        print(f"Status: {results['status']}")
        if results['status'] == 'completed':
            print(f"Total jobs: {results['total_jobs']}")
            print(f"Completed: {results['completed_jobs']}")
            print(f"Failed: {results['failed_jobs']}")
            print(f"Duration: {results['duration_formatted']}")
            print(f"Processes used: {optimal_procs}")
        else:
            raise RuntimeError(f"Processing failed with status: {results['status']}")

    except Exception as e:
        print(f"❌ BIDS full processing test failed: {e}")
        import traceback
        traceback.print_exc()
        raise e
# %%
