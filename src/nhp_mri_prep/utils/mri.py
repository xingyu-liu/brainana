"""
MRI processing utilities for nhp_mri_prep.

This module provides utilities for common MRI processing operations.
"""

import os
import logging
import nibabel as nib
import numpy as np
from pathlib import Path
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
    if logger is None:
        logger = logging.getLogger(__name__)
    
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


def shape_to_ants_input_type(shape: list) -> int:
    """Map image shape to ANTs antsApplyTransforms -e (input-image-type) value.

    ANTs -e options: 0=scalar, 1=vector, 2=tensor, 3=time-series, 4=multichannel,
    5=five-dimensional. For 3D/4D images: 3D or 4D with last dim 1 -> 0 (scalar);
    4D with last dim > 1 -> 3 (time-series).

    Args:
        shape: Image dimensions from get_image_shape [x, y, z, t] or [x, y, z]

    Returns:
        Integer 0-5 for antsApplyTransforms -e
    """
    if len(shape) < 3:
        return 0
    if len(shape) == 3:
        return 0
    # len >= 4: check 4th dimension
    if shape[3] <= 1:
        return 0  # scalar (3D or pseudo-3D)
    return 3  # time-series (4D)


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
    if logger is None:
        logger = logging.getLogger(__name__)
    
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


# Cross product coefficients: basis(type1) × basis(type2) = coeff * basis(type3)
# In RAS space: RL=X, AP=Y, SI=Z
# Standard cross products: X × Y = Z, Y × Z = X, Z × X = Y (positive)
# Reverse order: Y × X = -Z, Z × Y = -X, X × Z = -Y (negative)
_CROSS_COEFFS = {
    ('RL', 'AP', 'SI'): 1,   # R × A = S
    ('AP', 'SI', 'RL'): 1,   # A × S = R
    ('SI', 'RL', 'AP'): 1,   # S × R = A
    ('AP', 'RL', 'SI'): -1,  # A × R = I (=-S)
    ('SI', 'AP', 'RL'): -1,  # S × A = L (=-R)
    ('RL', 'SI', 'AP'): -1,  # R × S = P (=-A)
}

# Unit vectors for each direction
_DIRECTION_VECTORS = {
    'R': np.array([1, 0, 0]),
    'L': np.array([-1, 0, 0]),
    'A': np.array([0, 1, 0]),
    'P': np.array([0, -1, 0]),
    'S': np.array([0, 0, 1]),
    'I': np.array([0, 0, -1]),
}


def _get_handedness(orientation: str) -> int:
    """Determine if an orientation code is right-handed or left-handed.
    
    Right-handed: axis0 × axis1 = axis2 (e.g., RAS, PRS, LSA)
    Left-handed: axis0 × axis1 = -axis2 (e.g., PSR, RAI)
    
    Args:
        orientation: 3-letter orientation code (e.g., 'RAS', 'PSR')
        
    Returns:
        +1 for right-handed, -1 for left-handed
    """
    v0 = _DIRECTION_VECTORS[orientation[0]]
    v1 = _DIRECTION_VECTORS[orientation[1]]
    v2 = _DIRECTION_VECTORS[orientation[2]]
    
    cross = np.cross(v0, v1)
    
    if np.allclose(cross, v2):
        return 1  # right-handed
    elif np.allclose(cross, -v2):
        return -1  # left-handed
    else:
        raise ValueError(f"Invalid orientation code: {orientation}")


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
        >>> # RAS: given A(1) and S(2), determine R at position 0
        >>> _determine_third_orientation(1, 2, 0, 'A', 'S', 'AP', 'SI')
        'R'
        
        >>> # PRS: given R(1) and S(2), determine P at position 0
        >>> _determine_third_orientation(1, 2, 0, 'R', 'S', 'RL', 'SI')
        'P'
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
    
    # Determine which type of direction we need to return
    all_types = {'AP', 'SI', 'RL'}
    dir3_type = (all_types - {dir1_type, dir2_type}).pop()
    
    # Get cross product coefficient for (type at dir3_idx, type at dir1_idx, type at dir2_idx)
    # This accounts for the natural cross product direction between axis types
    coeff = _CROSS_COEFFS.get((dir3_type, dir1_type, dir2_type), 1)
    
    # Calculate third direction sign using the right-hand rule:
    # For a right-handed coordinate system: axis0 × axis1 = axis2
    # Combined formula: dir3_sign = parity × coeff × dir2_sign × dir1_sign
    dir3_sign = parity * coeff * dir2_sign * dir1_sign
    
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
        real_A_is_actually_labeled_as: Where the real/physical Anterior is currently 
            labeled in the image. For example, 'L' means the brain's anterior appears 
            at the L-labeled position.
        real_S_is_actually_labeled_as: Where the real/physical Superior is currently 
            labeled in the image. For example, 'A' means the brain's superior appears 
            at the A-labeled position.
        
    Returns:
        Corrected affine matrix (4x4 numpy array)
    
    Example:
        If original orientation is RAS but real A is at L and real S is at S:
        1. RAS means x+=R, y+=A, z+=S
        2. From parameters: real A at L → real P at R; real S at S → real I at I
        3. Build target: x+ has real P → P; z+ has real S → S; y+ = ? (right-hand rule)
        4. Right-hand rule: P × ? = S → ? = R
        5. Result: PRS
    """
    # Extract affine matrix if input is a nibabel image
    if isinstance(affine, nib.spatialimages.SpatialImage):
        affine_matrix = affine.affine.copy()
    else:
        affine_matrix = affine.copy()
    
    _OPPOSITES = {'R': 'L', 'L': 'R', 'A': 'P', 'P': 'A', 'S': 'I', 'I': 'S'}
    
    real_A_dir = real_A_is_actually_labeled_as.upper()
    real_S_dir = real_S_is_actually_labeled_as.upper()
    
    # Step 1: Get current orientation code (e.g., RAS → ['R', 'A', 'S'])
    current_axes = list(aff2axcodes(affine_matrix))
    current_orientation = "".join(current_axes)
    
    # Step 2: Build mapping of where each real direction is labeled
    # From the two parameters, we can deduce all six directions:
    #   real_A at X → real_P at opposite(X)
    #   real_S at Y → real_I at opposite(Y)
    #   real_R and real_L are determined by right-hand rule later
    real_P_dir = _OPPOSITES[real_A_dir]
    real_I_dir = _OPPOSITES[real_S_dir]
    
    # Step 3: For each axis position, determine the correct label
    # The rule: if real X is at position labeled Y, then position Y should become X
    target_axes = [None, None, None]
    
    # Place A/P: real A is at real_A_dir, real P is at real_P_dir
    for i, label in enumerate(current_axes):
        if label == real_A_dir or label == _OPPOSITES[real_A_dir]:
            # This position contains real A or real P
            if label == real_A_dir:
                target_axes[i] = 'A'
            else:
                target_axes[i] = 'P'
    
    # Place S/I: real S is at real_S_dir, real I is at real_I_dir
    for i, label in enumerate(current_axes):
        if label == real_S_dir or label == _OPPOSITES[real_S_dir]:
            # This position contains real S or real I
            if label == real_S_dir:
                target_axes[i] = 'S'
            else:
                target_axes[i] = 'I'
    
    # Step 4: Determine handedness of original orientation
    # We want to preserve the handedness after correction
    handedness = _get_handedness(current_orientation)
    
    # Step 5: Use right/left-hand rule for the third axis (R/L)
    # Find the position that's still None
    third_pos = target_axes.index(None)
    
    # Find A/P and S/I positions and directions
    ap_pos = None
    si_pos = None
    ap_dir = None
    si_dir = None
    for i, d in enumerate(target_axes):
        if d in ['A', 'P']:
            ap_pos, ap_dir = i, d
        elif d in ['S', 'I']:
            si_pos, si_dir = i, d
    
    # Determine R/L using right-hand rule first
    rl_dir = _determine_third_orientation(
        ap_pos, si_pos, third_pos, ap_dir, si_dir, 'AP', 'SI'
    )
    
    # If original is left-handed, flip the result to preserve handedness
    if handedness == -1:
        rl_dir = _OPPOSITES[rl_dir]
    
    target_axes[third_pos] = rl_dir
    
    target_orientation = "".join(target_axes)
    
    # Step 6: Find the n×90° rotation that achieves target orientation
    rotations_4x4 = _get_n90_rotations_4x4()
    
    for rot_4x4 in rotations_4x4:
        test_affine = rot_4x4 @ affine_matrix
        test_axes = list(aff2axcodes(test_affine))
        test_orientation = "".join(test_axes)
        
        if test_orientation == target_orientation:
            return test_affine
    
    raise ValueError(
        f"Could not find n×90° rotation to transform orientation "
        f"{current_orientation} to {target_orientation}. "
        f"This may indicate the mismatch parameters are incorrect."
    )


# ---------------------------------------------------------------------------
# NIfTI image padding / cropping utilities
# ---------------------------------------------------------------------------
# NOTE: preprocessing.py has similar inline padding logic (percentage-based)
# that could be refactored to use pad_image() below.

def pad_image(
    imagef: Union[str, Path],
    outputf: Union[str, Path],
    pad_left: Union[np.ndarray, list],
    pad_right: Optional[Union[np.ndarray, list]] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Zero-pad a NIfTI image and update the affine to keep physical coords consistent.

    Handles 3-D scalar images as well as higher-dimensional data (e.g. 4-D
    time-series or multi-component vector fields).  Only the first three
    (spatial) dimensions are padded.

    Args:
        imagef: Input NIfTI image path.
        outputf: Output path for the padded image.
        pad_left: Per-dimension left-side padding, shape ``(3,)``.
        pad_right: Per-dimension right-side padding, shape ``(3,)``.
            If *None*, symmetric padding is used (same as *pad_left*).
        logger: Optional logger instance.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    pad_left = np.asarray(pad_left, dtype=int)
    pad_right = np.asarray(pad_right, dtype=int) if pad_right is not None else pad_left.copy()

    img = nib.load(str(imagef))
    data = img.get_fdata()
    affine = img.affine.copy()
    header = img.header.copy()

    # Build pad_width — spatial dims get padding, extra dims (channels etc.) do not
    pad_width = [(int(l), int(r)) for l, r in zip(pad_left, pad_right)]
    for _ in range(len(data.shape) - 3):
        pad_width.append((0, 0))

    padded_data = np.pad(data, pad_width, mode='constant', constant_values=0)

    # Shift the affine origin so that the original voxels keep the same world coords
    pad_shift_world = affine[:3, :3] @ (-pad_left.astype(float))
    new_affine = affine.copy()
    new_affine[:3, 3] = affine[:3, 3] + pad_shift_world

    new_img = nib.Nifti1Image(padded_data.astype(data.dtype), new_affine, header)
    nib.save(new_img, str(outputf))

    logger.info(
        f"Padded image from {list(data.shape[:3])} to {list(padded_data.shape[:3])} "
        f"(left={list(pad_left)}, right={list(pad_right)})"
    )


def pad_image_to_min_size(
    imagef: Union[str, Path],
    min_size: int,
    outputf: Union[str, Path],
    logger: Optional[logging.Logger] = None,
) -> Optional[np.ndarray]:
    """Zero-pad a NIfTI image so every spatial dimension is >= *min_size*.

    Symmetric zero-padding is applied to each dimension that is smaller than
    *min_size*.  When the deficit is odd, the extra voxel goes to the right
    side.

    Args:
        imagef: Input NIfTI image path.
        min_size: Minimum required size for each spatial dimension.
        outputf: Output path for the padded image.  Only written when padding
            is actually needed.
        logger: Optional logger instance.

    Returns:
        Per-side **left** padding as ``np.ndarray`` of shape ``(3,)``, or
        *None* if all dimensions were already >= *min_size* (no file written).
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    img = nib.load(str(imagef))
    spatial_shape = np.array(img.shape[:3])

    if np.all(spatial_shape >= min_size):
        logger.debug(f"No padding needed: all dims {list(spatial_shape)} >= {min_size}")
        return None

    pad_total = np.maximum(min_size - spatial_shape, 0)
    pad_left = pad_total // 2
    pad_right = pad_total - pad_left

    pad_image(imagef, outputf, pad_left, pad_right, logger)

    return pad_left


def crop_image_to_original(
    imagef: Union[str, Path],
    ref_imagef: Union[str, Path],
    pad_left: np.ndarray,
    outputf: Union[str, Path],
    logger: Optional[logging.Logger] = None,
) -> None:
    """Crop a padded NIfTI image back to match a reference image's grid.

    Reverses the effect of :func:`pad_image_to_min_size` by slicing out the
    padded voxels and restoring the reference image's affine.  Works for both
    scalar images and multi-component vector fields (e.g. ANTs warp fields).

    In-place operation is supported (``imagef == outputf``).

    Args:
        imagef: Padded image to crop.
        ref_imagef: Original (unpadded) reference image — its shape and affine
            define the target grid.
        pad_left: Per-dimension left padding that was applied (returned by
            :func:`pad_image_to_min_size`).
        outputf: Output path for the cropped image.
        logger: Optional logger instance.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    img = nib.load(str(imagef))
    ref = nib.load(str(ref_imagef))

    # Force eager load so in-place overwrite is safe
    data = np.asarray(img.dataobj)
    ref_shape = ref.shape[:3]
    pad_left = np.asarray(pad_left, dtype=int)

    # Crop spatial dims; preserve any extra dims (vector components, time, …)
    slices = [slice(int(p), int(p) + int(s)) for p, s in zip(pad_left, ref_shape)]
    for _ in range(len(data.shape) - 3):
        slices.append(slice(None))

    cropped_data = data[tuple(slices)]

    # Preserve intent codes / data-type metadata from the padded image header,
    # but use the reference affine so the output matches the original grid.
    new_header = img.header.copy()
    cropped_img = nib.Nifti1Image(cropped_data, ref.affine, new_header)
    nib.save(cropped_img, str(outputf))

    logger.info(
        f"Cropped image from {list(data.shape[:3])} back to {list(cropped_data.shape[:3])}"
    )

