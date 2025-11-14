"""
BIDS (Brain Imaging Data Structure) utilities for macacaMRIprep.

This module provides functions for parsing and working with BIDS-compliant
file names and directory structures.
"""

import re
from pathlib import Path
from typing import Dict, Optional, Union, Any
import json


# Standard BIDS entity order according to BIDS specification
# This ensures consistent ordering across all BIDS-related functions
BIDS_ENTITY_ORDER = [
    'sub', 'ses', 'task', 'acq', 'ce', 'dir', 'rec', 'run', 'echo', 
    'flip', 'inv', 'mt', 'part', 'recording', 'space', 'split', 'desc'
]


def get_filename_stem(file_path: Union[str, Path]) -> str:
    """
    Extract the filename stem (without extensions) from a file path.
    
    Handles multiple extensions like .nii.gz, .nii, .gz properly.
    This function preserves the exact input structure instead of reconstructing
    BIDS entities, avoiding potential mismatches.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Filename without extensions
        
    Examples:
        >>> get_filename_stem("sub-01_ses-pre_T1w.nii.gz")
        "sub-01_ses-pre_T1w"
        >>> get_filename_stem("/path/to/sub-01_task-rest_bold.nii")
        "sub-01_task-rest_bold"
    """
    file_path = Path(file_path)
    stem = file_path.name
    
    # Remove extensions in order of preference
    for ext in ['.nii.gz', '.nii', '.gz']:
        if stem.endswith(ext):
            stem = stem[:-len(ext)]
            break
            
    return stem


def parse_bids_entities(filename: str) -> Dict[str, str]:
    """
    Parse all BIDS entities from a filename.
    
    This function extracts ALL key-value pairs that follow the BIDS naming
    convention (key-value) from a filename, without being limited to a 
    predefined set of entities. This ensures we capture both standard
    and custom BIDS entities.
    
    Args:
        filename: BIDS filename to parse (can be full path or just filename)
    
    Returns:
        Dictionary mapping entity keys to values
        
    Examples:
        >>> parse_bids_entities("sub-01_ses-pre_task-rest_run-1_bold.nii.gz")
        {'sub': '01', 'ses': 'pre', 'task': 'rest', 'run': '1'}
        
        >>> parse_bids_entities("sub-032097_ses-001_run-1_desc-brain_T1w.nii.gz")
        {'sub': '032097', 'ses': '001', 'run': '1', 'desc': 'brain'}
    """
    # Extract just the filename if a full path was provided
    if '/' in filename or '\\' in filename:
        filename = Path(filename).name
    
    entities = {}
    
    # This captures ALL key-value pairs, not just predefined ones
    pattern = r'([a-zA-Z]+)-([a-zA-Z0-9-]+)'
    matches = re.findall(pattern, filename)
    
    for entity, value in matches:
        entities[entity] = value
    
    return entities


def create_bids_filename(entities: Dict[str, str], suffix: str, extension: str = ".nii.gz") -> str:
    """
    Create a BIDS-compliant filename from entities dictionary.
    
    Args:
        entities: Dictionary of BIDS entities (key-value pairs)
        suffix: BIDS suffix (e.g., 'T1w', 'bold', 'desc-brain_T1w')
        extension: File extension (default: '.nii.gz')
    
    Returns:
        BIDS-compliant filename
        
    Examples:
        >>> create_bids_filename({'sub': '01', 'ses': 'pre'}, 'T1w')
        'sub-01_ses-pre_T1w.nii.gz'
        
        >>> create_bids_filename({'sub': '01', 'run': '1'}, 'desc-brain_T1w')
        'sub-01_run-1_desc-brain_T1w.nii.gz'
    """
    # Use the standard BIDS entity order
    
    # Build filename components in proper order
    components = []
    
    # Add entities in standard order first
    for entity in BIDS_ENTITY_ORDER:
        if entity in entities:
            components.append(f"{entity}-{entities[entity]}")
    
    # Add any remaining entities not in the standard order
    remaining_entities = set(entities.keys()) - set(BIDS_ENTITY_ORDER)
    for entity in sorted(remaining_entities):  # Sort for consistency
        components.append(f"{entity}-{entities[entity]}")
    
    # Join components and add suffix and extension
    filename = "_".join(components)
    if filename:
        filename += f"_{suffix}{extension}"
    else:
        filename = f"{suffix}{extension}"
    
    return filename


def find_bids_metadata(nifti_path: Union[str, Path], dataset_dir: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Find and load BIDS sidecar JSON metadata for a NIfTI file using hierarchical search.
    
    BIDS inheritance principle: JSON files at higher levels in the hierarchy 
    are inherited by files at lower levels, with more specific files taking precedence.
    
    Search order:
    1. Exact match in same directory (most specific)
    2. Session level (if applicable)
    3. Subject level
    4. Dataset root level (most general)
    
    Args:
        nifti_path: Path to the NIfTI file
        dataset_dir: Root directory of the BIDS dataset
        
    Returns:
        Dictionary containing merged metadata from all applicable JSON files,
        or None if no metadata found
    """
    nifti_path = Path(nifti_path)
    dataset_dir = Path(dataset_dir)
    
    # Extract BIDS entities from filename
    entities = parse_bids_entities(nifti_path.name)
    
    # Generate potential JSON filenames at different hierarchy levels
    json_candidates = []
    
    # 1. Exact match in same directory (highest priority)
    exact_json = nifti_path.with_suffix('').with_suffix('.json')
    if exact_json.exists():
        json_candidates.append(exact_json)
    
    # 2. Session level JSON (if session exists)
    if entities.get('ses'):
        ses_dir = dataset_dir / f"sub-{entities['sub']}" / f"ses-{entities['ses']}"
        
        # Look for modality-specific JSONs
        if 'task' in entities:
            # task-specific JSON
            ses_task_json = ses_dir / nifti_path.parent.name / f"task-{entities['task']}_bold.json"
            if ses_task_json.exists():
                json_candidates.append(ses_task_json)
        
        # General modality JSON at session level
        if nifti_path.parent.name in ['func', 'anat', 'dwi', 'fmap']:
            ses_modality_json = ses_dir / nifti_path.parent.name / f"{nifti_path.suffix.replace('.nii.gz', '.json').replace('.nii', '.json')}"
            # This is for files like T1w.json, bold.json at session level
            general_name = nifti_path.name.split('_')[-1].replace('.nii.gz', '.json').replace('.nii', '.json')
            ses_general_json = ses_dir / nifti_path.parent.name / general_name
            if ses_general_json.exists():
                json_candidates.append(ses_general_json)
    
    # 3. Subject level JSON
    sub_dir = dataset_dir / f"sub-{entities['sub']}"
    
    if 'task' in entities:
        # task-specific JSON at subject level
        sub_task_json = sub_dir / nifti_path.parent.name / f"task-{entities['task']}_bold.json"
        if sub_task_json.exists():
            json_candidates.append(sub_task_json)
    
    # General modality JSON at subject level
    if nifti_path.parent.name in ['func', 'anat', 'dwi', 'fmap']:
        general_name = nifti_path.name.split('_')[-1].replace('.nii.gz', '.json').replace('.nii', '.json')
        sub_general_json = sub_dir / nifti_path.parent.name / general_name
        if sub_general_json.exists():
            json_candidates.append(sub_general_json)
    
    # 4. Dataset root level JSON (lowest priority)
    if 'task' in entities:
        # task-specific JSON at dataset level
        dataset_task_json = dataset_dir / f"task-{entities['task']}_bold.json"
        if dataset_task_json.exists():
            json_candidates.append(dataset_task_json)
    
    # General modality JSON at dataset level
    general_name = nifti_path.name.split('_')[-1].replace('.nii.gz', '.json').replace('.nii', '.json')
    dataset_general_json = dataset_dir / general_name
    if dataset_general_json.exists():
        json_candidates.append(dataset_general_json)
    
    # Load and merge JSON files (most general first, most specific last)
    merged_metadata = {}
    
    # Reverse the list to start with most general (dataset level) and end with most specific (exact match)
    for json_file in reversed(json_candidates):
        try:
            with open(json_file, 'r') as f:
                metadata = json.load(f)
                merged_metadata.update(metadata)  # More specific files override general ones
        except (json.JSONDecodeError, IOError) as e:
            # Log warning but continue with other files
            continue
    
    return merged_metadata if merged_metadata else None

