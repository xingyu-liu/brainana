"""
MRI processing utilities for macacaMRIprep.

This module provides utilities for common MRI processing operations.
"""

import os
import logging
import nibabel as nib
import numpy as np
from typing import Dict, Optional, Union
from nibabel.orientations import aff2axcodes
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
    Note:
        this function can get the orientation without loading the image file
        Be careful about afni and fsl or nibable using opposite orientation code.
        For example, RAS in fsl is actually LPI in afni.
        So when using afni's orientation code, always use afni's reorientation function.
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


def get_opposite_orientation(direction: str) -> str:
    """
    Get the opposite anatomical direction.
    
    Args:
        direction: One of 'R', 'L', 'A', 'P', 'S', 'I'
        
    Returns:
        Opposite direction (e.g., 'R' -> 'L', 'A' -> 'P')
    """
    opposites = {'R': 'L', 'L': 'R', 'A': 'P', 'P': 'A', 'S': 'I', 'I': 'S'}
    return opposites.get(direction, direction)


def get_image_orientation_from_affine(
    affine: Union[np.ndarray, nib.spatialimages.SpatialImage],
) -> str:
    """Get orientation code from an affine matrix.
    
    Args:
        affine: Affine matrix (4x4 numpy array) or nibabel image object
        
    Returns:
        Orientation code string (e.g., 'RAS', 'LPI', 'RPS')
        
    Raises:
        ValueError: If aff2axcodes returns unexpected type
        AttributeError: If affine cannot be extracted from input
    """
    # Extract affine matrix if input is a nibabel image
    if isinstance(affine, nib.spatialimages.SpatialImage):
        affine_matrix = affine.affine
    else:
        affine_matrix = affine
    
    # Get orientation code from affine matrix
    axes_codes = nib.aff2axcodes(affine_matrix)
    if not isinstance(axes_codes, (list, tuple)):
        raise ValueError(
            f"aff2axcodes returned unexpected type: {type(axes_codes)}, value: {axes_codes}"
        )
    
    orientation_code = "".join(axes_codes)
    return orientation_code


# Module-level cache for rotation matrices
_N90_ROTATIONS_3X3 = None
_N90_ROTATIONS_4X4 = None


def _generate_n90_rotations() -> list[np.ndarray]:
    """Generate all 24 unique n×90° rotation matrices (all rotational symmetries of a cube).
    
    For 90° increments, cos and sin values are always 0, 1, or -1, so we hardcode them
    for efficiency and clarity. Results are cached at module level.
    
    This generates all 24 possible orientations reachable by n×90° rotations.
    The 24 rotations are all proper rotations (det=1) that map basis vectors to ±basis vectors.
    
    Returns:
        List of 24 unique 3x3 rotation matrices
    """
    global _N90_ROTATIONS_3X3
    
    if _N90_ROTATIONS_3X3 is not None:
        return _N90_ROTATIONS_3X3
    
    # Base rotations around principal axes
    Rx90 = np.array([[1,  0,  0], [0,  0, -1], [0,  1,  0]], dtype=np.float64)   # 90° around X
    Rx180 = np.array([[1,  0,  0], [0, -1,  0], [0,  0, -1]], dtype=np.float64)  # 180° around X
    Rx270 = np.array([[1,  0,  0], [0,  0,  1], [0, -1,  0]], dtype=np.float64)  # 270° around X
    
    Ry90 = np.array([[ 0,  0,  1], [ 0,  1,  0], [-1,  0,  0]], dtype=np.float64)  # 90° around Y
    Ry180 = np.array([[-1,  0,  0], [ 0,  1,  0], [ 0,  0, -1]], dtype=np.float64) # 180° around Y
    Ry270 = np.array([[ 0,  0, -1], [ 0,  1,  0], [ 1,  0,  0]], dtype=np.float64)  # 270° around Y
    
    Rz90 = np.array([[ 0, -1,  0], [ 1,  0,  0], [ 0,  0,  1]], dtype=np.float64)   # 90° around Z
    Rz180 = np.array([[-1,  0,  0], [ 0, -1,  0], [ 0,  0,  1]], dtype=np.float64)  # 180° around Z
    Rz270 = np.array([[ 0,  1,  0], [-1,  0,  0], [ 0,  0,  1]], dtype=np.float64)  # 270° around Z
    
    # Generate all combinations systematically
    # Start with identity and single-axis rotations
    rotations = [np.eye(3, dtype=np.float64)]
    rotations.extend([Rx90, Rx180, Rx270, Ry90, Ry180, Ry270, Rz90, Rz180, Rz270])
    
    # Generate composite rotations: all combinations of two rotations
    base_rots = [Rx90, Rx180, Rx270, Ry90, Ry180, Ry270, Rz90, Rz180, Rz270]
    for r1 in base_rots:
        for r2 in base_rots:
            composite = r1 @ r2
            rotations.append(composite)
    
    # Remove duplicates by comparing matrices (with tolerance for floating point)
    unique_rotations = []
    seen = set()
    for rot in rotations:
        # Round to handle any floating point issues, then convert to tuple
        rot_rounded = np.round(rot, decimals=10)
        rot_tuple = tuple(rot_rounded.flatten())
        if rot_tuple not in seen:
            seen.add(rot_tuple)
            unique_rotations.append(rot)
    
    # Should have exactly 24 rotations
    if len(unique_rotations) != 24:
        # If we don't have exactly 24, log a warning but continue
        import logging
        logging.warning(f"Expected 24 unique rotations, found {len(unique_rotations)}")
    
    _N90_ROTATIONS_3X3 = unique_rotations
    return unique_rotations


def _get_n90_rotations_4x4() -> list[np.ndarray]:
    """Get cached 4x4 rotation matrices for affine transformations.
    
    Returns:
        List of 4x4 rotation matrices (cached)
    """
    global _N90_ROTATIONS_4X4
    
    if _N90_ROTATIONS_4X4 is not None:
        return _N90_ROTATIONS_4X4
    
    rotations_3x3 = _generate_n90_rotations()
    rotations_4x4 = []
    
    for rot_3x3 in rotations_3x3:
        rot_4x4 = np.eye(4, dtype=rot_3x3.dtype)
        rot_4x4[:3, :3] = rot_3x3
        rotations_4x4.append(rot_4x4)
    
    _N90_ROTATIONS_4X4 = rotations_4x4
    return rotations_4x4


def _determine_third_orientation(
    dir1_idx: int,
    dir2_idx: int,
    dir3_idx: int,
    dir1: str,
    dir2: str,
    dir1_type: str,
    dir2_type: str
) -> str:
    """Determine the third orientation direction using right-hand rule.
    
    Given two orientations and their positions, determines the third orientation
    that satisfies the right-hand rule: R × A = S (where × is cross product).
    
    The function is general and works for any combination:
    - A/P and S/I → determines R/L
    - A/P and R/L → determines S/I
    - S/I and R/L → determines A/P
    
    Args:
        dir1_idx: Axis index (0, 1, or 2) where first direction is located
        dir2_idx: Axis index (0, 1, or 2) where second direction is located
        dir3_idx: Axis index (0, 1, or 2) where third direction should be determined
        dir1: First direction (e.g., 'A', 'P', 'S', 'I', 'R', 'L')
        dir2: Second direction (e.g., 'A', 'P', 'S', 'I', 'R', 'L')
        dir1_type: Type of first direction ('AP', 'SI', or 'RL')
        dir2_type: Type of second direction ('AP', 'SI', or 'RL')
        
    Returns:
        The third direction that satisfies right-hand rule
        
    Examples:
        >>> # RAS: R(0) × A(1) = S(2) - right-handed
        >>> _determine_third_orientation(1, 2, 0, 'A', 'S', 'AP', 'SI')
        'R'
        
        >>> # xSA → LSA: L(0) × A(2) = S(1) - left-handed
        >>> _determine_third_orientation(2, 1, 0, 'A', 'S', 'AP', 'SI')
        'L'
    """
    # Right-handed cycles follow the pattern: (0,1,2), (1,2,0), (2,0,1)
    # These have even parity (determinant = +1)
    # Left-handed cycles: (0,2,1), (1,0,2), (2,1,0) have odd parity (determinant = -1)
    right_handed_cycles = {(0, 1, 2), (1, 2, 0), (2, 0, 1)}
    
    # Check if the axis order (dir3_idx, dir1_idx, dir2_idx) forms a right-handed cycle
    cycle = (dir3_idx, dir1_idx, dir2_idx)
    parity = 1 if cycle in right_handed_cycles else -1
    
    # Convert directions to signs: A/S/R = +1, P/I/L = -1
    dir1_sign = 1 if dir1 in ['A', 'S', 'R'] else -1
    dir2_sign = 1 if dir2 in ['A', 'S', 'R'] else -1
    
    # Calculate third direction sign using the right-hand rule:
    # For right-handed: dir3_sign × dir1_sign = dir2_sign  →  dir3_sign = dir2_sign × dir1_sign
    # For left-handed: dir3_sign × dir1_sign = -dir2_sign  →  dir3_sign = -dir2_sign × dir1_sign
    # Combined: dir3_sign = parity × dir2_sign × dir1_sign
    dir3_sign = parity * dir2_sign * dir1_sign
    
    # Determine which type of direction we need to return
    # The three types are: AP (Anterior/Posterior), SI (Superior/Inferior), RL (Right/Left)
    all_types = {'AP', 'SI', 'RL'}
    dir3_type = (all_types - {dir1_type, dir2_type}).pop()
    
    # Map sign to direction based on type
    if dir3_type == 'RL':
        return 'R' if dir3_sign > 0 else 'L'
    elif dir3_type == 'AP':
        return 'A' if dir3_sign > 0 else 'P'
    else:  # SI
        return 'S' if dir3_sign > 0 else 'I'


def correct_affine_for_mismatch_orientation(
    affine: Union[np.ndarray, nib.spatialimages.SpatialImage],
    real_A_is_actually_labeled_as: str,
    real_S_is_actually_labeled_as: str,
) -> np.ndarray:
    """Correct affine for orientation mismatch.

    The mismatch is caused by physical misorientation of the brain (n×90° rotation).
    This function finds the unique rotation that corrects the affine matrix.

    Args:
        affine: Affine matrix (4x4 numpy array) or nibabel image object
        real_A_is_actually_labeled_as: What the axis currently labeled 'A' actually points to
            (one of: 'P', 'S', 'I', 'R', 'L')
        real_S_is_actually_labeled_as: What the axis currently labeled 'S' actually points to
            (one of: 'A', 'P', 'I', 'R', 'L')
        
    Returns:
        Corrected affine matrix (4x4 numpy array)
    
    Note:
        The parameters are assumed to be validated by the config validation module.
        Only A/P and S/I mismatches are corrected; R/L is determined by right-hand rule.
    """
    # Extract affine matrix if input is a nibabel image
    if isinstance(affine, nib.spatialimages.SpatialImage):
        affine_matrix = affine.affine.copy()
    else:
        affine_matrix = affine.copy()
    
    # Step 1: Get current orientation code
    current_axes = list(aff2axcodes(affine_matrix))
    current_orientation = "".join(current_axes)
    
    # Find indices of A/P and S/I in current orientation
    # We need to find which axis is labeled 'A' (or 'P') and which is labeled 'S' (or 'I')
    try:
        a_idx = current_axes.index('A')
    except ValueError:
        try:
            a_idx = current_axes.index('P')
        except ValueError:
            raise ValueError(f"Current orientation {current_orientation} has neither 'A' nor 'P'")
    
    try:
        s_idx = current_axes.index('S')
    except ValueError:
        try:
            s_idx = current_axes.index('I')
        except ValueError:
            raise ValueError(f"Current orientation {current_orientation} has neither 'S' nor 'I'")
    
    # Step 2: Build target orientation code
    # Normalize the mismatch parameters to uppercase
    real_A_dir = real_A_is_actually_labeled_as.upper()
    real_S_dir = real_S_is_actually_labeled_as.upper()
    
    # Create target orientation code
    # The axis at a_idx is currently labeled 'A' (or 'P') but actually points to real_A_dir
    # After correction, it should be labeled with real_A_dir
    target_axes = current_axes.copy()
    target_axes[a_idx] = real_A_dir
    target_axes[s_idx] = real_S_dir
    
    # Find R/L index (the one that's not A or S)
    rl_idx = [i for i in range(3) if i not in [a_idx, s_idx]][0]
    
    # Step 2b: Determine the third orientation using right-hand rule
    # Find where A/P and S/I are in the target orientation
    # They could be at a_idx, s_idx, or rl_idx depending on what real_A_dir and real_S_dir are
    
    ap_dir = None
    si_dir = None
    ap_pos = None
    si_pos = None
    
    # Check each position in target_axes to find A/P and S/I
    for pos in [a_idx, s_idx, rl_idx]:
        d = target_axes[pos]
        if d in ['A', 'P']:
            ap_dir = d
            ap_pos = pos
        elif d in ['S', 'I']:
            si_dir = d
            si_pos = pos
    
    # Determine the third orientation using right-hand rule
    if ap_dir is not None and si_dir is not None:
        # We have A/P and S/I, need to determine R/L
        rl_dir = _determine_third_orientation(
            ap_pos, si_pos, rl_idx, ap_dir, si_dir, 'AP', 'SI'
        )
        target_axes[rl_idx] = rl_dir
    elif ap_dir is not None:
        # We have A/P, need to determine S/I (real_S_dir must be R/L)
        # Find where R/L is (it's at s_idx since real_S_dir is R/L)
        rl_at_s = target_axes[s_idx]  # This is real_S_dir which is R/L
        # Determine S/I based on A/P and R/L, S/I goes at s_idx
        si_dir = _determine_third_orientation(
            ap_pos, s_idx, s_idx, ap_dir, rl_at_s, 'AP', 'RL'
        )
        target_axes[s_idx] = si_dir
    elif si_dir is not None:
        # We have S/I, need to determine A/P (real_A_dir must be R/L)
        # Find where R/L is (it's at a_idx since real_A_dir is R/L)
        rl_at_a = target_axes[a_idx]  # This is real_A_dir which is R/L
        # Determine A/P based on S/I and R/L, A/P goes at a_idx
        ap_dir = _determine_third_orientation(
            si_pos, a_idx, a_idx, si_dir, rl_at_a, 'SI', 'RL'
        )
        target_axes[a_idx] = ap_dir
    
    target_orientation = "".join(target_axes)
    
    # Step 3: Test all n×90° rotations to find the one that matches target
    rotations_4x4 = _get_n90_rotations_4x4()
    
    # Test each rotation (left-multiply: R @ A)
    for rot_4x4 in rotations_4x4:
        test_affine = rot_4x4 @ affine_matrix
        test_axes = list(aff2axcodes(test_affine))
        test_orientation = "".join(test_axes)
        
        if test_orientation == target_orientation:
            # Found the correct rotation!
            return test_affine
    
    # If no rotation found, raise an error
    raise ValueError(
        f"Could not find n×90° rotation to transform orientation "
        f"{current_orientation} to {target_orientation}. "
        f"This may indicate the mismatch parameters are incorrect."
    )

