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
from pathlib import Path
from typing import Dict, Any, List

# Add src/ to path for nhp_mri_prep imports (nextflow_scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.config.config_io import get_nested_config_value, load_yaml_config
from nhp_mri_prep.config.config_validation import validate_config
from nhp_mri_prep.steps.bids_discovery import discover_bids_dataset


def validate_bids(bids_dir: Path) -> bool:
    """
    Lightweight, dependency-free sanity check that ``bids_dir`` looks like a
    BIDS dataset the pipeline can process.

    This does not run the full bids-validator (the pipeline intentionally builds
    its BIDSLayout with ``validate=False`` to tolerate benign, especially
    macaque-specific, spec deviations). It only confirms the directory contains
    at least one ``sub-*/`` subject directory, which is what discovery needs.
    The main purpose is to turn the common "pointed at the wrong directory"
    mistake into a clear, early error instead of a later, vaguer
    "No jobs discovered".

    Args:
        bids_dir: Path to BIDS dataset

    Returns:
        True if the check passed, False otherwise
    """
    has_subject_dir = any(
        p.is_dir() and p.name.startswith("sub-") for p in bids_dir.iterdir()
    )
    if not has_subject_dir:
        print(
            f"ERROR: {bids_dir} does not look like a BIDS dataset: "
            f"no 'sub-*/' subject directories found.",
            file=sys.stderr,
        )
        return False

    print("INFO: BIDS structure check passed")
    return True


def _count_job_bids_inputs(job: Dict[str, Any]) -> int:
    """Count original BIDS NIfTI inputs represented by one discovery job."""
    fps = job.get("file_paths")
    if isinstance(fps, list) and fps:
        return len(fps)
    if job.get("file_path"):
        return 1
    return 0


def _sum_job_bids_inputs(jobs: List[Dict[str, Any]]) -> int:
    """Sum BIDS NIfTI inputs across a list of discovery jobs."""
    return sum(_count_job_bids_inputs(j) for j in jobs)


def _pluralize(n: int, singular: str, plural: str | None = None) -> str:
    """Return ``f'{n} {singular|plural}'`` with basic English pluralization."""
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural if plural is not None else singular + 's'}"


def _print_modality_summary(
    label: str,
    modality_jobs: List[Dict[str, Any]],
    synthesis_type: str,
) -> None:
    """Print one anatomical modality line plus optional synthesis breakdown."""
    n_jobs = len(modality_jobs)
    n_inputs = _sum_job_bids_inputs(modality_jobs)
    print(
        f"  {label}: {_pluralize(n_inputs, 'BIDS file')} → "
        f"{_pluralize(n_jobs, 'job')}"
    )

    synthesis_jobs = [
        j
        for j in modality_jobs
        if j.get("needs_synthesis", False) and j.get("synthesis_type") == synthesis_type
    ]
    if not synthesis_jobs:
        return

    cross_session = [
        j for j in synthesis_jobs if j.get("synthesis_scope") == "cross_session"
    ]
    within_session = [
        j for j in synthesis_jobs if j.get("synthesis_scope") == "within_session"
    ]
    if cross_session:
        print(
            f"    - Cross-session synthesis: "
            f"{_pluralize(len(cross_session), 'job')} "
            f"({_sum_job_bids_inputs(cross_session)} inputs)"
        )
    if within_session:
        print(
            f"    - Within-session synthesis: "
            f"{_pluralize(len(within_session), 'job')} "
            f"({_sum_job_bids_inputs(within_session)} inputs)"
        )
    # Complement of `synthesis_jobs` within this modality, rather than a count of
    # jobs without `needs_synthesis`: a job flagged for synthesis under a
    # *different* synthesis_type belongs to neither line above nor here, and
    # counting it as single would stop the sub-counts adding up to the job total.
    n_single = n_jobs - len(synthesis_jobs)
    if n_single > 0:
        print(f"    - Single (no synthesis): {_pluralize(n_single, 'job')}")


def print_summary(
    anat_jobs: List[Dict[str, Any]],
    func_jobs: List[Dict[str, Any]],
    anat_only: bool = False,
) -> None:
    """
    Print a summary of discovered jobs.

    Distinguishes original BIDS NIfTI inputs from post-synthesis processing
    jobs so multi-run anatomical synthesis is not misreported as a single file.

    Args:
        anat_jobs: List of anatomical job dictionaries
        func_jobs: List of functional job dictionaries
        anat_only: True when ``general.anat_only`` is set. Functional discovery
            is skipped entirely in that case, so zero counts would wrongly read
            as "this dataset has no BOLD data"; an explicit notice is printed
            instead.
    """
    print("\n" + "=" * 60)
    print("BIDS Discovery Summary")
    print("=" * 60)

    # Count subjects
    anat_subjects = sorted(set(j.get("subject_id") for j in anat_jobs))
    func_subjects = sorted(set(j.get("subject_id") for j in func_jobs))
    all_subjects = sorted(set(anat_subjects + func_subjects))

    print(f"\nSubjects: {len(all_subjects)}")
    if len(all_subjects) <= 10:
        print(f"  {', '.join(all_subjects)}")
    else:
        print(f"  {', '.join(all_subjects[:10])} ... ({len(all_subjects) - 10} more)")

    # Anatomical summary: BIDS inputs vs processing jobs after synthesis grouping
    anat_inputs = _sum_job_bids_inputs(anat_jobs)
    print("\nAnatomical data:")
    print(f"  BIDS inputs → processing jobs: {anat_inputs} → {len(anat_jobs)}")

    t1w_jobs = [j for j in anat_jobs if j.get("suffix") == "T1w"]
    t2w_jobs = [j for j in anat_jobs if j.get("suffix") == "T2w"]
    _print_modality_summary("T1w", t1w_jobs, synthesis_type="t1w")
    _print_modality_summary("T2w", t2w_jobs, synthesis_type="t2w")

    # Functional summary (BOLD is currently 1:1 with jobs)
    print("\nFunctional data:")
    if anat_only:
        print(
            "  Skipped: anat_only = true — functional data is not "
            "discovered or processed in this run."
        )
        print("\n")
        return

    bold_inputs = _sum_job_bids_inputs(func_jobs)
    print(f"  Processing jobs: {len(func_jobs)}")
    print(f"  BOLD: {_pluralize(bold_inputs, 'BIDS file')}")
    if func_jobs:
        func_tasks = sorted(set(j.get("task") for j in func_jobs if j.get("task")))
        if func_tasks:
            print(f"  Tasks: {', '.join(func_tasks)}")

    print("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Discover BIDS dataset for Nextflow pipeline"
    )
    parser.add_argument(
        "--bids_dir", type=Path, required=True, help="Path to BIDS dataset directory"
    )
    parser.add_argument(
        "--output_dir", type=Path, required=True, help="Path to output directory"
    )
    parser.add_argument(
        "--config_file",
        type=Path,
        required=True,
        help="Path to configuration YAML file",
    )
    parser.add_argument(
        "--subjects",
        type=str,
        default=None,
        help="Comma-separated list of subject IDs to filter",
    )
    parser.add_argument(
        "--sessions",
        type=str,
        default=None,
        help="Comma-separated list of session IDs to filter",
    )
    parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        help="Comma-separated list of task names to filter",
    )
    parser.add_argument(
        "--runs",
        type=str,
        default=None,
        help="Comma-separated list of run numbers to filter",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.bids_dir.exists():
        print(f"ERROR: BIDS directory not found: {args.bids_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.config_file.exists():
        print(f"ERROR: Config file not found: {args.config_file}", file=sys.stderr)
        sys.exit(1)

    # Load config (accepts tabs in indentation via normalization)
    try:
        config = load_yaml_config(args.config_file)
    except Exception as e:
        print(f"ERROR: Failed to load config file: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate the config up front so bad values (e.g. dof: 7, an unknown
    # skullstripping method, an out-of-range weight) fail fast here with a
    # clear message, rather than surfacing as an opaque error deep in a
    # process after minutes of compute. validate_config() merges the user
    # config over the defaults, so it checks the effective settings.
    try:
        validate_config(config)
    except (ValueError, TypeError) as e:
        print(f"ERROR: Invalid configuration in {args.config_file}:", file=sys.stderr)
        print(f"  {e}", file=sys.stderr)
        sys.exit(1)

    # Parse filtering parameters
    subjects_list = None
    if args.subjects:
        subjects_list = [s.strip() for s in args.subjects.split(",")]

    sessions_list = None
    if args.sessions:
        sessions_list = [s.strip() for s in args.sessions.split(",")]

    tasks_list = None
    if args.tasks:
        tasks_list = [t.strip() for t in args.tasks.split(",")]

    runs_list = None
    if args.runs:
        runs_list = [r.strip() for r in args.runs.split(",")]

    # Validate BIDS dataset structure (always runs)
    if not validate_bids(args.bids_dir):
        sys.exit(1)

    # Create output directory
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        # Verify directory was created and is accessible
        if not args.output_dir.exists():
            print(
                f"ERROR: Failed to create output directory: {args.output_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.output_dir.is_dir():
            print(
                f"ERROR: Output path exists but is not a directory: {args.output_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        # Resolve to absolute path for clarity
        args.output_dir = args.output_dir.resolve()
    except (OSError, PermissionError) as e:
        print(
            f"ERROR: Failed to create output directory {args.output_dir}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create nextflow_reports subdirectory
    try:
        (args.output_dir / "nextflow_reports").mkdir(exist_ok=True)
        if not (args.output_dir / "nextflow_reports").exists():
            print("ERROR: Failed to create nextflow_reports directory", file=sys.stderr)
            sys.exit(1)
    except (OSError, PermissionError) as e:
        print(
            f"ERROR: Failed to create nextflow_reports directory: {e}", file=sys.stderr
        )
        sys.exit(1)

    # Discover jobs
    try:
        anat_jobs, func_jobs = discover_bids_dataset(
            bids_dir=args.bids_dir,
            config=config,
            subjects=subjects_list,
            sessions=sessions_list,
            tasks=tasks_list,
            runs=runs_list,
        )
    except Exception as e:
        print(f"ERROR: BIDS discovery failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Print summary. anat_only comes from the same config key discovery itself
    # uses to skip functional discovery, so the summary matches what ran.
    anat_only = bool(get_nested_config_value(config, "general.anat_only", False))
    print_summary(anat_jobs, func_jobs, anat_only=anat_only)

    # Save JSON files
    anat_json_path = args.output_dir / "nextflow_reports" / "anatomical_jobs.json"
    func_json_path = args.output_dir / "nextflow_reports" / "functional_jobs.json"

    with open(anat_json_path, "w") as f:
        json.dump(anat_jobs, f, indent=2)

    with open(func_json_path, "w") as f:
        json.dump(func_jobs, f, indent=2)

    # Verify files were written successfully
    if not anat_json_path.exists() or not func_json_path.exists():
        print("ERROR: Failed to write job list files", file=sys.stderr)
        sys.exit(1)

    print("INFO: Discovery complete. Saved job lists to:")
    print(f"  - {anat_json_path}")
    print(f"  - {func_json_path}")
    print(f"INFO: Output directory: {args.output_dir}")

    # Exit with error if no jobs found
    if not anat_jobs and not func_jobs:
        print("ERROR: No jobs discovered. Check that:", file=sys.stderr)
        print("  (1) The path is the BIDS dataset root.", file=sys.stderr)
        print(
            "  (2) It contains at least one subject with anat and/or func data in BIDS layout.",
            file=sys.stderr,
        )
        print(
            "  (3) Validate with https://bids-standard.github.io/bids-validator/ if unsure.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
