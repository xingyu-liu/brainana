"""
Nextflow-specific utility functions for macacaMRIprep.

This module provides utilities that are commonly used in Nextflow process scripts.
"""

from pathlib import Path
import os
import shutil


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

