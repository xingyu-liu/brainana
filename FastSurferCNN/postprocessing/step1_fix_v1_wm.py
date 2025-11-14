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
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional


def get_cube_range(data, key_list):
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


def detect_connected_components(data):
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
    comp_label, num_comp = label(data, return_num=True, connectivity=2)
    comp_sizes = np.bincount(comp_label.flatten())[1:]

    print(f"number of connected components: {num_comp}")
    print(f"size of each component (sorted): {', '.join(np.sort(comp_sizes)[::-1].astype(str))}")

    return comp_label, num_comp, comp_sizes


def fix_v1_wm(
    seg_f: str,
    t1w_f: str,
    mask_f: str,
    hemi_mask_f: str,
    lut_path: str,
    tpl_t1w_f: str,
    tpl_wm_f: str,
    roi_name: str = 'V1',
    wm_thr: float = 0.5,
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
    tpl_t1w_f : str
        Path to template T1w file (cropped to ROI)
    tpl_wm_f : str
        Path to template WM probability map
    roi_name : str, optional
        ROI name (default: 'V1')
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
        for hemi in ['lh', 'rh']
    }
    if verbose:
        print(f"ROI indices: {roi_index}")
    
    # Get cerebellum indices (to exclude)
    cerebellum_index = roi_info.loc[roi_info['name_full'].str.contains('cerebellum'), 'ID'].values
    if verbose:
        print(f"Cerebellum indices to exclude: {len(cerebellum_index)} labels")
    
    # Get WM indices
    WM_index = {
        hemi: roi_info.loc[(roi_info['name'] == 'ctxWM') & (roi_info['hemi'] == hemi), 'ID'].values[0] 
        for hemi in ['lh', 'rh']
    }
    if verbose:
        print(f"WM indices: {WM_index}")
    
    # Load MRI data
    if verbose:
        print(f"\nLoading MRI data...")
    t1w_img = nib.load(str(t1w_f))
    seg_img = nib.load(str(seg_f))
    mask_img = nib.load(str(mask_f))
    hemi_mask_img = nib.load(str(hemi_mask_f))
    
    t1w_data = t1w_img.get_fdata()
    seg_data = seg_img.get_fdata().astype(np.int16)
    mask_data = mask_img.get_fdata().astype(np.int16)
    hemi_mask = hemi_mask_img.get_fdata().astype(np.int16)
    
    # Get cube range covering the ROI
    if verbose:
        print(f"\nCropping to {roi_name} region...")
    roi_cube_range = get_cube_range(seg_data, list(roi_index.values()))
    
    # Crop all data to ROI
    seg_roi = seg_data[
        roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1, 
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1, 
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1]
    t1w_roi = t1w_data[
        roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1, 
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1, 
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1]
    mask_roi = mask_data[
        roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1, 
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1, 
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1]
    hemi_mask_roi = hemi_mask[
        roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1, 
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1, 
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1]
    
    # Set excluded areas to 0
    t1w_roi[mask_roi==0] = 0
    t1w_roi[np.isin(seg_roi, cerebellum_index)] = 0
    
    seg_roi_orig = np.copy(seg_roi)
    seg_roi[np.isin(seg_roi, cerebellum_index)] = 0
    
    # Keep only largest connected component
    if verbose:
        print(f"Detecting connected components...")
    labeled_roi, num_comp, comp_sizes = detect_connected_components(t1w_roi!=0)
    largest_component = np.argmax(comp_sizes) + 1
    t1w_roi[labeled_roi != largest_component] = 0
    seg_roi[labeled_roi != largest_component] = 0
    
    # Save cropped ROI files
    seg_roi_f = working_dir / f"{seg_f.stem}_{roi_name}.nii.gz"
    t1w_roi_f = working_dir / f"{t1w_f.stem}_{roi_name}.nii.gz"
    
    # Calculate new affine for cropped data
    affine_orig = t1w_img.affine.copy()
    crop_offset = np.array([roi_cube_range[0, 0], roi_cube_range[1, 0], roi_cube_range[2, 0], 1])
    new_affine = affine_orig.copy()
    new_affine[:3, 3] = (affine_orig @ crop_offset)[:3]
    
    # Save cropped files
    t1w_roi_img = nib.Nifti1Image(t1w_roi, new_affine, t1w_img.header)
    seg_roi_img = nib.Nifti1Image(seg_roi, new_affine, seg_img.header)
    nib.save(t1w_roi_img, str(t1w_roi_f))
    nib.save(seg_roi_img, str(seg_roi_f))
    
    if verbose:
        print(f"  Saved cropped T1w to: {t1w_roi_f}")
        print(f"  Saved cropped segmentation to: {seg_roi_f}")
    
    # Registration
    if verbose:
        print(f"\nRegistering template to individual space...")
    reg_working_dir = working_dir / 'registration'
    reg_working_dir.mkdir(exist_ok=True)
    
    reg_outputs = ants_register(
        fixedf=str(t1w_roi_f),
        movingf=tpl_t1w_f,
        working_dir=str(reg_working_dir),
        output_prefix='template_to_individual',
        xfm_type='syn'
    )
    
    if verbose:
        print(f"  Forward transform: {reg_outputs['forward_transform']}")
    
    # Apply transforms to template segmentation and WM
    WM_roi_2_f = str(seg_roi_f).replace('.nii.gz', '_reversed_from_template_WM.nii.gz')
    
    if verbose:
        print(f"\nApplying transforms to template images...")
    
    ants_apply_transforms(
        movingf=tpl_wm_f,
        moving_type=0,
        interpolation='LanczosWindowedSinc',
        outputf_name=WM_roi_2_f,
        fixedf=str(t1w_roi_f),
        working_dir=str(reg_working_dir),
        transformf=reg_outputs['forward_transform'],
        generate_tmean=False
    )
    
    # Reload backprojected segmentation
    if verbose:
        print(f"\nIntegrating backprojected WM labels...")
    
    WM_roi_2 = nib.load(WM_roi_2_f).get_fdata()
    WM_roi_2 = WM_roi_2 > wm_thr
    
    # Convert WM to hemisphere-wise segmentation
    hemi_mask_dict = {'rh': 1, 'lh': 2}
    
    seg_roi_2_refined = np.copy(seg_roi_orig)
    if verbose:
        print(f"  Original WM voxels - RH: {np.sum(seg_roi_2_refined==WM_index['rh'])}, LH: {np.sum(seg_roi_2_refined==WM_index['lh'])}")
    
    for hemi in ['rh', 'lh']:
        seg_roi_2_refined[(hemi_mask_roi==hemi_mask_dict[hemi]) & (WM_roi_2 != 0)] = WM_index[hemi]
    
    if verbose:
        print(f"  Updated WM voxels - RH: {np.sum(seg_roi_2_refined==WM_index['rh'])}, LH: {np.sum(seg_roi_2_refined==WM_index['lh'])}")
    
    # Put back to uncropped space
    seg_2 = np.copy(seg_data)
    seg_2[roi_cube_range[0, 0]:roi_cube_range[0, 1] + 1, 
        roi_cube_range[1, 0]:roi_cube_range[1, 1] + 1, 
        roi_cube_range[2, 0]:roi_cube_range[2, 1] + 1] = seg_roi_2_refined
    
    # Backup and save
    if backup_original:
        backup_f = str(seg_f).replace('.mgz', '_orig.mgz')
        if not Path(backup_f).exists():  # Don't overwrite existing backup
            shutil.copy(str(seg_f), backup_f)
            if verbose:
                print(f"\n  Backed up original segmentation to: {backup_f}")
    
    seg_2_img = nib.MGHImage(seg_2, t1w_img.affine, seg_img.header)
    nib.save(seg_2_img, str(seg_f))
    
    if verbose:
        print(f"\n✅ V1 WM fixing completed!")
        print(f"  Updated segmentation: {seg_f}")
        print(f"{'='*70}\n")
