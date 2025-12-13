"""
N4 Bias Field Correction for MRI images.

Provides bias field correction and white matter intensity normalization
using SimpleITK's N4 algorithm.

Based on original N4_bias_correct.py from FastSurfer.
"""

# Copyright 2023 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import cast
import logging
import os

import numpy as np
import numpy.typing as npt
import SimpleITK as sitk

from ..io.image import read_image, write_image

logger = logging.getLogger(__name__)


def n4_bias_correction(
    image: sitk.Image,
    mask: sitk.Image | None = None,
    shrink_factor: int = 4,
    num_levels: int = 4,
    num_iterations: int = 50,
    convergence_threshold: float = 0.0,
) -> sitk.Image:
    """
    Perform N4 bias field correction on an image.

    Parameters
    ----------
    image : sitk.Image
        Input image (should be Float32)
    mask : sitk.Image, optional
        Brain mask. If None, all non-zero voxels are used.
    shrink_factor : int, default=4
        Factor to shrink image for faster processing
    num_levels : int, default=4
        Number of multi-resolution levels
    num_iterations : int, default=50
        Maximum iterations per level
    convergence_threshold : float, default=0.0
        Convergence threshold (0 = run all iterations)

    Returns
    -------
    sitk.Image
        Bias field corrected image
    """
    # Create mask if not provided
    if mask is not None:
        # Binarize mask
        mask = mask > 0
    else:
        # Default: all voxels >= 0
        mask = sitk.Abs(image) >= 0
        mask.CopyInformation(image)
        logger.debug("Using default mask (all voxels)")

    original_image = image

    # Subsample for speed
    if shrink_factor > 1:
        image = sitk.Shrink(image, [shrink_factor] * image.GetDimension())
        mask = sitk.Shrink(mask, [shrink_factor] * image.GetDimension())

    # Initialize corrector
    corrector = sitk.N4BiasFieldCorrectionImageFilter()
    corrector.SetMaximumNumberOfIterations([num_iterations] * num_levels)
    corrector.SetConvergenceThreshold(convergence_threshold)

    # Run correction
    sitk.ProcessObject.SetGlobalDefaultCoordinateTolerance(1e-04)
    corrector.Execute(image, mask)

    # Apply bias field to original (full resolution) image
    log_bias_field = corrector.GetLogBiasFieldAsImage(original_image)
    corrected_image = original_image / sitk.Exp(log_bias_field)

    return corrected_image


def normalize_intensity(
    image: sitk.Image,
    mask: sitk.Image | None,
    source_range: tuple[float, float],
    target_range: tuple[float, float],
) -> sitk.Image:
    """
    Normalize image intensity using linear mapping.

    Parameters
    ----------
    image : sitk.Image
        Input image
    mask : sitk.Image, optional
        Brain mask. Voxels inside mask are guaranteed to be > 0.
    source_range : tuple[float, float]
        Source intensity range (background, foreground)
    target_range : tuple[float, float]
        Target intensity range (background, foreground)

    Returns
    -------
    sitk.Image
        Normalized image
    """
    # Compute linear transformation: y = m * (x - src_bg) + tgt_bg
    m = (target_range[0] - target_range[1]) / (source_range[0] - source_range[1])
    logger.debug(f"Normalization slope: {m:.4f}")

    normalized = (image - source_range[0]) * m + target_range[0]

    if mask is not None:
        # Ensure normalized image is > 0 where mask is true
        correction_mask = cast(sitk.Image, (normalized < 1) & mask)
        return normalized + sitk.Cast(correction_mask, normalized.GetPixelID())
    
    return normalized


def normalize_wm_from_aseg(
    image: sitk.Image,
    mask: sitk.Image | None,
    aseg: sitk.Image,
    target_wm: float = 105.0,
    target_bg: float = 3.0,
) -> sitk.Image:
    """
    Normalize white matter intensity using aseg segmentation.

    Uses the left and right white matter labels (2 and 41) from
    the aseg to determine the source WM intensity.

    Parameters
    ----------
    image : sitk.Image
        Bias-corrected image
    mask : sitk.Image, optional
        Brain mask
    aseg : sitk.Image
        FreeSurfer aseg segmentation
    target_wm : float, default=105.0
        Target white matter intensity
    target_bg : float, default=3.0
        Target background intensity

    Returns
    -------
    sitk.Image
        Normalized image
    """
    img_array = sitk.GetArrayFromImage(image)
    aseg_array = sitk.GetArrayFromImage(aseg)

    # Left and Right White Matter labels
    wm_mask = (aseg_array == 2) | (aseg_array == 41)
    source_wm = np.mean(img_array[wm_mask]).item()
    
    # Background from 1st percentile
    source_bg = np.percentile(img_array.flat[::100], 1)

    logger.info(f"Source WM intensity: {source_wm:.2f}")
    logger.info(f"Source BG intensity: {source_bg:.2f}")

    return normalize_intensity(
        image, mask,
        (source_bg, source_wm),
        (target_bg, target_wm),
    )


def normalize_wm_from_centroid(
    image: sitk.Image,
    mask: sitk.Image | None,
    centroid: npt.ArrayLike,
    radius: float = 50.0,
    target_wm: float = 110.0,
    target_bg: float = 3.0,
) -> sitk.Image:
    """
    Normalize white matter intensity using a ball around a centroid.

    Uses the 90th percentile of intensities in a ball around the
    centroid to estimate WM intensity.

    Parameters
    ----------
    image : sitk.Image
        Bias-corrected image
    mask : sitk.Image, optional
        Brain mask
    centroid : array-like
        Center point in voxel coordinates
    radius : float, default=50.0
        Radius of the ball in voxels
    target_wm : float, default=110.0
        Target white matter intensity
    target_bg : float, default=3.0
        Target background intensity

    Returns
    -------
    sitk.Image
        Normalized image
    """
    centroid = np.asarray(centroid)
    img_size = image.GetSize()
    img_spacing = image.GetSpacing()

    logger.debug(f"Centroid: {centroid}")
    logger.debug(f"Image size: {img_size}")

    # Create distance map to centroid
    def get_distance_sq(axis: int) -> np.ndarray:
        ii = np.arange(img_size[2 - axis])
        for i in range(3):
            if i != axis:
                ii = np.expand_dims(ii, 0 if i < axis else -1)
        xx = img_spacing[axis] * (ii - centroid[axis])
        return xx * xx

    zz, yy, xx = map(get_distance_sq, range(3))
    distance_sq = xx + yy + zz
    ball_mask = distance_sq < radius * radius

    # Get intensities in ball
    img_array = sitk.GetArrayFromImage(image)
    source_bg, source_wm = np.percentile(img_array[ball_mask], [1, 90])

    logger.info(f"Source WM intensity (90th pct): {source_wm:.2f}")
    logger.info(f"Source BG intensity (1st pct): {source_bg:.2f}")

    return normalize_intensity(
        image, mask,
        (source_bg, source_wm),
        (target_bg, target_wm),
    )


def get_brain_centroid(mask: sitk.Image) -> np.ndarray:
    """
    Get the centroid of a brain mask.

    Parameters
    ----------
    mask : sitk.Image
        Binary brain mask

    Returns
    -------
    np.ndarray
        Centroid in voxel coordinates
    """
    label_stats = sitk.LabelShapeStatisticsImageFilter()
    label_stats.Execute(mask)
    centroid_world = label_stats.GetCentroid(1)
    centroid_voxel = mask.TransformPhysicalPointToIndex(centroid_world)
    
    logger.debug(f"Brain centroid (world): {centroid_world}")
    logger.debug(f"Brain centroid (voxel): {centroid_voxel}")
    
    return np.array(centroid_voxel)


def read_talairach_xfm(filename: Path | str) -> np.ndarray:
    """
    Read a Talairach transform (.xfm) file.

    Parameters
    ----------
    filename : Path or str
        Path to .xfm file

    Returns
    -------
    np.ndarray
        4x4 transformation matrix

    Raises
    ------
    ValueError
        If file format is invalid
    """
    with open(filename) as f:
        lines = f.readlines()

    try:
        # Find the linear transform header
        transform_iter = iter(lines)
        _ = next(ln for ln in transform_iter if ln.lower().startswith("linear_"))
        
        # Read the next 3 lines as the transform matrix
        transform_lines = [next(transform_iter) for _ in range(3)]
        tal_str = [ln.replace(";", " ") for ln in transform_lines]
        tal = np.genfromtxt(tal_str)
        tal = np.vstack([tal, [0, 0, 0, 1]])

        logger.debug(f"Read Talairach transform:\n{tal}")
        return tal

    except StopIteration:
        raise ValueError(f"Could not find 'Linear_' header in {filename}")
    except Exception as e:
        raise ValueError(f"Could not parse Talairach transform in {filename}") from e


def get_talairach_origin_voxel(
    talairach: npt.ArrayLike,
    image: sitk.Image,
) -> np.ndarray:
    """
    Get the Talairach origin in voxel coordinates.

    Parameters
    ----------
    talairach : array-like
        4x4 Talairach transformation matrix
    image : sitk.Image
        Reference image

    Returns
    -------
    np.ndarray
        Origin in voxel coordinates
    """
    tal_inv = np.linalg.inv(talairach)
    tal_origin = np.array(tal_inv[0:3, 3]).ravel()
    vox_origin = image.TransformPhysicalPointToIndex(tal_origin)
    
    logger.debug(f"Talairach origin (physical): {tal_origin}")
    logger.debug(f"Talairach origin (voxel): {vox_origin}")
    
    return np.array(vox_origin)


def bias_correct_and_normalize(
    input_path: Path,
    output_path: Path,
    mask_path: Path | None = None,
    aseg_path: Path | None = None,
    talairach_path: Path | None = None,
    shrink_factor: int = 4,
    num_levels: int = 4,
    num_iterations: int = 50,
    threads: int = 1,
) -> None:
    """
    High-level function to bias correct and normalize an image.

    This is the main entry point for bias correction, equivalent
    to calling the original N4_bias_correct.py script.

    Parameters
    ----------
    input_path : Path
        Input image path
    output_path : Path
        Output image path
    mask_path : Path, optional
        Brain mask path
    aseg_path : Path, optional
        Aseg segmentation for WM-based normalization
    talairach_path : Path, optional
        Talairach transform for centroid-based normalization
    shrink_factor : int, default=4
        N4 shrink factor
    num_levels : int, default=4
        N4 multi-resolution levels
    num_iterations : int, default=50
        N4 iterations per level
    threads : int, default=1
        Number of threads
    """
    # Set threads via SimpleITK API
    sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(threads)
    
    # Also set environment variables to ensure ITK/OpenMP respects the thread limit
    # This is critical because ITK may check environment variables before API settings
    # and some operations may spawn subprocesses that don't inherit API settings
    from ..utils.threading import set_numerical_threads
    set_numerical_threads(threads, include_itk=True)

    # Read input
    logger.info(f"Reading input: {input_path}")
    image, header = read_image(input_path, sitk.sitkFloat32, with_header=True)

    # Read mask
    mask = None
    if mask_path:
        logger.info(f"Reading mask: {mask_path}")
        mask = read_image(mask_path, sitk.sitkUInt8)
        mask = cast(sitk.Image, mask > 0)

    # Run N4 correction
    logger.info("Running N4 bias correction...")
    corrected = n4_bias_correction(
        image, mask,
        shrink_factor=shrink_factor,
        num_levels=num_levels,
        num_iterations=num_iterations,
    )

    # Normalize WM intensity
    if aseg_path:
        logger.info("Normalizing using aseg segmentation...")
        aseg = read_image(aseg_path)
        corrected = normalize_wm_from_aseg(corrected, mask, aseg, target_wm=105.0)
    elif talairach_path:
        logger.info("Normalizing using Talairach centroid...")
        tal = read_talairach_xfm(talairach_path)
        centroid = get_talairach_origin_voxel(tal, image)
        corrected = normalize_wm_from_centroid(corrected, mask, centroid)
    elif mask is not None:
        logger.info("Normalizing using mask centroid...")
        centroid = get_brain_centroid(mask)
        corrected = normalize_wm_from_centroid(corrected, mask, centroid)
    else:
        logger.warning("No normalization performed (no aseg, talairach, or mask)")

    # Convert to UCHAR and save
    logger.info("Converting to UCHAR...")
    corrected = sitk.Cast(
        sitk.Clamp(corrected, lowerBound=0, upperBound=255),
        sitk.sitkUInt8,
    )

    logger.info(f"Writing output: {output_path}")
    write_image(corrected, output_path, header)


__all__ = [
    "n4_bias_correction",
    "normalize_intensity",
    "normalize_wm_from_aseg",
    "normalize_wm_from_centroid",
    "get_brain_centroid",
    "read_talairach_xfm",
    "get_talairach_origin_voxel",
    "bias_correct_and_normalize",
]

