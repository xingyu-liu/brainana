#!/usr/bin/env python3
"""
BIDS discovery script for Nextflow pipeline.

This script runs BEFORE Nextflow starts to:
1. Validate BIDS dataset (optional)
2. Discover all anatomical and functional jobs
3. Print a summary of discovered jobs
4. Save JSON files for Nextflow to read

This ensures discovery completes before processing starts, allowing
Nextflow to show proper job counts in progress.
"""

import argparse
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from macacaMRIprep.steps.bids_discovery import discover_bids_dataset


def validate_bids(bids_dir: Path, skip_validation: bool) -> bool:
    """
    Validate BIDS dataset using bids-validator.
    
    Args:
        bids_dir: Path to BIDS dataset
        skip_validation: If True, skip validation
        
    Returns:
        True if validation passed or was skipped, False otherwise
    """
    if skip_validation:
        print("INFO: BIDS validation skipped")
        return True
    
    print("INFO: Running BIDS validation...")
    try:
        result = subprocess.run(
            ['bids-validator', str(bids_dir)],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print("INFO: BIDS validation passed")
            return True
        else:
            print("ERROR: BIDS validation failed", file=sys.stderr)
            print(result.stderr[:1000], file=sys.stderr)
            return False
    except (FileNotFoundError, OSError) as e:
        # Handle both "command not found" and permission errors
        if isinstance(e, OSError) and e.errno == 13:
            print("WARNING: bids-validator permission denied, skipping validation", file=sys.stderr)
        else:
            print("WARNING: bids-validator not found or not executable, skipping validation", file=sys.stderr)
        return True
    except subprocess.TimeoutExpired:
        print("ERROR: BIDS validation timed out", file=sys.stderr)
        return False
    except Exception as e:
        print(f"WARNING: BIDS validation encountered an error ({e}), skipping validation", file=sys.stderr)
        return True  # Don't fail the pipeline if validation has issues


def print_summary(
    anat_jobs: List[Dict[str, Any]],
    func_jobs: List[Dict[str, Any]],
    output_dir: Path
) -> None:
    """
    Print a summary of discovered jobs.
    
    Args:
        anat_jobs: List of anatomical job dictionaries
        func_jobs: List of functional job dictionaries
        output_dir: Output directory path
    """
    print("\n" + "=" * 60)
    print("BIDS Discovery Summary")
    print("=" * 60)
    
    # Count subjects
    anat_subjects = sorted(set(j.get('subject_id') for j in anat_jobs))
    func_subjects = sorted(set(j.get('subject_id') for j in func_jobs))
    all_subjects = sorted(set(anat_subjects + func_subjects))
    
    print(f"\nSubjects: {len(all_subjects)}")
    if len(all_subjects) <= 10:
        print(f"  {', '.join(all_subjects)}")
    else:
        print(f"  {', '.join(all_subjects[:10])} ... ({len(all_subjects) - 10} more)")
    
    # Anatomical summary
    print(f"\nAnatomical data:")
    print(f"  Total jobs: {len(anat_jobs)}")
    
    t1w_jobs = [j for j in anat_jobs if j.get('suffix') == 'T1w']
    t2w_jobs = [j for j in anat_jobs if j.get('suffix') == 'T2w']
    synthesis_jobs = [j for j in anat_jobs if j.get('needs_synthesis', False)]
    
    print(f"  T1w files: {len(t1w_jobs)}")
    if synthesis_jobs:
        print(f"    - Multi-run synthesis needed: {len(synthesis_jobs)}")
        print(f"    - Single T1w files: {len(t1w_jobs) - len(synthesis_jobs)}")
    print(f"  T2w files: {len(t2w_jobs)}")
    
    # Functional summary
    print(f"\nFunctional data:")
    print(f"  Total jobs: {len(func_jobs)}")
    
    if func_jobs:
        func_tasks = sorted(set(j.get('task') for j in func_jobs if j.get('task')))
        func_runs = sorted(set(j.get('run') for j in func_jobs if j.get('run')))
        print(f"  BOLD files: {len(func_jobs)}")
        if func_tasks:
            print(f"  Tasks: {', '.join(func_tasks)}")
        if func_runs:
            print(f"  Runs: {', '.join(str(r) for r in func_runs)}")
    else:
        print(f"  BOLD files: 0")

    print("\n")

def main():
    parser = argparse.ArgumentParser(
        description="Discover BIDS dataset for Nextflow pipeline"
    )
    parser.add_argument(
        '--bids_dir',
        type=Path,
        required=True,
        help='Path to BIDS dataset directory'
    )
    parser.add_argument(
        '--output_dir',
        type=Path,
        required=True,
        help='Path to output directory'
    )
    parser.add_argument(
        '--config_file',
        type=Path,
        required=True,
        help='Path to configuration YAML file'
    )
    parser.add_argument(
        '--skip_bids_validation',
        action='store_true',
        help='Skip BIDS validation'
    )
    parser.add_argument(
        '--subjects',
        type=str,
        default=None,
        help='Comma-separated list of subject IDs to filter'
    )
    parser.add_argument(
        '--sessions',
        type=str,
        default=None,
        help='Comma-separated list of session IDs to filter'
    )
    parser.add_argument(
        '--tasks',
        type=str,
        default=None,
        help='Comma-separated list of task names to filter'
    )
    parser.add_argument(
        '--runs',
        type=str,
        default=None,
        help='Comma-separated list of run numbers to filter'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.bids_dir.exists():
        print(f"ERROR: BIDS directory not found: {args.bids_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not args.config_file.exists():
        print(f"ERROR: Config file not found: {args.config_file}", file=sys.stderr)
        sys.exit(1)
    
    # Load config
    try:
        import yaml
        with open(args.config_file) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load config file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Parse filtering parameters
    subjects_list = None
    if args.subjects:
        subjects_list = [s.strip() for s in args.subjects.split(',')]
    
    sessions_list = None
    if args.sessions:
        sessions_list = [s.strip() for s in args.sessions.split(',')]
    
    tasks_list = None
    if args.tasks:
        tasks_list = [t.strip() for t in args.tasks.split(',')]
    
    runs_list = None
    if args.runs:
        runs_list = [r.strip() for r in args.runs.split(',')]
    
    # Validate BIDS dataset
    if not validate_bids(args.bids_dir, args.skip_bids_validation):
        print("ERROR: BIDS validation failed. Use --skip_bids_validation to skip.", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'nextflow_reports').mkdir(exist_ok=True)
    
    # Discover jobs
    try:
        anat_jobs, func_jobs = discover_bids_dataset(
            bids_dir=args.bids_dir,
            config=config,
            subjects=subjects_list,
            sessions=sessions_list,
            tasks=tasks_list,
            runs=runs_list
        )
    except Exception as e:
        print(f"ERROR: BIDS discovery failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Print summary
    print_summary(anat_jobs, func_jobs, args.output_dir)
    
    # Save JSON files
    anat_json_path = args.output_dir / 'nextflow_reports' / 'anatomical_jobs.json'
    func_json_path = args.output_dir / 'nextflow_reports' / 'functional_jobs.json'
    
    with open(anat_json_path, 'w') as f:
        json.dump(anat_jobs, f, indent=2)
    
    with open(func_json_path, 'w') as f:
        json.dump(func_jobs, f, indent=2)
    
    print(f"INFO: Discovery complete. Saved job lists to:")
    print(f"  - {anat_json_path}")
    print(f"  - {func_json_path}")
    
    # Exit with error if no jobs found
    if not anat_jobs and not func_jobs:
        print("WARNING: No jobs discovered. Pipeline will have nothing to process.", file=sys.stderr)
        sys.exit(0)  # Don't fail, let Nextflow handle empty channels


if __name__ == '__main__':
    main()

