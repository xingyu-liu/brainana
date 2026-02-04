"""
Image I/O utilities for FastSurfer surface reconstruction.

Handles reading and writing of medical images in various formats
(MGZ, NIfTI) with conversions between nibabel and SimpleITK.

Based on original image_io.py from FastSurfer.
"""

# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Any, overload
import logging

import nibabel as nib
import numpy as np
import SimpleITK as sitk
from nibabel.freesurfer.mghformat import MGHHeader

logger = logging.getLogger(__name__)


def mgh_from_sitk(
    sitk_img: sitk.Image,
    orig_mgh_header: MGHHeader | None = None,
) -> nib.MGHImage:
    """
    Convert SimpleITK image to nibabel MGH image.

    Parameters
    ----------
    sitk_img : sitk.Image
        SimpleITK image to convert
    orig_mgh_header : MGHHeader, optional
        Original MGH header to preserve metadata

    Returns
    -------
    nib.MGHImage
        Converted MGH image
    """
    if orig_mgh_header:
        h1 = MGHHeader.from_header(orig_mgh_header)
    else:
        h1 = MGHHeader()
    
    # Get voxel sizes and set zooms (=delta in h1 header)
    spacing = sitk_img.GetSpacing()
    h1.set_zooms(np.asarray(spacing))
    
    # Get direction cosines from sitk image, reshape to 3x3 Matrix
    direction = np.asarray(sitk_img.GetDirection()).reshape(3, 3, order="F") * [
        -1, -1, 1,
    ]
    h1["Mdc"] = direction
    
    # Compute affine
    origin = np.asarray(sitk_img.GetOrigin()).reshape(3, 1) * [[-1], [-1], [1]]
    affine = np.vstack([np.hstack([h1["Mdc"].T * h1["delta"], origin]), [0, 0, 0, 1]])
    
    # Get dims and calculate new image center in world coords
    dims = np.array(sitk_img.GetSize())
    if dims.size == 3:
        dims = np.hstack((dims, [1]))
    h1["dims"] = dims
    h1["Pxyz_c"] = affine.dot(np.hstack((dims[:3] / 2.0, [1])))[:3]
    
    # Swap axes as data is stored differently between sITK and Nibabel
    data = np.swapaxes(sitk.GetArrayFromImage(sitk_img), 0, 2)
    
    # Assemble MGHImage from header, image data and affine
    mgh_img = nib.MGHImage(data, affine, h1)
    return mgh_img


def sitk_from_mgh(img: nib.MGHImage) -> sitk.Image:
    """
    Convert nibabel MGH image to SimpleITK image.

    Parameters
    ----------
    img : nib.MGHImage
        MGH image to convert

    Returns
    -------
    sitk.Image
        Converted SimpleITK image
    """
    # Reorder data as structure differs between nibabel and sITK
    data = np.swapaxes(np.asanyarray(img.dataobj), 0, 2)
    
    # sitk can only create image with system native endianness
    if not data.dtype.isnative:
        data = data.byteswap().view(data.dtype.newbyteorder())
    
    # Create image from array
    img_sitk = sitk.GetImageFromArray(data)
    
    # Get direction from MDC, need to change sign of dim 0 and 1
    direction = img.header["Mdc"] * [-1, -1, 1]
    img_sitk.SetDirection(direction.ravel(order="F"))
    
    # Set voxel sizes
    img_sitk.SetSpacing(np.array(img.header.get_zooms()).tolist())
    
    # Get origin from affine, needs to change sign of dim 0 and 1
    origin = img.affine[:3, 3:] * [[-1], [-1], [1]]
    img_sitk.SetOrigin(origin.ravel())
    
    return img_sitk


@overload
def read_image(
    filename: str | Path,
    dtype: Any | None = None,
    *,
    with_header: bool = False,
) -> sitk.Image:
    ...


@overload
def read_image(
    filename: str | Path,
    dtype: Any | None = None,
    *,
    with_header: bool = True,
) -> tuple[sitk.Image, MGHHeader | None]:
    ...


def read_image(
    filename: str | Path,
    dtype: Any | None = None,
    *,
    with_header: bool = False,
) -> sitk.Image | tuple[sitk.Image, MGHHeader | None]:
    """
    Read a medical image file.

    Supports MGZ (FreeSurfer), NIfTI (.nii, .nii.gz) formats.

    Parameters
    ----------
    filename : str or Path
        Path to the image file
    dtype : Any, optional
        SimpleITK pixel type to cast to (e.g., sitk.sitkFloat32)
    with_header : bool, default=False
        If True, also return the MGH header (for MGZ files)

    Returns
    -------
    sitk.Image
        The loaded image
    MGHHeader or None
        The MGH header (only if with_header=True and file is MGZ)

    Raises
    ------
    ValueError
        If the image format is not supported
    """
    filename = Path(filename)
    # Get actual file extension (last suffix or last two for .nii.gz)
    suffixes = filename.suffixes
    if len(suffixes) >= 2 and "".join(suffixes[-2:]).lower() == ".nii.gz":
        suffix = ".nii.gz"
    elif len(suffixes) >= 1:
        suffix = suffixes[-1].lower()
    else:
        suffix = ""
    header = None

    if suffix in (".nii.gz", ".nii"):
        logger.debug(f"Reading NIfTI image: {filename}")
        if dtype:
            itkimage = sitk.ReadImage(str(filename), dtype)
        else:
            itkimage = sitk.ReadImage(str(filename))
    elif suffix == ".mgz":
        logger.debug(f"Reading MGZ image: {filename}")
        image = nib.load(filename)
        header = image.header
        itkimage = sitk_from_mgh(image)
        if dtype:
            itkimage = sitk.Cast(itkimage, dtype)
    else:
        raise ValueError(
            f"Unsupported image format: {suffix}. "
            "Supported formats: .mgz, .nii, .nii.gz"
        )

    if with_header:
        return itkimage, header
    else:
        return itkimage


def write_image(
    img: sitk.Image,
    filename: str | Path,
    header: MGHHeader | None = None,
) -> None:
    """
    Write a medical image to file.

    Supports MGZ (FreeSurfer), NIfTI (.nii, .nii.gz) formats.

    Parameters
    ----------
    img : sitk.Image
        Image to write
    filename : str or Path
        Output file path
    header : MGHHeader, optional
        MGH header to use (for MGZ output)

    Raises
    ------
    ValueError
        If the image format is not supported
    """
    filename = Path(filename)
    # Get actual file extension (last suffix or last two for .nii.gz)
    suffixes = filename.suffixes
    if len(suffixes) >= 2 and "".join(suffixes[-2:]).lower() == ".nii.gz":
        suffix = ".nii.gz"
    elif len(suffixes) >= 1:
        suffix = suffixes[-1].lower()
    else:
        suffix = ""

    # Ensure parent directory exists
    filename.parent.mkdir(parents=True, exist_ok=True)

    if suffix in (".nii.gz", ".nii"):
        logger.debug(f"Writing NIfTI image: {filename}")
        sitk.WriteImage(img, str(filename))
    elif suffix == ".mgz":
        logger.debug(f"Writing MGZ image: {filename}")
        mgh_image = mgh_from_sitk(img, header)
        nib.save(mgh_image, filename)
    else:
        raise ValueError(
            f"Unsupported image format: {suffix}. "
            "Supported formats: .mgz, .nii, .nii.gz"
        )


# Backwards compatibility aliases
readITKimage = read_image
writeITKimage = write_image


__all__ = [
    "read_image",
    "write_image",
    "mgh_from_sitk",
    "sitk_from_mgh",
    # Backwards compatibility
    "readITKimage",
    "writeITKimage",
]

