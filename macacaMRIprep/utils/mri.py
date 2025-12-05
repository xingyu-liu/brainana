"""
MRI processing utilities for macacaMRIprep.

This module provides utilities for common MRI processing operations.
"""

import os
import logging
from typing import Dict, Optional
from .system import run_command

def calculate_func_tmean(
    funcf: str,
    outputf: str,
    logger: logging.Logger,
) -> Dict[str, str]:
    """Calculate mean functional image.
    
    Args:
        funcf: Input functional file
        dir_working: Working directory
        logger: Logger instance
        output_name: Name for the output mean file
    
    Returns:
        Dictionary with output file path
    """

    # Build command as list of strings
    command_fslmaths = [
        'fslmaths',
        str(funcf),
        '-Tmean',
        str(outputf)
    ]
    
    try:
        returncode, stdout, stderr = run_command(command_fslmaths, step_logger=logger)
        if returncode == 0:
            logger.info(f"Output: mean functional image created successfully - {outputf}")
        else:
            logger.error(f"Step: mean functional image creation failed - return code {returncode}")
            logger.error(f"System: stderr - {stderr}")
            raise RuntimeError(f"Mean functional image creation failed: {stderr}")
    except Exception as e:
        logger.error(f"Step: mean functional image creation failed - {str(e)}")
        raise
    
    return {"output": outputf} 

def get_image_shape(
    imagef: str,
    logger: Optional[logging.Logger] = None,
) -> list:
    """Get image shape.
    
    Args:
        imagef: Input image file
        logger: Logger instance
        
    Returns:
        List of integers representing image dimensions [x, y, z, t]
    """
    # use 3dinfo to get the shape of the image
    command_3dinfo = [
        '3dinfo',
        '-n4',
        str(imagef)
    ]
    returncode, stdout, stderr = run_command(command_3dinfo, step_logger=logger)
    if returncode == 0:
        logger.info(f"Data: image shape - {stdout}")
        # Parse the output and convert to integers
        shape_values = stdout.strip().split()
        return [int(dim) for dim in shape_values]
    else:
        logger.error(f"Step: image shape retrieval failed - return code {returncode}")
        logger.error(f"System: stderr - {stderr}")
        raise RuntimeError(f"Image shape retrieval failed: {stderr}")
    
def get_image_resolution(
    imagef: str,
    logger: Optional[logging.Logger] = None,
) -> list:
    """Get image resolution.
    
    Args:
        imagef: Input image file
        logger: Logger instance
        
    Returns:
        List of floats representing image resolution [x, y, z]
    """
    # use 3dinfo to get the resolution of the image
    command_3dinfo = [
        '3dinfo',
        '-ad3',
        str(imagef)
    ]  
    returncode, stdout, stderr = run_command(command_3dinfo, step_logger=logger)
    if returncode == 0:
        logger.info(f"Data: image resolution - {stdout}")
        # Parse the output and convert to floats
        resolution_values = stdout.strip().split()
        return [float(res) for res in resolution_values]
    else:
        logger.error(f"Step: image resolution retrieval failed - return code {returncode}")
        logger.error(f"System: stderr - {stderr}")
        raise RuntimeError(f"Image resolution retrieval failed: {stderr}")


def get_image_orientation(
    imagef: str,
    logger: Optional[logging.Logger] = None,
) -> str:
    """Get the orientation code of an image file.
    
    Args:
        imagef: Input image file
        logger: Optional logger instance
    
    Returns:
        Orientation code string (e.g., 'RAS', 'LPI', 'RPS')
        
    Raises:
        RuntimeError: If orientation retrieval fails
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # use 3dinfo to get the orientation of the image file
    command_3dinfo = [
        '3dinfo',
        '-orient',
        str(imagef)
    ]
    returncode, stdout, stderr = run_command(command_3dinfo, step_logger=logger)
    if returncode == 0:
        orientation = stdout.strip()  # Remove newline characters
        logger.debug(f"Data: image orientation - {orientation}")
        return orientation
    else:
        logger.error(f"Step: image orientation retrieval failed - return code {returncode}")
        raise RuntimeError(f"Failed to get image orientation: {stderr}")


def reorient_image_to_orientation(
    imagef: str,
    orientation: str,
    outputf: str,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """Reorient image to a specific orientation.
    
    Args:
        imagef: Input image file
        orientation: Target orientation string (e.g., 'RAS', 'LPI', 'RPS')
        outputf: Output image file
        logger: Logger instance
    
    Returns:
        Dictionary with output file path
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Validate orientation string (should be 3 characters)
    if len(orientation) != 3:
        raise ValueError(f"Orientation must be a 3-character string (e.g., 'RAS'), got '{orientation}'")
    
    valid_chars = set('RLAPIS')
    if not all(c in valid_chars for c in orientation.upper()):
        raise ValueError(f"Orientation contains invalid characters. Must be from {{R, L, A, P, I, S}}, got '{orientation}'")
    
    orientation = orientation.upper()
    logger.info(f"Data: target orientation - {orientation}")

    # use 3dresample to reorient the image to the target orientation
    command_3dresample = [
        '3dresample',
        '-input', str(imagef),
        '-prefix', str(outputf),
        '-orient', orientation
    ]
    returncode, stdout, stderr = run_command(command_3dresample, step_logger=logger)
    if returncode == 0:
        logger.info(f"Output: image reoriented successfully - {outputf}")
    else:
        logger.error(f"Step: image reorientation failed - return code {returncode}")
        logger.error(f"System: stderr - {stderr}")
        raise RuntimeError(f"Image reorientation failed: {stderr}")
    
    return {"output": outputf}


def reorient_image_to_target(
    imagef: str,
    targetf: str,
    outputf: str,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """Reorient image to match the orientation of a target file.
    
    Args:
        imagef: Input image file
        targetf: Target image file (orientation will be extracted from this file)
        outputf: Output image file
        logger: Logger instance
    
    Returns:
        Dictionary with output file path
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Get orientation from target file
    orientation = get_image_orientation(targetf, logger)
    logger.info(f"Data: target file orientation - {orientation}")

    # Use the orientation-based reorientation function
    return reorient_image_to_orientation(imagef, orientation, outputf, logger)
    