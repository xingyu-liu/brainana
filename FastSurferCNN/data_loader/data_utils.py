# Copyright 2023 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# IMPORTS
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import nibabel as nib
import numpy as np
import pandas as pd
import scipy.ndimage.morphology as morphology
import torch
from nibabel.filebasedimages import FileBasedHeader as _Header
from numpy import typing as npt
from scipy.ndimage import (
    binary_closing,
    binary_erosion,
    filters,
    generate_binary_structure,
    uniform_filter,
)
from skimage.measure import label, regionprops

from FastSurferCNN.data_loader.conform import check_affine_in_nifti, conform, is_conform
from FastSurferCNN.utils import logging

##
# Global Vars
##
SUPPORTED_OUTPUT_FILE_FORMATS = ("mgz", "nii", "nii.gz")
LOGGER = logging.getLogger(__name__)

##
# Helper Functions
##


# Conform an MRI brain image to UCHAR, RAS orientation, and 1mm or minimal isotropic
# voxels
def load_and_conform_image(
        img_filename: Path | str,
        order: int = 1,
        logger: logging.Logger = LOGGER,
        **conform_kwargs,
) -> tuple[_Header, np.ndarray, np.ndarray]:
    """
    Load MRI image and conform it to UCHAR, RAS orientation and 1mm or minimum isotropic
    voxels size.

    Only, if it does not already have this format.

    Parameters
    ----------
    img_filename : Path, str
        Path and name of volume to read.
    order : int, default=1
        Interpolation order for image conformation (0=nearest, 1=linear(default), 2=quadratic, 3=cubic).
    logger : logging.Logger, default=<local logger>
        Logger to write output to (default = STDOUT).
    **conform_kwargs
        Additional parameters to conform and is_conform.

    Returns
    -------
    nibabel.Header header_info
        Header information of the conformed image.
    numpy.ndarray affine_info
        Affine information of the conformed image.
    numpy.ndarray orig_data
        Conformed image data.

    Raises
    ------
    RuntimeError
        If input has multiple input frames or inconsistent nifti headers.
    """
    img_file = Path(img_filename)
    orig = cast(nib.analyze.SpatialImage, nib.load(img_file))
    # is_conform and conform accept numeric values and the string 'min' instead of the bool value
    if not is_conform(orig, **conform_kwargs):

        logger.info("Conforming image to UCHAR, RAS orientation, and minimum isotropic voxels")

        if len(orig.shape) > 3 and orig.shape[3] != 1:
            raise RuntimeError(f"Multiple input frames ({orig.shape[3]}) not supported!")

        # Check affine if image is nifti image
        if img_file.suffix == ".nii" or img_file.suffixes[-2:] == [".nii", ".gz"]:
            if not check_affine_in_nifti(cast(nib.nifti1.Nifti1Image | nib.nifti2.Nifti1Image, orig), logger=logger):
                raise RuntimeError("Inconsistency in nifti-header!")

        # conform
        orig = conform(orig, order=order, **conform_kwargs)

    # Return header and affine information
    return orig.header, orig.affine, np.asanyarray(orig.dataobj)


def load_image(
        file: str | Path,
        name: str = "image",
        **kwargs,
) -> tuple[nib.analyze.SpatialImage, np.ndarray]:
    """
    Load file 'file' with nibabel, including all data.

    Parameters
    ----------
    file : Path, str
        Path to the file to load.
    name : str, default="image"
        Name of the file (optional), only effects error messages.
    **kwargs :
        Additional keyword arguments.

    Returns
    -------
    Tuple[nib.analyze.SpatialImage, np.ndarray]
        The nibabel image object and a numpy array of the data.

    Raises
    ------
    IOError
        Failed loading the file
        nibabel releases the GIL, so the following is a parallel example.
        {
        >>> from concurrent.futures import ThreadPoolExecutor
        >>> with ThreadPoolExecutor() as pool:
        >>>     future1 = pool.submit(load_image, filename1)
        >>>     future2 = pool.submit(load_image, filename2)
        >>>     image, data = future1.result()
        >>>     image2, data2 = future2.result()
        }
    """
    try:
        img = cast(nib.analyze.SpatialImage, nib.load(file, **kwargs))
    except (OSError, FileNotFoundError) as e:
        raise OSError(f"Failed loading the {name} '{file}' with error: {e.args[0]}") from e
    return img, np.asarray(img.dataobj)


def load_maybe_conform(
        file: Path | str,
        alt_file: Path | str,
        **conform_kwargs,
) -> tuple[Path, nib.analyze.SpatialImage, np.ndarray]:
    """
    Load an image by file, check whether it is conformed to vox_size and conform to
    vox_size if it is not.

    Parameters
    ----------
    file : Path, str
        Path to the file to load.
    alt_file : Path, str
        Alternative file to interpolate from.
    **conform_kwargs
        Additional parameters to conform and is_conform.

    Returns
    -------
    Path
        The path to the file.
    nib.analyze.SpatialImage
        The file container object including the corrected header.
    np.ndarray
        The data loaded from the file.

    See Also
    --------
    FastSurferCNN.data_loader.conform.conform
        For additional parameters supported via `conform_kwargs`.
    """
    file = Path(file)
    alt_file = Path(alt_file)
    conform_kwargs_is_conform = dict(conform_kwargs.items())
    del conform_kwargs_is_conform["order"]

    _is_conform, img = False, None
    if file.is_file():
        # see if the file is 1mm
        img = cast(nib.analyze.SpatialImage, nib.load(file))
        # is_conform only needs the header, not the data
        _is_conform = is_conform(img, **conform_kwargs_is_conform, verbose=False, vox_eps=0.1)

    if _is_conform:
        # calling np.asarray here, forces the load of img.dataobj into memory
        # (which is parallel with other operations, if done here)
        data = np.asarray(img.dataobj)
        dst_file = file
    else:
        # the image is not conformed to 1mm, do this now.
        fileext = [ext for ext in SUPPORTED_OUTPUT_FILE_FORMATS if file.name.endswith("." + ext)]
        if len(fileext) != 1:
            raise RuntimeError(
                f"Invalid file extension of conf_name: {file}, must be one of {SUPPORTED_OUTPUT_FILE_FORMATS}."
            )
        file_no_fileext = str(file)[:-len(fileext[0]) - 1]
        vox_size = conform_kwargs.get("vox_size", 1.0)
        vox_suffix = ".min" if vox_size == "min" else f".{str(vox_size).replace('.', '')}mm"
        if not file_no_fileext.endswith(vox_suffix):
            file_no_fileext += vox_suffix
        # if the orig file is neither absolute nor in the subject path, use the conformed file
        src_file = alt_file if alt_file.is_file() else file
        if not alt_file.is_file():
            LOGGER.warning(
                f"No valid alternative file (e.g. orig, here: {alt_file}) was given to interpolate from, so we might "
                f"lose quality due to multiple chained interpolations. "
            )

        dst_file = Path(file_no_fileext + "." + fileext[0])
        # conform to 1mm
        header, affine, data = load_and_conform_image(
            src_file, logger=logging.getLogger(__name__ + ".conform"), **conform_kwargs,
        )

        # after conforming, save the conformed file
        save_image(header, affine, data, dst_file)
        img = nib.MGHImage(data, affine, header)
    return dst_file, img, data


# Save image routine
def save_image(
        header_info: _Header,
        affine_info: npt.NDArray[float],
        img_array: np.ndarray,
        save_as: str | Path,
        dtype: npt.DTypeLike | None = None
) -> None:
    """
    Save an image (nibabel MGHImage), according to the desired output file format.

    Supported formats are defined in supported_output_file_formats. Saves predictions to save_as.

    Parameters
    ----------
    header_info : _Header
        Image header information.
    affine_info : npt.NDArray[float]
        Image affine information.
    img_array : np.ndarray
        An array containing image data.
    save_as : Path, str
        Name under which to save prediction; this determines output file format.
    dtype : npt.DTypeLike, optional
        Image array type; if provided, the image object is explicitly set to match this type.
    """
    save_as = Path(save_as)
    valid_ext = save_as.suffix[1:] in SUPPORTED_OUTPUT_FILE_FORMATS or save_as.suffixes[-2:] == [".nii", ".gz"]
    assert valid_ext, f"Output filename does not contain a supported file format {SUPPORTED_OUTPUT_FILE_FORMATS}!"

    mgh_img = None
    if save_as.suffix == ".mgz":
        mgh_img = nib.MGHImage(img_array, affine_info, header_info)
    elif save_as.suffix == ".nii" or save_as.suffixes[-2:] == [".nii", ".gz"]:
        mgh_img = nib.nifti1.Nifti1Pair(img_array, affine_info, header_info)

    if dtype is not None:
        mgh_img.set_data_dtype(dtype)

    if save_as.suffix in (".mgz", ".nii"):
        nib.save(mgh_img, save_as)
    elif save_as.suffixes[-2:] == [".nii", ".gz"]:
        # For correct outputs, nii.gz files should be saved using the nifti1
        # sub-module's save():
        nib.nifti1.save(mgh_img, str(save_as))


# Transformation for mapping
def transform_axial(
        vol: npt.NDArray,
        coronal2axial: bool = True
) -> np.ndarray:
    """
    Transform volume into Axial axis and back.

    Parameters
    ----------
    vol : npt.NDArray
        Image volume to transform.
    coronal2axial : bool
        Transform from coronal to axial = True (default).

    Returns
    -------
    np.ndarray
        Transformed image.
    """
    if coronal2axial:
        return np.moveaxis(vol, [0, 1, 2], [1, 2, 0])
    else:
        return np.moveaxis(vol, [0, 1, 2], [2, 0, 1])


def transform_sagittal(
        vol: npt.NDArray,
        coronal2sagittal: bool = True
) -> np.ndarray:
    """
    Transform volume into Sagittal axis and back.

    Parameters
    ----------
    vol : npt.NDArray
        Image volume to transform.
    coronal2sagittal : bool
        Transform from coronal to sagittal = True (default).

    Returns
    -------
    np.ndarray:
        Transformed image.
    """
    if coronal2sagittal:
        return np.moveaxis(vol, [0, 1, 2], [2, 1, 0])
    else:
        return np.moveaxis(vol, [0, 1, 2], [2, 1, 0])


# Thick slice generator (for eval) and blank slices filter (for training)
def get_thick_slices(
        img_data: npt.NDArray,
        slice_thickness: int = 3
) -> np.ndarray:
    """
    Extract thick slices from the image.

    Feed slice_thickness preceding and succeeding slices to network,
    label only middle one.

    Parameters
    ----------
    img_data : npt.NDArray
        3D MRI image read in with nibabel.
    slice_thickness : int
        Number of slices to stack on top and below slice of interest (default=3).

    Returns
    -------
    np.ndarray
        Image data with the thick slices of the n-th axis appended into the n+1-th axis.
    """
    img_data_pad = np.pad(
        img_data, ((0, 0), (0, 0), (slice_thickness, slice_thickness)), mode="edge"
    )
    from numpy.lib.stride_tricks import sliding_window_view

    # sliding_window_view will automatically create thick slices through a sliding window, but as this in only a view,
    # less memory copies are required
    return sliding_window_view(img_data_pad, 2 * slice_thickness + 1, axis=2)


def filter_blank_slices_thick(
        img_vol: npt.NDArray,
        label_vol: npt.NDArray,
        weight_vol: npt.NDArray,
        threshold: int = 50
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Filter blank slices from the volume using the label volume.

    Parameters
    ----------
    img_vol : npt.NDArray
        Orig image volume.
    label_vol : npt.NDArray
        Label images (ground truth).
    weight_vol : npt.NDArray
        Weight corresponding to labels.
    threshold : int
        Threshold for number of pixels needed to keep slice (below = dropped). (Default value = 50).

    Returns
    -------
    filtered img_vol : np.ndarray
        Image volume with blank slices removed.
    label_vol : np.ndarray
        Label volume with blank slices removed.
    weight_vol : np.ndarray
        Weight volume with blank slices removed.
    """
    # Get indices of all slices with more than threshold labels/pixels
    select_slices = np.sum(label_vol, axis=(0, 1)) > threshold

    # Retain only slices with more than threshold labels/pixels
    img_vol = img_vol[:, :, select_slices, :]
    label_vol = label_vol[:, :, select_slices]
    weight_vol = weight_vol[:, :, select_slices]

    return img_vol, label_vol, weight_vol


# weight map generator
def create_weight_mask(
        mapped_aseg: npt.NDArray,
        max_weight: int = 5,
        max_edge_weight: int = 5,
        max_hires_weight: int | None = None,
        mean_filter: bool = False,
        cortex_mask: bool = True,
        gradient: bool = True,
        cortex_labels: set | None = None,
        verbose: bool = False
) -> np.ndarray:
    """
    Create weighted mask with multiple weighting strategies.
    
    Weight components:
    1. Base weights: Median frequency balancing (addresses class imbalance)
    2. Gradient weights: Edge detection (ALL label boundaries including subcortical)
    3. High-res weights: Challenging cortical regions (narrow sulci, thin gyri)
    4. Cortex border weights: Outer cortical boundary (pial surface)
    
    Note: Deep nuclei and subcortical structures are weighted through gradient (edge) weights.
          The cortex-specific masks only apply to cortical labels.

    Parameters
    ----------
    mapped_aseg : np.ndarray
        Segmentation to create weight mask from.
    max_weight : int
        Maximal weight on median frequency balancing (cap at this value). Default: 5.
    max_edge_weight : int
        Maximal weight on gradient (cap at this value). Applies to ALL boundaries. Default: 5.
    max_hires_weight : int
        Maximal weight on narrow cortical regions (cap at this value). Default: None.
    mean_filter : bool
        Flag to add mean_filter smoothing. Default: False.
    cortex_mask : bool
        Flag to create outer cortical boundary weight mask. Default: True.
    gradient : bool
        Flag to create gradient weight mask for all boundaries. Default: True.
    cortex_labels : set
        Explicit set of cortical label IDs from atlas metadata (e.g., ARM2, ARM3).
        Required for cortex-specific weight masks.

    Returns
    -------
    np.ndarray
        Weight mask for training.
    """
    unique, counts = np.unique(mapped_aseg, return_counts=True)

    # Median Frequency Balancing
    weights_per_label = np.median(counts) / counts
    weights_per_label[weights_per_label > max_weight] = max_weight
    
    # Create full weight array indexed by label value (not by position in unique array)
    # This is necessary because we'll index it using mapped_aseg values directly
    max_label = int(np.max(unique))
    class_wise_weights = np.zeros(max_label + 1, dtype=np.float32)
    class_wise_weights[unique.astype(int)] = weights_per_label
    
    (h, w, d) = mapped_aseg.shape
    weights_mask = np.reshape(class_wise_weights[mapped_aseg.ravel().astype(int)], (h, w, d))

    # Gradient Weighting
    if gradient:
        (gx, gy, gz) = np.gradient(mapped_aseg)
        grad_weight = max_edge_weight * np.asarray(
            np.power(np.power(gx, 2) + np.power(gy, 2) + np.power(gz, 2), 0.5) > 0,
            dtype="float",
        )

        weights_mask += grad_weight

    if max_hires_weight is not None and cortex_labels is not None:
        # High-resolution weighting for challenging cortical structures
        if verbose:
            print(f"  Adding narrow cortical region mask (weight={max_hires_weight}):")
        mask1 = deep_sulci_and_wm_strand_mask(
            mapped_aseg, structure=np.ones((3, 3, 3)), cortex_labels=cortex_labels, verbose=verbose
        )
        weights_mask += mask1 * max_hires_weight

        if cortex_mask:
            if verbose:
                print(f"  Adding outer cortical boundary mask (weight={max_hires_weight // 2}):")
            mask2 = cortex_border_mask(
                mapped_aseg, structure=np.ones((3, 3, 3)), cortex_labels=cortex_labels, verbose=verbose
            )
            weights_mask += mask2 * (max_hires_weight) // 2

    if mean_filter:
        weights_mask = uniform_filter(weights_mask, size=3)

    return weights_mask


def cortex_border_mask(
        label: npt.NDArray,
        structure: npt.NDArray,
        cortex_labels: set,
        verbose: bool = False
) -> np.ndarray:
    """
    Create a mask of the outer cortical boundary (pial surface region).
    
    This identifies the outermost layer of cortical gray matter, which is the
    boundary between cortex and CSF/meninges. This boundary is critical for:
    - Accurate cortical thickness measurements
    - Cortical surface reconstruction
    - Distinguishing cortex from CSF
    
    Note: This is about CORTICAL boundaries, not subcortical structures (deep nuclei).
    Deep nuclei boundaries (e.g., thalamus-WM) are handled by gradient weighting.

    Parameters
    ----------
    label : npt.NDArray
        Ground truth labels.
    structure : npt.NDArray
        Structuring element to erode with.
    cortex_labels : set
        Explicit set of cortical label IDs from atlas metadata (e.g., ARM2, ARM3).
    verbose : bool
        Print statistics about detected boundaries.

    Returns
    -------
    np.ndarray
        Binary mask of the outer cortical boundary (pial surface region).
    """
    # Create binary brainmask, erode it, and find the difference (outer layer)
    bm = np.clip(label, a_max=1, a_min=0)
    eroded = binary_erosion(bm, structure=structure)
    diff_im = np.logical_xor(eroded, bm)

    # Keep only the outer layer that belongs to cortical labels
    cortex_mask = np.isin(label, list(cortex_labels))
    diff_im[~cortex_mask] = 0
    
    # Print readable statistics
    num_detected = np.sum(diff_im)
    if verbose:
        total_voxels = diff_im.size
        percent = 100 * num_detected / total_voxels if total_voxels > 0 else 0
        print(f"  → Outer cortical boundary: {num_detected:,} voxels ({percent:.2f}% of volume)")
        print(f"     (pial surface region where cortex meets CSF)")
    
    return diff_im


def deep_sulci_and_wm_strand_mask(
        volume: npt.NDArray,
        structure: npt.NDArray,
        cortex_labels: set,
        iteration: int = 1,
        verbose: bool = False
) -> np.ndarray:
    """
    Get a binary mask of narrow/thin cortical regions (deep sulci and intervening white matter).
    
    This function identifies challenging-to-segment cortical structures:
    - Deep cortical sulci (narrow folds in the cortex)
    - Thin gyral tips (narrow cortical protrusions)
    - Small white matter regions between closely packed cortical folds
    
    Note: This detects CORTICAL structures, not subcortical nuclei (deep nuclei).
    Deep nuclei boundaries are handled by gradient weighting.

    Parameters
    ----------
    volume : npt.NDArray
        Loaded image (aseg, label space).
    structure : npt.NDArray
        Structuring element (e.g. np.ones((3, 3, 3))).
    cortex_labels : set
        Explicit set of cortical label IDs from atlas metadata (e.g., ARM2, ARM3).
    iteration : int
        Number of times mask should be dilated + eroded. Defaults to 1.
    verbose : bool
        Print statistics about detected regions.

    Returns
    -------
    np.ndarray
        Binary mask of narrow/thin cortical structures.
    """
    # Create binary mask of cortical regions only (cortex = 1, everything else = 0)
    cortex_binary = np.zeros(shape=volume.shape)
    cortex_mask = np.isin(volume, list(cortex_labels))
    cortex_binary[cortex_mask] = 1

    # Apply morphological closing (erosion then dilation) to find thin cortical structures
    # This removes thin regions (deep sulci, narrow gyri) while preserving bulk cortex
    eroded = binary_closing(cortex_binary, iterations=iteration, structure=structure)

    # Get the difference: these are the narrow/thin cortical regions that were removed
    diff_image = np.logical_xor(cortex_binary, eroded)
    
    # Print readable statistics
    num_detected = np.sum(diff_image)
    if verbose:
        total_voxels = diff_image.size
        percent = 100 * num_detected / total_voxels if total_voxels > 0 else 0
        print(f"  → Narrow cortical regions: {num_detected:,} voxels ({percent:.2f}% of volume)")
        print(f"     (deep sulci, thin gyri, and intervening WM)")
    
    return diff_image


# Label mapping functions (to aparc (eval) and to label (train))
def read_classes_from_lut(lut_file: str | Path):
    """
    Read in a ColorLUT table with atlas label definitions.
    
    Supports both basic and extended ColorLUT formats:
    - Basic format: ID, LabelName, R, G, B, A
    - Extended format: ID, LabelName, Region, Hemi, R, G, B, A
    
    The extended format includes region type (cortex/subcortex) and hemisphere
    information, eliminating the need for a separate roiinfo file.

    Parameters
    ----------
    lut_file : Path, str
        The path and name of ColorLUT file with classes of interest.
        Example entry (basic):
        ID LabelName  R   G   B   A
        0   Unknown   0   0   0   0
        1   Left-Cerebral-Exterior 70  130 180 0
        
        Example entry (extended):
        ID LabelName  Region  Hemi  R   G   B   A
        2   cortex-rh-ACgG  cortex  rh  240 237 34  0
        ...

    Returns
    -------
    pandas.DataFrame
        DataFrame with label info. Always includes: ID, LabelName, R/Red, G/Green, 
        B/Blue, A/Alpha. May also include: Region, Hemi (if extended format).
    """
    if not isinstance(lut_file, Path):
        lut_file = Path(lut_file)
    if lut_file.suffix == ".tsv":
        return pd.read_csv(lut_file, sep="\t")

    # Read in file
    names = {
        "ID": "int",
        "LabelName": "str",
        "Red": "int",
        "Green": "int",
        "Blue": "int",
        "Alpha": "int",
    }
    kwargs = {}
    if lut_file.suffix == ".csv":
        kwargs["sep"] = ","
    elif lut_file.suffix == ".txt":
        kwargs["sep"] = "\\s+"
    else:
        raise RuntimeError(
            f"Unknown LUT file extension {lut_file}, must be csv, txt or tsv."
        )
    
    # Check if the file has a header row by reading the first non-comment line
    skiprows = []
    with open(lut_file, 'r') as f:
        for row_num, line in enumerate(f):
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith('#'):
                continue
            # Check if first column can be converted to integer
            sep = kwargs.get("sep", ",")
            if sep == "\\s+":
                first_col = line.split()[0]
            else:
                first_col = line.split(sep)[0]
            try:
                int(first_col)
                # First column is an integer, so this is data, not a header
                break
            except ValueError:
                # First column is not an integer, so it's likely a header - skip this row
                skiprows.append(row_num)
                break
    
    return pd.read_csv(
        lut_file,
        index_col=False,
        skip_blank_lines=True,
        comment="#",
        header=None,
        skiprows=skiprows if skiprows else None,
        names=list(names.keys()),
        dtype=names,
        **kwargs,
    )


def lut_has_extended_format(lut_df: pd.DataFrame) -> bool:
    """
    Check if a LUT DataFrame has the extended format with Region and Hemi columns.
    
    Parameters
    ----------
    lut_df : pandas.DataFrame
        DataFrame returned by read_classes_from_lut()
    
    Returns
    -------
    bool
        True if the LUT has Region and Hemi columns (extended format)
    """
    return 'Region' in lut_df.columns and 'Hemi' in lut_df.columns


def get_region_info_from_lut(lut_df: pd.DataFrame) -> tuple[dict[int, str], dict[int, str]]:
    """
    Extract region and hemisphere information from an extended LUT.
    
    Parameters
    ----------
    lut_df : pandas.DataFrame
        DataFrame returned by read_classes_from_lut() with extended format
    
    Returns
    -------
    tuple[dict[int, str], dict[int, str]]
        Two dictionaries: (label_id -> region_type, label_id -> hemisphere)
        Returns empty dicts if LUT doesn't have extended format.
    
    Examples
    --------
    >>> lut = read_classes_from_lut("ARM2_ColorLUT.tsv")
    >>> region_map, hemi_map = get_region_info_from_lut(lut)
    >>> region_map[2]  # 'cortex'
    >>> hemi_map[2]    # 'rh'
    """
    if not lut_has_extended_format(lut_df):
        return {}, {}
    
    region_map = dict(zip(lut_df['ID'], lut_df['Region']))
    hemi_map = dict(zip(lut_df['ID'], lut_df['Hemi']))
    return region_map, hemi_map


def map_label2aparc_aseg(
        mapped_aseg: torch.Tensor,
        labels: torch.Tensor | npt.NDArray
) -> torch.Tensor:
    """
    Perform look-up table mapping from sequential label space to LUT space.

    Parameters
    ----------
    mapped_aseg : torch.Tensor
        Label space segmentation (aparc.DKTatlas + aseg).
    labels : Union[torch.Tensor, npt.NDArray]
        List of labels defining LUT space.

    Returns
    -------
    torch.Tensor
        Labels in LUT space.
    """
    if isinstance(labels, np.ndarray):
        labels = torch.from_numpy(labels)
    labels = labels.to(mapped_aseg.device)
    return labels[mapped_aseg]


# FreeSurfer-specific functions removed
# These were hardcoded for FreeSurfer's specific label scheme and are not needed
# for generalized atlas support (ARM2, ARM3, etc.)


def is_freesurfer_lut(labels: npt.NDArray) -> bool:
    """
    Detect if LUT is FreeSurfer-based or a custom atlas (ARM2, ARM3, etc.).
    
    FreeSurfer uses labels in 1000-2999 range for cortical parcels.
    Custom atlases like ARM2/ARM3 use different schemes (e.g., negative labels for WM).
    
    Parameters
    ----------
    labels : npt.NDArray
        Label IDs from the LUT.
        
    Returns
    -------
    bool
        True if FreeSurfer atlas, False otherwise.
    """
    # Check for negative labels - custom atlases (ARM2/ARM3) use negative labels for WM
    # FreeSurfer never uses negative labels
    if np.any(labels < 0):
        return False
    
    # Check for FreeSurfer's characteristic label range
    # FreeSurfer has many labels between 1000-2999 (cortical parcellations)
    # Custom atlases typically have far fewer labels in this range
    fs_range_labels = np.sum((labels >= 1000) & (labels < 3000))
    
    # If we have more than 50 labels in the FreeSurfer range, it's likely FreeSurfer
    # ARM2/ARM3 have much fewer labels (~36 cortical labels total, ~18 in 1000+ range)
    if fs_range_labels > 50:
        return True
    
    # Default: if uncertain, assume non-FreeSurfer for safety
    # (split_cortex_labels is very specific to FreeSurfer and should not run on other atlases)
    return False


def split_cortex_labels(aparc: npt.NDArray) -> np.ndarray:
    """
    Split cortex labels to completely de-lateralize structures.
    
    ⚠️ WARNING: This function is FREESURFER-SPECIFIC and contains hardcoded
    FreeSurfer label IDs. It should ONLY be called for FreeSurfer atlases.
    
    For custom atlases (ARM2, ARM3, etc.), this function should be skipped.
    The function assumes:
    - WM labels: 2 (LH), 41 (RH)
    - Cortical labels: 1003-1035 (LH), 2003-2035 (RH)
    - LH to RH offset: +1000

    Parameters
    ----------
    aparc : npt.NDArray
        Anatomical segmentation and parcellation from FreeSurfer network.

    Returns
    -------
    np.ndarray
        Re-lateralized aparc (FreeSurfer-specific).
        
    Notes
    -----
    This function is automatically skipped for non-FreeSurfer atlases in predict.py
    based on the is_freesurfer_lut() check.
    """
    # FREESURFER-SPECIFIC: Post processing - Splitting classes
    # Quick Fix for 2026 vs 1026; 2029 vs. 1029; 2025 vs. 1025
    # Uses hardcoded FreeSurfer WM labels: 2 (LH), 41 (RH)
    rh_wm = get_largest_cc(aparc == 41)
    lh_wm = get_largest_cc(aparc == 2)
    rh_wm = regionprops(label(rh_wm, background=0))
    lh_wm = regionprops(label(lh_wm, background=0))
    centroid_rh = np.asarray(rh_wm[0].centroid)
    centroid_lh = np.asarray(lh_wm[0].centroid)

    labels_list = np.array(
        [
            1003,
            1006,
            1007,
            1008,
            1009,
            1011,
            1015,
            1018,
            1019,
            1020,
            1025,
            1026,
            1027,
            1028,
            1029,
            1030,
            1031,
            1034,
            1035,
        ]
    )

    for label_current in labels_list:

        label_img = label(aparc == label_current, connectivity=3, background=0)

        for region in regionprops(label_img):

            if region.label != 0:  # To avoid background

                if np.linalg.norm(
                    np.asarray(region.centroid) - centroid_rh
                ) < np.linalg.norm(np.asarray(region.centroid) - centroid_lh):
                    mask = label_img == region.label
                    aparc[mask] = label_current + 1000

    # Quick Fixes for overlapping classes
    aseg_lh = filters.gaussian_filter(
        1000 * np.asarray(aparc == 2, dtype=float), sigma=3
    )
    aseg_rh = filters.gaussian_filter(
        1000 * np.asarray(aparc == 41, dtype=float), sigma=3
    )

    lh_rh_split = np.argmax(
        np.concatenate(
            (np.expand_dims(aseg_lh, axis=3), np.expand_dims(aseg_rh, axis=3)), axis=3
        ),
        axis=3,
    )

    # Problematic classes: 1026, 1011, 1029, 1019
    for prob_class_lh in [1011, 1019, 1026, 1029]:
        prob_class_rh = prob_class_lh + 1000
        mask_prob_class = (aparc == prob_class_lh) | (aparc == prob_class_rh)
        mask_lh = np.logical_and(mask_prob_class, lh_rh_split == 0)
        mask_rh = np.logical_and(mask_prob_class, lh_rh_split == 1)

        aparc[mask_lh] = prob_class_lh
        aparc[mask_rh] = prob_class_rh

    return aparc


def unify_lateralized_labels(
        lut: str | pd.DataFrame,
        combi: tuple[str, str] = ("Left-", "Right-")
) -> Mapping:
    """
    Generate lookup dictionary of left-right labels.

    Parameters
    ----------
    lut : Union[str, pd.DataFrame]
        Either lut-file string to load or pandas dataframe
        Example entry:
        ID LabelName  R   G   B   A
        0   Unknown   0   0   0   0
        1   Left-Cerebral-Exterior 70  130 180 0.
    combi : Tuple[str, str]
        Prefix or labelnames to combine. Default: Left- and Right-.

    Returns
    -------
    Mapping
        Dictionary mapping between left and right hemispheres.
    """
    if isinstance(lut, str):
        lut = read_classes_from_lut(lut)
    left = lut[["ID", "LabelName"]][lut["LabelName"].str.startswith(combi[0])]
    right = lut[["ID", "LabelName"]][lut["LabelName"].str.startswith(combi[1])]
    left["LabelName"] = left["LabelName"].str.removeprefix(combi[0])
    right["LabelName"] = right["LabelName"].str.removeprefix(combi[1])
    mapp = left.merge(right, on="LabelName")
    return pd.Series(mapp.ID_y.values, index=mapp.ID_x).to_dict()


def get_labels_from_lut(
        lut: str | pd.DataFrame,
        label_extract: tuple[str, str] = ("Left-", "ctx-rh")
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract labels from the lookup tables.

    Parameters
    ----------
    lut : Union[str, pd.DataFrame]
        ColorLUT table with atlas label definitions (either path to it
        or already loaded as pandas DataFrame).
        Example entry:
        ID LabelName  R   G   B   A
        0   Unknown   0   0   0   0
        1   Left-Cerebral-Exterior 70  130 180 0.
    label_extract : Tuple[str, str]
        Suffix of label names to mask for sagittal labels
        Default: "Left-" and "ctx-rh".

    Returns
    -------
    np.ndarray
        Full label list.
    np.ndarray
        Sagittal label list.
    """
    if isinstance(lut, str):
        lut = read_classes_from_lut(lut)
    mask = lut["LabelName"].str.startswith(label_extract)
    return lut["ID"].values, lut["ID"][~mask].values


# FreeSurfer-specific label mapping functions removed
# These contained hardcoded FreeSurfer label mappings (aparc, aseg processing)
# For atlas-agnostic support, use atlas.atlas_manager methods instead


def map_prediction_sagittal2full(
        prediction_sag: npt.NDArray,
        num_classes: int = 51,
        lut: str | None = None,
        atlas_name: str | None = None
) -> np.ndarray:
    """
    Remap the prediction on the sagittal network to full label space used by coronal and axial networks.

    Create full aparc.DKTatlas+aseg.mgz.

    Parameters
    ----------
    prediction_sag : npt.NDArray
        Sagittal prediction (labels).
    num_classes : int
        Number of SAGITTAL classes (96 for full classes, 51 for hemi split, 21 for aseg) (Default value = 51).
    lut : Optional[str]
        Look-up table listing class labels (Default value = None).
    atlas_name : Optional[str]
        Name of the atlas to use. If None, tries to determine from environment or context.

    Returns
    -------
    np.ndarray
        Remapped prediction.
    """
    # Use atlas manager for flexible atlas support
    from atlas.atlas_manager import get_atlas_manager
    import os
    
    # Determine atlas name
    if atlas_name is None:
        atlas_name = os.environ.get('ATLAS_NAME', 'ARM3')
    
    atlas_manager = get_atlas_manager(atlas_name)
    
    # Use atlas-specific expansion mapping
    idx_list = atlas_manager.get_sagittal_to_bilateral_expansion()
    return prediction_sag[:, idx_list, :, :]


# Clean up and class separation
def bbox_3d(
        img: npt.NDArray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract the three-dimensional bounding box coordinates.

    Parameters
    ----------
    img : npt.NDArray
        Mri image.

    Returns
    -------
    np.ndarray
        Rmin.
    np.ndarray
        Rmax.
    np.ndarray
        Cmin.
    np.ndarray
        Cmax.
    np.ndarray
        Zmin.
    np.ndarray
        Zmax.
    """
    r = np.any(img, axis=(1, 2))
    c = np.any(img, axis=(0, 2))
    z = np.any(img, axis=(0, 1))

    rmin, rmax = np.where(r)[0][[0, -1]]
    cmin, cmax = np.where(c)[0][[0, -1]]
    zmin, zmax = np.where(z)[0][[0, -1]]

    return rmin, rmax, cmin, cmax, zmin, zmax


def get_largest_cc(segmentation: npt.NDArray) -> np.ndarray:
    """
    Find the largest connected component of segmentation.

    Parameters
    ----------
    segmentation : npt.NDArray
        Segmentation.

    Returns
    -------
    np.ndarray
        Largest connected component of segmentation (binary mask).
    """
    labels = label(segmentation, connectivity=3, background=0)

    bincount = np.bincount(labels.flat)
    background = np.argmax(bincount)
    bincount[background] = -1

    largest_cc = labels == np.argmax(bincount)

    return largest_cc
