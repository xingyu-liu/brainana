#!/usr/bin/env python3
"""
Fix missing thin WM in V1 by registering template V1 WM to individual space.

This script:
1. Crops to V1 ROI region
2. Registers template T1w to individual T1w
3. Applies transform to template V1 WM segmentation
4. Integrates the backprojected WM labels into the original segmentation

Copyright 2024
"""

import nibabel as nib
import numpy as np
import pandas as pd
from skimage.measure import label
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# Constants
HEMISPHERES = ['lh', 'rh']
HEMI_MASK_VALUES = {'rh': 1, 'lh': 2}
CONNECTIVITY = 2
DEFAULT_ROI_NAME = 'calcarine'
DEFAULT_WM_THRESHOLD = 0.5


def get_cube_range(data: np.ndarray, key_list: List[int]) -> np.ndarray:
    """
    Get the cube index range that covers the specific keys.
    
    Parameters
    ----------
    data : np.ndarray
        3D atlas data
    key_list : list
        List of label IDs to find
        
    Returns
    -------
    np.ndarray
        3D index range [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
    """
    key_range = np.where(np.isin(data, key_list))
    
    # Check if any matches were found
    if len(key_range[0]) == 0:
        raise ValueError(f"No voxels found matching the key_list: {key_list}")
    
    return np.array([[np.min(key_range[i]), np.max(key_range[i])] for i in range(3)])


def detect_connected_components(data: np.ndarray) -> Tuple[np.ndarray, int, np.ndarray]:
    """
    Detect connected components in binary data.
    
    Parameters
    ----------
    data : np.ndarray
        Binary 3D data
        
    Returns
    -------
    comp_label : np.ndarray
        Labeled connected components
    num_comp : int
        Number of components
    comp_sizes : np.ndarray
        Size of each component
    """
    comp_label, num_comp = label(data, return_num=True, connectivity=CONNECTIVITY)
    comp_sizes = np.bincount(comp_label.flatten())[1:]

    print(f"number of connected components: {num_comp}")
    print(f"size of each component (sorted): {', '.join(np.sort(comp_sizes)[::-1].astype(str))}")

    return comp_label, num_comp, comp_sizes


def crop_3d_array(data: np.ndarray, cube_range: np.ndarray) -> np.ndarray:
    """
    Crop a 3D array to the specified cube range.
    
    Parameters
    ----------
    data : np.ndarray
        3D array to crop
    cube_range : np.ndarray
        3D index range [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
        
    Returns
    -------
    np.ndarray
        Cropped 3D array
    """
    return data[
        cube_range[0, 0]:cube_range[0, 1] + 1,
        cube_range[1, 0]:cube_range[1, 1] + 1,
        cube_range[2, 0]:cube_range[2, 1] + 1
    ]


def calculate_cropped_affine(original_affine: np.ndarray, cube_range: np.ndarray) -> np.ndarray:
    """
    Calculate the affine transformation for cropped data.
    
    Parameters
    ----------
    original_affine : np.ndarray
        Original 4x4 affine matrix
    cube_range : np.ndarray
        3D index range [[x_min, x_max], [y_min, y_max], [z_min, z_max]]
        
    Returns
    -------
    np.ndarray
        New 4x4 affine matrix for cropped data
    """
    new_affine = original_affine.copy()
    crop_offset = np.array([cube_range[0, 0], cube_range[1, 0], cube_range[2, 0], 1])
    new_affine[:3, 3] = (original_affine @ crop_offset)[:3]
    return new_affine


def load_and_crop_roi_data(
    t1w_path: Path,
    seg_path: Path,
    mask_path: Optional[Path],
    roi_cube_range: np.ndarray,
    cerebellum_indices: np.ndarray,
    keep_largest_component: bool = True,
    verbose: bool = True
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, nib.Nifti1Image, nib.Nifti1Image]:
    """
    Load and crop T1w and segmentation data to ROI region.
    
    Parameters
    ----------
    t1w_path : Path
        Path to T1w file
    seg_path : Path
        Path to segmentation file
    mask_path : Path, optional
        Path to brain mask file (if None, mask is not applied)
    roi_cube_range : np.ndarray
        3D index range for ROI
    cerebellum_indices : np.ndarray
        Cerebellum label indices to exclude
    keep_largest_component : bool
        Whether to keep only the largest connected component
    verbose : bool
        Print progress information
        
    Returns
    -------
    t1w_roi : np.ndarray
        Cropped T1w data
    seg_roi : np.ndarray
        Cropped segmentation data
    seg_roi_orig : np.ndarray
        Original cropped segmentation (before exclusions)
    new_affine : np.ndarray
        Affine matrix for cropped data
    t1w_img : nib.Nifti1Image
        Original T1w image object
    seg_img : nib.Nifti1Image
        Original segmentation image object
    """
    # Load images
    t1w_img = nib.load(str(t1w_path))
    t1w_data = t1w_img.get_fdata()
    
    seg_img = nib.load(str(seg_path))
    seg_data = seg_img.get_fdata().astype(np.int16)
    
    # Crop to ROI
    t1w_roi = crop_3d_array(t1w_data, roi_cube_range)
    seg_roi = crop_3d_array(seg_data, roi_cube_range)
    seg_roi_orig = np.copy(seg_roi)
    
    # Apply mask if provided
    if mask_path is not None:
        mask_img = nib.load(str(mask_path))
        mask_data = mask_img.get_fdata().astype(np.int16)
        mask_roi = crop_3d_array(mask_data, roi_cube_range)
        t1w_roi[mask_roi == 0] = 0
    
    # Exclude cerebellum
    t1w_roi[np.isin(seg_roi, cerebellum_indices)] = 0
    seg_roi[np.isin(seg_roi, cerebellum_indices)] = 0
    
    # Keep only largest connected component
    if keep_largest_component:
        if verbose:
            print("Detecting connected components...")
        labeled_roi, num_comp, comp_sizes = detect_connected_components(t1w_roi != 0)
        if num_comp > 0:
            largest_component = np.argmax(comp_sizes) + 1
            t1w_roi[labeled_roi != largest_component] = 0
            seg_roi[labeled_roi != largest_component] = 0
    
    # Calculate new affine
    new_affine = calculate_cropped_affine(t1w_img.affine, roi_cube_range)
    
    return t1w_roi, seg_roi, seg_roi_orig, new_affine, t1w_img, seg_img


def save_cropped_image(
    data: np.ndarray,
    affine: np.ndarray,
    header: nib.Nifti1Header,
    output_path: Path,
    verbose: bool = True
) -> None:
    """
    Save cropped image to file.
    
    Parameters
    ----------
    data : np.ndarray
        Image data
    affine : np.ndarray
        Affine matrix
    header : nib.Nifti1Header
        Image header
    output_path : Path
        Output file path
    verbose : bool
        Print progress information
    """
    img = nib.Nifti1Image(data, affine, header)
    nib.save(img, str(output_path))
    if verbose:
        print(f"  Saved cropped image to: {output_path}")


def _get_stem_without_extension(path: Path) -> str:
    """
    Get file stem without .nii/.mgz extensions.
    
    Handles .nii, .mgz, and .nii.gz extensions properly.
    
    Parameters
    ----------
    path : Path
        File path
        
    Returns
    -------
    str
        Stem without .nii/.mgz extension
    """
    # Handle .nii.gz first (Path.stem only removes .gz, leaving .nii)
    name = path.name
    if name.endswith('.nii.gz'):
        return name[:-7]
    elif name.endswith('.nii') or name.endswith('.mgz'):
        return name[:-4]
    # Otherwise return stem (which removes the last extension)
    return path.stem


def fix_roi_wm(
    seg_f: str,
    t1w_f: str,
    mask_f: str,
    hemi_mask_f: str,
    lut_path: str,
    tpl_seg_f: str,
    tpl_t1w_f: str,
    tpl_roi_wm_f: str,
    roi_name: str = DEFAULT_ROI_NAME,
    wm_thr: float = DEFAULT_WM_THRESHOLD,
    backup_original: bool = True,
    verbose: bool = True
) -> None:
    """
    Fix missing thin WM in V1 by registering template V1 WM to individual space.
    
    Parameters
    ----------
    seg_f : str
        Path to segmentation file (will be modified in place)
    t1w_f : str
        Path to T1w file
    mask_f : str
        Path to brain mask file
    hemi_mask_f : str
        Path to hemisphere mask file
    lut_path : str
        Path to ColorLUT file
    tpl_seg_f : str
        Path to template segmentation file
    tpl_t1w_f : str
        Path to template T1w file (full image, will be cropped to ROI internally)
    tpl_roi_wm_f : str
        Path to template WM probability map
    roi_name : str, optional
        ROI name (default: 'calcarine')
    wm_thr : float, optional
        Threshold for WM probability map (default: 0.5)
    backup_original : bool, optional
        Whether to backup original segmentation (default: True)
    verbose : bool, optional
        Print progress information (default: True)
    """
    try:
        from macacaMRIprep.operations.registration import ants_register, ants_apply_transforms
    except ImportError:
        raise ImportError(
            "macacaMRIprep is required for V1 WM fixing. "
            "Please install it or skip this step with --no-fixv1"
        )
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"Fixing V1 WM using template registration")
        print(f"{'='*70}\n")
    
    # Convert paths to Path objects
    seg_f = Path(seg_f)
    t1w_f = Path(t1w_f)
    mask_f = Path(mask_f)
    hemi_mask_f = Path(hemi_mask_f)
    tpl_seg_f = Path(tpl_seg_f)
    tpl_t1w_f = Path(tpl_t1w_f)
    tpl_roi_wm_f = Path(tpl_roi_wm_f)
    lut_path = Path(lut_path)
    
    # Create working directory
    working_dir = seg_f.parent / roi_name
    working_dir.mkdir(exist_ok=True)
    
    # Load ColorLUT
    if verbose:
        print(f"Loading ColorLUT: {lut_path}")
    roi_info = pd.read_csv(lut_path, sep='\t')
    roi_info = roi_info.dropna().reset_index(drop=True)
    
    # Get ROI indices
    roi_index = {
        hemi: roi_info.loc[(roi_info['name'] == roi_name) & (roi_info['hemi'] == hemi), 'ID'].values
        for hemi in HEMISPHERES
    }
    if verbose:
        print(f"ROI indices: {roi_index}")
    
    # Get cerebellum indices (to exclude)
    cerebellum_index = roi_info.loc[roi_info['name_full'].str.contains('cerebellum'), 'ID'].values
    if verbose:
        print(f"Cerebellum indices to exclude: {len(cerebellum_index)} labels")
    
    # Get WM indices
    wm_index = {
        hemi: roi_info.loc[(roi_info['name'] == 'ctxWM') & (roi_info['hemi'] == hemi), 'ID'].values[0]
        for hemi in HEMISPHERES
    }
    if verbose:
        print(f"WM indices: {wm_index}")
    
    # Load and crop individual data
    if verbose:
        print(f"\nLoading and cropping individual data to {roi_name} region...")
    seg_img = nib.load(str(seg_f))
    seg_data = seg_img.get_fdata().astype(np.int16)
    roi_cube_range = get_cube_range(seg_data, list(roi_index.values()))
    
    t1w_roi, seg_roi, seg_roi_orig, new_affine, t1w_img, _ = load_and_crop_roi_data(
        t1w_path=t1w_f,
        seg_path=seg_f,
        mask_path=mask_f,
        roi_cube_range=roi_cube_range,
        cerebellum_indices=cerebellum_index,
        keep_largest_component=True,
        verbose=verbose
    )
    
    # Save cropped individual ROI files
    seg_roi_f = working_dir / f"input_segmentation_{roi_name}.nii.gz"
    t1w_roi_f = working_dir / f"input_T1w_{roi_name}.nii.gz"
    
    save_cropped_image(t1w_roi, new_affine, t1w_img.header, t1w_roi_f, verbose)
    save_cropped_image(seg_roi, new_affine, seg_img.header, seg_roi_f, verbose)
    
    # Load and crop template data
    if verbose:
        print(f"\nLoading and cropping template data to {roi_name} region...")
    tpl_seg_img = nib.load(str(tpl_seg_f))
    tpl_seg_data = tpl_seg_img.get_fdata().astype(np.int16)
    tpl_roi_cube_range = get_cube_range(tpl_seg_data, list(roi_index.values()))
    
    tpl_t1w_roi, tpl_seg_roi, _, tpl_new_affine, tpl_t1w_img, _ = load_and_crop_roi_data(
        t1w_path=tpl_t1w_f,
        seg_path=tpl_seg_f,
        mask_path=None,  # Template doesn't use mask
        roi_cube_range=tpl_roi_cube_range,
        cerebellum_indices=cerebellum_index,
        keep_largest_component=False,  # Template doesn't need component filtering
        verbose=verbose
    )
    
    # Save cropped template ROI files
    tpl_seg_roi_f = working_dir / f"tpl_segmentation_{roi_name}.nii.gz"
    tpl_t1w_roi_f = working_dir / f"tpl_T1w_{roi_name}.nii.gz"
    
    save_cropped_image(tpl_t1w_roi, tpl_new_affine, tpl_t1w_img.header, tpl_t1w_roi_f, verbose)
    save_cropped_image(tpl_seg_roi, tpl_new_affine, tpl_seg_img.header, tpl_seg_roi_f, verbose)
    
    # Registration
    if verbose:
        print(f"\nRegistering template to individual space...")
    reg_working_dir = working_dir / 'registration'
    reg_working_dir.mkdir(exist_ok=True)
    
    reg_outputs = ants_register(
        fixedf=str(t1w_roi_f),
        movingf=str(tpl_t1w_roi_f),
        working_dir=str(reg_working_dir),
        output_prefix='template_to_individual',
        xfm_type='syn'
    )
    
    if verbose:
        print(f"  Forward transform: {reg_outputs['forward_transform']}")
    
    # Apply transforms to template WM probability map
    wm_roi_transformed_f = seg_roi_f.with_name(
        seg_roi_f.stem + '_reversed_from_template_WM.nii.gz'
    )
    
    if verbose:
        print(f"\nApplying transforms to template WM probability map...")
    
    ants_apply_transforms(
        movingf=str(tpl_roi_wm_f),
        moving_type=0,
        interpolation='LanczosWindowedSinc',
        outputf_name=str(wm_roi_transformed_f),
        fixedf=str(t1w_roi_f),
        working_dir=str(reg_working_dir),
        transformf=reg_outputs['forward_transform'],
        generate_tmean=False
    )
    
    # Integrate backprojected WM labels
    if verbose:
        print(f"\nIntegrating backprojected WM labels...")
    
    wm_roi_transformed = nib.load(str(wm_roi_transformed_f)).get_fdata()
    wm_roi_binary = wm_roi_transformed > wm_thr
    
    # Load hemisphere mask and crop to ROI
    hemi_mask_img = nib.load(str(hemi_mask_f))
    hemi_mask = hemi_mask_img.get_fdata().astype(np.int16)
    hemi_mask_roi = crop_3d_array(hemi_mask, roi_cube_range)
    
    # Update segmentation with WM labels
    seg_roi_refined = np.copy(seg_roi_orig)
    if verbose:
        print(f"  Original WM voxels - RH: {np.sum(seg_roi_refined == wm_index['rh'])}, "
              f"LH: {np.sum(seg_roi_refined == wm_index['lh'])}")
    
    for hemi in HEMISPHERES:
        hemi_mask_value = HEMI_MASK_VALUES[hemi]
        seg_roi_refined[(hemi_mask_roi == hemi_mask_value) & (wm_roi_binary != 0)] = wm_index[hemi]
    
    if verbose:
        print(f"  Updated WM voxels - RH: {np.sum(seg_roi_refined == wm_index['rh'])}, "
              f"LH: {np.sum(seg_roi_refined == wm_index['lh'])}")
    
    # Put back to uncropped space
    seg_refined = np.copy(seg_data)
    seg_refined[
        roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1,
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1,
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1
    ] = seg_roi_refined
    
    # Backup and save
    if backup_original:
        backup_f = seg_f.with_name(_get_stem_without_extension(seg_f) + '_orig.nii.gz')
        if not backup_f.exists():  # Don't overwrite existing backup
            shutil.copy(str(seg_f), str(backup_f))
            if verbose:
                print(f"\n  Backed up original segmentation to: {backup_f}")
    
    seg_refined_img = nib.MGHImage(seg_refined, t1w_img.affine, seg_img.header)
    nib.save(seg_refined_img, str(seg_f))
    
    if verbose:
        print(f"\n✅ V1 WM fixing completed!")
        print(f"  Updated segmentation: {seg_f}")
        print(f"{'='*70}\n")
