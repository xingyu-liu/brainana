"""
I/O utilities for nhp_skullstrip_nn.
"""

import os
import torch
import numpy as np
from typing import Union, Tuple, Optional
import nibabel as nib
from pathlib import Path
import pickle
import torch.nn as nn

from .log import get_logger
from .gpu import get_device


def write_nifti(
    data: np.ndarray, 
    affine: np.ndarray, 
    header: nib.Nifti1Header,
    output_path: Union[str, Path],
    shape: Optional[Tuple[int, ...]] = None, 
) -> None:
    """
    Save a numpy array as a NIfTI file with the given affine and shape.
    
    Args:
        data: Numpy array containing the image data
        affine: Affine transformation matrix
        shape: Original shape to crop the data to
        output_path: Path where to save the NIfTI file
        
    Raises:
        ValueError: If data dimensions don't match expected shape
        IOError: If file cannot be written
    """
    output_path = Path(output_path)
    
    # Ensure data fits within specified shape
    if shape is not None:
        if len(shape) != len(data.shape):
            raise ValueError(f"Shape mismatch: data has {len(data.shape)} dimensions, "
                            f"but shape specifies {len(shape)} dimensions")
        
        # Crop data to specified shape
        slices = tuple(slice(0, min(data.shape[i], shape[i])) for i in range(len(shape)))
        data_cropped = data[slices]
    else:
        data_cropped = data
    
    # Create and save NIfTI image
    try:
        img = nib.Nifti1Image(data_cropped, affine, header)
        img.to_filename(str(output_path))
    except Exception as e:
        raise IOError(f"Failed to write NIfTI file to {output_path}: {e}")


def load_nifti(
    file_path: Union[str, Path],
    normalize: bool = True,
    dtype: np.dtype = np.float32
) -> Tuple[np.ndarray, np.ndarray, Tuple[int, ...]]:
    """
    Load a NIfTI file and return data, affine, and shape.
    
    Args:
        file_path: Path to the NIfTI file
        normalize: Whether to apply 0-1 normalization
        dtype: Data type for the output array
        
    Returns:
        Tuple of (data, affine, shape)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be loaded
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"NIfTI file not found: {file_path}")
    
    try:
        nifti = nib.load(str(file_path))
        data = np.array(nifti.get_fdata(), dtype=dtype)
        
        if normalize and data.max() > data.min():
            data = (data - data.min()) / (data.max() - data.min())
        
        return data, nifti.affine, nifti.shape
        
    except Exception as e:
        raise IOError(f"Failed to load NIfTI file {file_path}: {e}")


def validate_nifti_compatibility(
    file1_path: Union[str, Path], 
    file2_path: Union[str, Path]
) -> bool:
    """
    Check if two NIfTI files have compatible shapes and affines.
    
    Args:
        file1_path: Path to first NIfTI file
        file2_path: Path to second NIfTI file
        
    Returns:
        True if files are compatible, False otherwise
    """
    try:
        _, affine1, shape1 = load_nifti(file1_path, normalize=False)
        _, affine2, shape2 = load_nifti(file2_path, normalize=False)
        
        shape_compatible = shape1 == shape2
        affine_compatible = np.allclose(affine1, affine2, atol=1e-6)
        
        return shape_compatible and affine_compatible
        
    except (FileNotFoundError, IOError):
        return False


def save_nifti(data: np.ndarray, 
               affine: np.ndarray, 
               header: nib.Nifti1Header,
               file_path: Union[str, Path],
               shape: Optional[Tuple[int, ...]] = None) -> None:
    """
    Save data as a NIfTI file.
    
    Args:
        data: Data array to save
        affine: Affine transformation matrix
        header: NIfTI header
        shape: Original shape to crop the data to
        file_path: Output file path
    """
    if shape is not None:
        if len(shape) != len(data.shape):
            raise ValueError(f"Shape mismatch: data has {len(data.shape)} dimensions, "
                            f"but shape specifies {len(shape)} dimensions")
        
    nifti = nib.Nifti1Image(data, affine, header)
    nib.save(nifti, str(file_path))


def load_pickle(file_path: Union[str, Path]) -> object:
    """Load data from a pickle file."""
    with open(str(file_path), 'rb') as f:
        return pickle.load(f)


def save_pickle(data: object, file_path: Union[str, Path]) -> None:
    """Save data to a pickle file."""
    with open(str(file_path), 'wb') as f:
        pickle.dump(data, f)