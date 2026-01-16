"""
BIDS dataset discovery for Nextflow integration.

This module provides functions to discover BIDS datasets and return
job lists that can be used to create Nextflow channels.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from bids import BIDSLayout

from ..utils.bids import parse_bids_entities


logger = logging.getLogger(__name__)


def _normalize_to_list(value):
    """
    Normalize a value to a list of strings.
    
    Handles None, single values (int, str), and lists.
    Converts all values to strings to preserve formatting.
    
    Args:
        value: Value to normalize (can be None, int, str, or list)
        
    Returns:
        List of strings, or None if input was None
    """
    if value is None:
        return None
    if isinstance(value, list):
        # Convert all items in list to strings
        return [str(item) for item in value]
    # Handle single value - convert to string
    return [str(value)]


def _normalize_bids_id(value, prefix):
    """
    Normalize a BIDS ID by removing prefix if present.
    
    Handles both 'prefix-032102' and '032102' formats.
    Preserves None values. Value should already be a string.
    
    Args:
        value: ID value (should be str, but handles int/None for safety)
        prefix: Prefix to remove (e.g., 'sub-', 'ses-', 'task-', 'run-')
        
    Returns:
        Normalized ID as string (without prefix), or None if input was None
    """
    if value is None:
        return None
    # Convert to string (should already be string from _normalize_to_list)
    value_str = str(value)
    if value_str.startswith(prefix):
        return value_str[len(prefix):]
    return value_str


def discover_bids_dataset(
    bids_dir: Path,
    config: Dict[str, Any],
    subjects: Optional[List[str]] = None,
    sessions: Optional[List[str]] = None,
    tasks: Optional[List[str]] = None,
    runs: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Discover BIDS dataset and return job lists for Nextflow.
    
    This function discovers all anatomical and functional files in a BIDS dataset
    and returns them as lists of job dictionaries that can be used to create
    Nextflow channels.
    
    Args:
        bids_dir: Path to BIDS dataset root directory
        config: Configuration dictionary (used for filtering)
        subjects: Optional list of subject IDs to include (None = all)
        sessions: Optional list of session IDs to include (None = all)
        tasks: Optional list of task names to include (None = all)
        runs: Optional list of run numbers to include (None = all)
        
    Returns:
        Tuple of (anatomical_jobs, functional_jobs)
        Each job is a dictionary with keys:
        - subject_id: Subject ID (without 'sub-' prefix)
        - session_id: Session ID (without 'ses-' prefix, or None)
        - file_path: Path to input file
        - modality: 'anat' or 'func'
        - suffix: BIDS suffix (e.g., 'T1w', 'bold')
        - task: Task name (for func, None for anat)
        - run: Run number (for func, None for anat)
        - entities: Full BIDS entities dictionary
        - needs_synthesis: Whether multiple T1w runs need synthesis (anat only)
    """
    bids_dir = Path(bids_dir)
    
    if not bids_dir.exists():
        raise FileNotFoundError(f"BIDS directory not found: {bids_dir}")
    
    # Initialize BIDS layout
    try:
        layout = BIDSLayout(
            str(bids_dir),
            validate=False,  # Skip validation for speed
            derivatives=False
        )
    except Exception as e:
        raise RuntimeError(f"Failed to initialize BIDS layout: {e}")
    
    # Apply filtering from config if not overridden
    bids_filtering = config.get("bids_filtering", {})
    if subjects is None:
        subjects = bids_filtering.get("subjects")
    if sessions is None:
        sessions = bids_filtering.get("sessions")
    if tasks is None:
        tasks = bids_filtering.get("tasks")
    if runs is None:
        runs = bids_filtering.get("runs")
    
    # Normalize to lists and remove prefixes
    subjects = _normalize_to_list(subjects)
    sessions = _normalize_to_list(sessions)
    tasks = _normalize_to_list(tasks)
    runs = _normalize_to_list(runs)
    
    # Normalize IDs (remove prefixes if present)
    if subjects is not None:
        subjects = [_normalize_bids_id(s, 'sub-') for s in subjects]
    if sessions is not None:
        sessions = [_normalize_bids_id(s, 'ses-') for s in sessions]
    if tasks is not None:
        tasks = [_normalize_bids_id(t, 'task-') for t in tasks]
    if runs is not None:
        runs = [_normalize_bids_id(r, 'run-') for r in runs]
    
    # Get all subjects
    all_subjects = layout.get_subjects()
    if subjects is None:
        target_subjects = all_subjects
    else:
        target_subjects = [s for s in subjects if s in all_subjects]
        if len(target_subjects) != len(subjects):
            missing = set(subjects) - set(target_subjects)
            logger.warning(
                f"Some requested subjects not found: {missing}. "
                f"If your config has unquoted numbers (e.g., '032102'), YAML may parse them incorrectly. "
                f"Please quote the values in your YAML config (e.g., subjects: \"032102\" or subjects: [\"032102\"])."
            )
    
    anatomical_jobs = []
    functional_jobs = []
    
    # Check if we should skip functional discovery based on config
    general_config = config.get("general", {})
    anat_only = general_config.get("anat_only", False)
    
    # Discover anatomical files (always discover, regardless of anat_only setting)
    for sub in target_subjects:
            # Get sessions for this subject
            sub_sessions = layout.get_sessions(subject=sub)
            if not sub_sessions:
                sub_sessions = [None]  # No sessions in dataset
            
            # Filter sessions if specified
            if sessions is not None:
                sub_sessions = [s for s in sub_sessions if s in sessions]
            
            for ses in sub_sessions:
                # Find anatomical files
                anat_filters = {
                    "subject": sub,
                    "datatype": "anat",
                    "suffix": ["T1w", "T2w"],
                    "extension": [".nii.gz", ".nii"]
                }
                if ses:
                    anat_filters["session"] = ses
                
                anat_files = list(layout.get(**anat_filters))
                
                if not anat_files:
                    continue
                
                # Group T1w and T2w files by run to detect multi-run cases
                t1w_files = [f for f in anat_files if f.get_entities().get('suffix') == 'T1w']
                t2w_files = [f for f in anat_files if f.get_entities().get('suffix') == 'T2w']
                
                # Check if multiple T1w runs exist (needs synthesis)
                t1w_runs = [f.get_entities().get('run') for f in t1w_files if f.get_entities().get('run')]
                t1w_needs_synthesis = len(set(t1w_runs)) > 1 if t1w_runs else False
                
                # Check if multiple T2w runs exist (needs synthesis)
                t2w_runs = [f.get_entities().get('run') for f in t2w_files if f.get_entities().get('run')]
                t2w_needs_synthesis = len(set(t2w_runs)) > 1 if t2w_runs else False
                
                # Create job for each anatomical file
                # For T1w: if multiple runs, create synthesis job first
                if t1w_files:
                    if t1w_needs_synthesis:
                        # Create synthesis job
                        synthesis_job = {
                            "subject_id": sub,
                            "session_id": ses,
                            "file_paths": [f.path for f in t1w_files],
                            "modality": "anat",
                            "suffix": "T1w",
                            "task": None,
                            "run": None,
                            "entities": t1w_files[0].get_entities(),
                            "needs_synthesis": True,
                            "synthesis_type": "t1w"
                        }
                        anatomical_jobs.append(synthesis_job)
                    else:
                        # Single T1w file - create regular job
                        for t1w_file in t1w_files:
                            entities = t1w_file.get_entities()
                            job = {
                                "subject_id": sub,
                                "session_id": ses,
                                "file_path": t1w_file.path,
                                "modality": "anat",
                                "suffix": "T1w",
                                "task": None,
                                "run": entities.get('run'),
                                "entities": entities,
                                "needs_synthesis": False
                            }
                            anatomical_jobs.append(job)
                
                # T2w files: if multiple runs, create synthesis job; otherwise individual jobs
                # Check if T2w should be registered to T1w (if T1w exists in same session)
                has_t1w_in_session = len(t1w_files) > 0
                if t2w_files:
                    if t2w_needs_synthesis:
                        # Create synthesis job for T2w
                        t2w_synthesis_job = {
                            "subject_id": sub,
                            "session_id": ses,
                            "file_paths": [f.path for f in t2w_files],
                            "modality": "anat",
                            "suffix": "T2w",
                            "task": None,
                            "run": None,
                            "entities": t2w_files[0].get_entities(),
                            "needs_synthesis": True,
                            "synthesis_type": "t2w",
                            "needs_t1w_registration": has_t1w_in_session
                        }
                        anatomical_jobs.append(t2w_synthesis_job)
                    else:
                        # Single T2w file - create regular job
                        for t2w_file in t2w_files:
                            entities = t2w_file.get_entities()
                            job = {
                                "subject_id": sub,
                                "session_id": ses,
                                "file_path": t2w_file.path,
                                "modality": "anat",
                                "suffix": "T2w",
                                "task": None,
                                "run": entities.get('run'),
                                "entities": entities,
                                "needs_synthesis": False,
                                "needs_t1w_registration": has_t1w_in_session  # Flag for special T2w processing
                            }
                            anatomical_jobs.append(job)
    
    # Discover functional files (skip if anat_only is True)
    if not anat_only:
        for sub in target_subjects:
            sub_sessions = layout.get_sessions(subject=sub)
            if not sub_sessions:
                sub_sessions = [None]
            
            if sessions is not None:
                sub_sessions = [s for s in sub_sessions if s in sessions]
            
            for ses in sub_sessions:
                # Find functional files
                func_filters = {
                    "subject": sub,
                    "datatype": "func",
                    "suffix": "bold",
                    "extension": [".nii.gz", ".nii"]
                }
                if ses:
                    func_filters["session"] = ses
                if tasks:
                    func_filters["task"] = tasks
                if runs:
                    func_filters["run"] = runs
                
                func_files = list(layout.get(**func_filters))
                
                # Create job for each functional file
                for func_file in func_files:
                    entities = func_file.get_entities()
                    job = {
                        "subject_id": sub,
                        "session_id": ses,
                        "file_path": func_file.path,
                        "modality": "func",
                        "suffix": "bold",
                        "task": entities.get('task'),
                        "run": entities.get('run'),
                        "entities": entities,
                        "needs_synthesis": False
                    }
                    functional_jobs.append(job)
    else:
        logger.info("Skipping functional discovery (anat_only = True)")
    
    logger.info(f"Discovered {len(anatomical_jobs)} anatomical jobs and {len(functional_jobs)} functional jobs")
    
    return anatomical_jobs, functional_jobs

