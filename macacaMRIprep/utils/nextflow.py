"""
Nextflow-specific utility functions for macacaMRIprep.

This module provides utilities that are commonly used in Nextflow process scripts.
"""

from pathlib import Path
import os
import shutil
import json
import yaml
from typing import Dict, Any, Optional, Union

from .bids import get_filename_stem
from .system import init_cmd_log_file as _init_cmd_log_file


def create_output_link(source_file, target_file):
    """
    Create symlink from source to target, fallback to copy if symlink fails.
    
    This function is used in Nextflow processes to avoid duplicating large files
    between the work directory and process output directory. Nextflow's publishDir
    will follow the symlink and copy the actual file content to the final output.
    
    Args:
        source_file: Path to source file (typically in work/ directory)
        target_file: Path to target file (in process output directory)
    
    Returns:
        None (creates symlink or copies file)
    """
    try:
        source_path = Path(source_file)
        target_path = Path(target_file)
        if target_path.exists() or target_path.is_symlink():
            target_path.unlink()
        source_rel = os.path.relpath(str(source_path), str(target_path.parent))
        os.symlink(source_rel, str(target_path))
    except (OSError, AttributeError):
        # Symlink not possible (different filesystem or Windows), use copy
        shutil.copy2(source_file, target_file)


def load_config(config_file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load YAML configuration file.
    
    This is a convenience wrapper for loading YAML config files in Nextflow processes.
    
    Args:
        config_file_path: Path to YAML configuration file
    
    Returns:
        Dictionary containing configuration values
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    config_path = Path(config_file_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    return config or {}


def detect_modality(bids_naming_template: Union[str, Path]) -> str:
    """
    Detect anatomical modality (T1w or T2w) from BIDS naming template filename.
    
    Args:
        bids_naming_template: Path to BIDS file (used as naming template)
    
    Returns:
        Modality string: 'T1w' or 'T2w' (defaults to 'T1w' if not detected)
    """
    original_stem = get_filename_stem(bids_naming_template)
    modality = 'T1w'  # default
    if '_T2w' in original_stem or original_stem.endswith('_T2w'):
        modality = 'T2w'
    elif '_T1w' in original_stem or original_stem.endswith('_T1w'):
        modality = 'T1w'
    return modality


def save_metadata(metadata_dict: Dict[str, Any], output_path: Union[str, Path] = 'metadata.json') -> None:
    """
    Save metadata dictionary to JSON file.
    
    Args:
        metadata_dict: Dictionary containing metadata to save
        output_path: Path to output JSON file (default: 'metadata.json')
    """
    output_file = Path(output_path)
    with open(output_file, 'w') as f:
        json.dump(metadata_dict, f, indent=2)


def init_cmd_log_for_nextflow(
    output_dir: str,
    subject_id: str,
    session_id: Optional[str],
    step_name: str
) -> Optional[Path]:
    """
    Initialize command log file for Nextflow process.
    
    This is a convenience wrapper around init_cmd_log_file that constructs
    the job_id from subject_id and session_id, which is the common pattern
    in Nextflow processes.
    
    Args:
        output_dir: Output directory path (string from Nextflow params)
        subject_id: Subject ID
        session_id: Session ID (can be None or empty string)
        step_name: Step/process name (e.g., 'ANAT_REORIENT')
    
    Returns:
        Path to command log file, or None if initialization failed
    """
    # Construct job_id from subject_id and session_id
    job_id = f"sub-{subject_id}"
    if session_id:
        job_id += f"_ses-{session_id}"
    
    return _init_cmd_log_file(
        output_dir=output_dir,
        job_id=job_id,
        step_name=step_name,
        subject_id=subject_id,
        session_id=session_id if session_id else None
    )

