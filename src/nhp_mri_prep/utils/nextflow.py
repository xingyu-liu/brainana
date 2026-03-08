"""
Nextflow-specific utility functions for nhp_mri_prep.

This module provides utilities that are commonly used in Nextflow process scripts.
"""

from pathlib import Path
import os
import shutil
import json
from typing import Dict, Any, Optional, Union

from .bids import get_filename_stem
from ..config.config_io import load_yaml_config


def create_output_link(source_file, target_file):
    """
    Create symlink from source to target, fallback to copy if symlink fails.

    This function is used in Nextflow processes to avoid duplicating large files
    between the work directory and process output directory. Nextflow's publishDir
    will follow the symlink and copy the actual file content to the final output.

    IMPORTANT: Resolves source symlinks to the original non-symlink file before
    creating a new symlink. This prevents deep symlink chains.

    Symlinks can fail with "Operation not supported" (errno 95 / EOPNOTSUPP) when
    the target directory is on a filesystem that does not support them, such as:
    - Docker bind-mounts from a Windows host
    - NFS or network shares mounted with nosymlink
    - FAT32, exFAT, or other non-Unix filesystems

    In those cases the function falls back to copying the file.

    Args:
        source_file: Path to source file (typically in work/ directory)
        target_file: Path to target file (in process output directory)

    Returns:
        None (creates symlink or copies file)
    """
    source_path = Path(source_file)
    target_path = Path(target_file)

    # Remove target if it exists
    if target_path.exists() or target_path.is_symlink():
        target_path.unlink()

    # Resolve source to actual file (follows symlink chain to original file)
    # This prevents creating symlinks to symlinks (deep symlink chains)
    source_resolved = source_path.resolve(strict=True)

    try:
        # Calculate relative path from target's parent to resolved source
        # This ensures the symlink works even if work directories are moved
        source_rel = os.path.relpath(str(source_resolved), str(target_path.parent))
        os.symlink(source_rel, str(target_path))
    except Exception:
        # Symlink not possible: filesystem doesn't support symlinks (EOPNOTSUPP),
        # cross-device link, or any other failure. Fall back to copy.
        shutil.copy2(str(source_resolved), str(target_path))


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
        ValueError: If YAML parsing fails
    """
    config_path = Path(config_file_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = load_yaml_config(config_path)
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


def normalize_session_id(session_id_raw: Optional[str]) -> Optional[str]:
    """
    Normalize session ID from Nextflow.
    
    Handles various representations of empty/null session IDs:
    - None
    - Empty string ""
    - Whitespace-only strings
    - String "null" (Nextflow may pass "null" as a string when session_id is empty/null in Groovy)
    
    Args:
        session_id_raw: Raw session ID from Nextflow
        
    Returns:
        Normalized session ID string, or None if empty/null
    """
    if not session_id_raw:
        return None
    
    session_id = session_id_raw.strip()
    if not session_id or session_id.lower() == 'null':
        return None
    
    return session_id

