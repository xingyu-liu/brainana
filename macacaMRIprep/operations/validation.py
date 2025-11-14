"""
Input validation and file system utilities for macacaMRIprep.

This module provides validation functions for input files, working directories,
and output files to ensure data integrity throughout the preprocessing pipeline.
"""

import os
import logging
from typing import Union, Dict, Any
from pathlib import Path
import json

def validate_input_file(imagef: Union[str, Path], logger: logging.Logger) -> Path:
    """Validate input neuroimaging file.
    
    Args:
        imagef: Path to input file
        logger: Logger instance
        
    Returns:
        Validated Path object
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is not a valid neuroimaging file
    """
    image_path = Path(imagef)
    if not image_path.exists():
        raise FileNotFoundError(f"Input file not found: {image_path}")
    
    # Validate it's a neuroimaging file
    if not str(image_path).endswith(('.nii', '.nii.gz')):
        raise ValueError(f"Input file must be a NIFTI file: {image_path}")
    
    logger.debug(f"Data: input file validated - {image_path}")
    return image_path

def validate_working_directory(working_dir: Union[str, Path], logger: logging.Logger) -> Path:
    """Validate working directory path and parent directory permissions.
    
    Args:
        working_dir: Working directory path
        logger: Logger instance
        
    Returns:
        Path object for working directory
        
    Raises:
        PermissionError: If parent directory cannot be accessed or written to
    """
    work_dir = Path(working_dir)
    
    # Check if directory already exists
    if work_dir.exists():
        # Test write permission if it exists
        try:
            test_file = work_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            logger.debug(f"System: working directory validated (existing) - {work_dir}")
            return work_dir
        except Exception as e:
            raise PermissionError(f"Cannot write to existing working directory {work_dir}: {e}")
    
    # If it doesn't exist, check that parent directory is writable
    parent_dir = work_dir.parent
    if not parent_dir.exists():
        # Try to create parent directory if it doesn't exist
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise PermissionError(f"Cannot create parent directory {parent_dir}: {e}")
    
    # Test write permission on parent directory
    try:
        test_file = parent_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.debug(f"System: working directory path validated (will be created when needed) - {work_dir}")
        return work_dir
    except Exception as e:
        raise PermissionError(f"Cannot write to parent directory {parent_dir}: {e}")

def ensure_working_directory(working_dir: Union[str, Path], logger: logging.Logger) -> Path:
    """Ensure working directory exists and is writable.
    
    Args:
        working_dir: Working directory path
        logger: Logger instance
        
    Returns:
        Path object for working directory
        
    Raises:
        PermissionError: If directory cannot be created or written to
    """
    work_dir = Path(working_dir)
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = work_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        logger.debug(f"System: working directory ensured - {work_dir}")
        return work_dir
    except Exception as e:
        raise PermissionError(f"Cannot create or write to working directory {work_dir}: {e}")

def validate_output_file(output_path: Union[str, Path], logger: logging.Logger) -> Path:
    """Validate that output file was created successfully.
    
    Args:
        output_path: Path to output file
        logger: Logger instance
        
    Returns:
        Validated Path object
        
    Raises:
        FileNotFoundError: If output file doesn't exist
        ValueError: If output file is invalid
    """
    output_file = Path(output_path)
    if not output_file.exists():
        raise FileNotFoundError(f"Expected output file not created: {output_file}")
    
    # Validate it's a valid neuroimaging file
    if not str(output_file).endswith(('.nii', '.nii.gz')):
        raise ValueError(f"Output file must be a NIFTI file: {output_file}")
    
    logger.debug(f"Data: output file validated - {output_file}")
    return output_file
