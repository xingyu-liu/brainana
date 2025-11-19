#!/usr/bin/env python3
"""
Generic postprocessing utilities for segmentation.

Contains reusable functions for:
- WM island flipping
- Mask creation
- Hemisphere mask creation

Copyright 2024
"""

import sys
from pathlib import Path
from typing import List

import numpy as np
import scipy.ndimage
from numpy import typing as npt
from skimage.measure import label

# Add parent directory to path for data_loader imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from FastSurferCNN.data_loader.data_utils import read_classes_from_lut


def flip_wm_islands(
    aseg_data: npt.NDArray[int],
    lh_wm_labels: List[int],
    rh_wm_labels: List[int]
) -> npt.NDArray[int]:
    """
    Flip disconnected WM islands to correct hemisphere.
    
    Sometimes WM islands are mislabeled and far from the main body.
    This can cause mri_cc to be very slow.
    
    Parameters
    ----------
    aseg_data : np.ndarray
        Segmentation data (usually after reduce_to_aseg)
    lh_wm_labels : list[int]
        List of left hemisphere WM label IDs (from roiinfo.txt)
    rh_wm_labels : list[int]
        List of right hemisphere WM label IDs (from roiinfo.txt)
        
    Returns
    -------
    np.ndarray
        Segmentation with WM islands flipped
    """
    if not lh_wm_labels and not rh_wm_labels:
        print("No WM labels provided, skipping flip_wm_islands")
        return aseg_data
    
    print("Checking for disconnected WM islands...")
    
    # Process each hemisphere's WM labels
    for wm_labels, other_wm_labels, hemi in [
        (lh_wm_labels, rh_wm_labels, 'LH'),
        (rh_wm_labels, lh_wm_labels, 'RH')
    ]:
        for wm_label in wm_labels:
            wm_mask = (aseg_data == wm_label)
            
            if not np.any(wm_mask):
                continue
            
            # Find connected components
            labeled_wm, num_components = label(wm_mask, return_num=True, connectivity=3)
            
            if num_components <= 1:
                continue
            
            print(f"  {hemi} WM (label={wm_label}) has {num_components} components")
            
            # Find largest component
            unique, counts = np.unique(labeled_wm[labeled_wm > 0], return_counts=True)
            largest = unique[np.argmax(counts)]
            
            # Check each island
            for component_id in unique:
                if component_id == largest:
                    continue
                
                # Get island voxels
                island_mask = (labeled_wm == component_id)
                island_size = np.sum(island_mask)
                
                # Find center of mass of island and main body
                island_com = np.array(np.where(island_mask)).mean(axis=1)
                main_com = np.array(np.where(labeled_wm == largest)).mean(axis=1)
                
                # Find center of mass of other hemisphere WM (any label)
                other_wm_mask = np.zeros_like(aseg_data, dtype=bool)
                for other_label in other_wm_labels:
                    other_wm_mask |= (aseg_data == other_label)
                
                if np.any(other_wm_mask):
                    other_com = np.array(np.where(other_wm_mask)).mean(axis=1)
                    
                    # If island is closer to other hemisphere, flip it to the most common other WM label
                    dist_to_main = np.linalg.norm(island_com - main_com)
                    dist_to_other = np.linalg.norm(island_com - other_com)
                    
                    if dist_to_other < dist_to_main:
                        # Use the first other WM label as target
                        target_label = other_wm_labels[0]
                        print(f"    Flipping island (size={island_size}) to label {target_label}")
                        aseg_data[island_mask] = target_label
    
    return aseg_data


def flip_wm_islands_auto(aseg_data: npt.NDArray[int], lut_path: Path) -> npt.NDArray[int]:
    """
    Wrapper for flip_wm_islands that extracts WM labels from extended ColorLUT.
    
    Parameters
    ----------
    aseg_data : np.ndarray
        Segmentation data (usually after reduce_to_aseg)
    lut_path : Path
        Path to extended ColorLUT file (must have region/hemi columns).
        
    Returns
    -------
    np.ndarray
        Segmentation with WM islands flipped
    """
    lut_path = Path(lut_path)
    lut_df = read_classes_from_lut(lut_path)
    
    # Find region and hemi columns (case-insensitive)
    region_col = None
    hemi_col = None
    
    for col in lut_df.columns:
        if col.lower() == 'region':
            region_col = col
        elif col.lower() == 'hemi':
            hemi_col = col
    
    if region_col is None or hemi_col is None:
        print(f"Warning: ColorLUT {lut_path.name} doesn't have extended format, skipping flip_wm_islands")
        return aseg_data
    
    # Extract WM labels from extended LUT using vectorized operations
    wm_mask = lut_df[region_col].str.lower() == 'wm'
    lh_wm_labels = lut_df[wm_mask & (lut_df[hemi_col].str.lower() == 'lh')]['ID'].tolist()
    rh_wm_labels = lut_df[wm_mask & (lut_df[hemi_col].str.lower() == 'rh')]['ID'].tolist()
    
    if not lh_wm_labels and not rh_wm_labels:
        print("Warning: No WM labels found in extended ColorLUT, skipping flip_wm_islands")
        return aseg_data
    
    print(f"✓ Loaded WM labels from extended ColorLUT")
    return flip_wm_islands(aseg_data, lh_wm_labels=lh_wm_labels, rh_wm_labels=rh_wm_labels)


def extract_largest_component(mask: npt.NDArray[int]) -> npt.NDArray[int]:
    """
    Extract the largest connected component from a binary mask.
    
    Parameters
    ----------
    mask : np.ndarray
        Binary mask array (0 or 1)
        
    Returns
    -------
    np.ndarray
        Binary mask containing only the largest connected component
    """
    if not np.any(mask):
        return mask  # Return empty mask if no positive voxels
    
    # Label connected components
    labels, num_labels = label(mask, return_num=True, connectivity=3)
    
    if num_labels == 0:
        return mask
    
    # Find largest component (excluding background label 0)
    unique, counts = np.unique(labels, return_counts=True)
    if len(counts) == 1:
        # Only background, return original
        return mask
    
    # Exclude background (0) and find largest
    largest_component = unique[np.argmax(counts[1:]) + 1]
    return (labels == largest_component).astype(mask.dtype)


def fill_label_holes(mask: npt.NDArray[int]) -> npt.NDArray[int]:
    """
    Fill holes in a binary mask using scipy's binary_fill_holes.
    
    This properly fills all holes in the mask, including those that may
    be connected to the main background through narrow connections.
    
    Parameters
    ----------
    mask : np.ndarray
        Binary mask array (0 or 1)
        
    Returns
    -------
    np.ndarray
        Binary mask with holes filled
    """
    # Convert to boolean for binary_fill_holes
    mask_bool = mask.astype(bool)
    
    # Fill holes using scipy's binary_fill_holes
    # This fills all holes that are completely surrounded by foreground
    filled_mask = scipy.ndimage.binary_fill_holes(mask_bool)
    
    return filled_mask.astype(mask.dtype)


def create_mask(aseg_data: npt.NDArray[int], dnum: int, enum: int) -> npt.NDArray[int]:
    """
    Create brain mask from aseg.
    
    Extract largest component, fill holes, then apply dilation/erosion.
    
    Parameters
    ----------
    aseg_data : np.ndarray
        Segmentation data
    dnum : int
        Number of dilation iterations
    enum : int
        Number of erosion iterations
        
    Returns
    -------
    np.ndarray
        Binary mask (1 = brain, 0 = background)
    """
    print(f"Creating mask (dilate {dnum}, erode {enum})...")
    
    # 1. Get initial mask (before dilation or erosion)
    mask = (aseg_data != 0).astype(int)
    print(f"  Initial mask: {np.sum(mask):,} voxels")
    
    # 2. Extract largest component
    mask = extract_largest_component(mask)
    print(f"  After extracting largest component: {np.sum(mask):,} voxels")
    
    # 3. Fill holes
    mask = fill_label_holes(mask)
    print(f"  After filling holes: {np.sum(mask):,} voxels")
    
    # 4. Apply morphological operations (dilation then erosion)
    # Use padding to avoid boundary effects where dilation is constrained
    # but erosion still applies fully, causing over-erosion
    if dnum > 0 or enum > 0:
        # Pad by the maximum of dilation/erosion iterations to ensure enough space
        pad_size = max(dnum, enum)
        
        # Pad the mask (3D: pad all three dimensions)
        padded_mask = np.pad(mask, pad_size, mode='constant', constant_values=0)
        
        # Apply dilation on padded mask
        if dnum > 0:
            padded_mask = scipy.ndimage.binary_dilation(padded_mask, iterations=dnum)
            print(f"  After dilation ({dnum} iterations): {np.sum(padded_mask):,} voxels (padded)")
        
        # Apply erosion on padded mask
        if enum > 0:
            padded_mask = scipy.ndimage.binary_erosion(padded_mask, iterations=enum)
            print(f"  After erosion ({enum} iterations): {np.sum(padded_mask):,} voxels (padded)")
        
        # Crop back to original size
        # For 3D: [pad_size:-pad_size, pad_size:-pad_size, pad_size:-pad_size]
        if mask.ndim == 3:
            mask = padded_mask[pad_size:-pad_size, pad_size:-pad_size, pad_size:-pad_size]
        elif mask.ndim == 2:
            mask = padded_mask[pad_size:-pad_size, pad_size:-pad_size]
    
    return mask.astype(int)


def create_hemisphere_masks(mask_data: npt.NDArray[int], 
    atlas_seg_data: npt.NDArray[int], 
    lut_path: Path) -> npt.NDArray[int]:
    """
    Create hemisphere masks from mask data and atlas segmentation data.
    
    Parameters
    ----------
    mask_data : npt.NDArray[int]
        Binary mask indicating brain voxels (1 = brain, 0 = background)
    atlas_seg_data : npt.NDArray[int]
        Atlas segmentation with label IDs
    lut_path : Path
        Path to the extended ColorLUT file (must have hemi column)
        
    Returns
    -------
    npt.NDArray[int]
        Hemisphere mask where 1 = right hemisphere, 2 = left hemisphere, 0 = background
    """
    lut_df = read_classes_from_lut(lut_path)
    
    # Find hemi column (case-insensitive)
    hemi_col = None
    for col in lut_df.columns:
        if col.lower() == 'hemi':
            hemi_col = col
            break
    
    if hemi_col is None:
        raise ValueError(f"ColorLUT {lut_path} does not have 'hemi' column")
    
    hemi_dict = {'rh': 1, 'lh': 2}
    hemi_list = ['rh', 'lh']
    
    print("Creating hemisphere masks...")

    # Step 1: Create initial hemisphere masks based on atlas segmentation
    # Read hemisphere info directly from ColorLUT for ALL labels (won't miss anything)
    lh_labels = lut_df[lut_df[hemi_col].str.lower() == 'lh']['ID'].tolist()
    rh_labels = lut_df[lut_df[hemi_col].str.lower() == 'rh']['ID'].tolist()
    hemi_labels = {'lh': lh_labels, 'rh': rh_labels}
    
    # Create masks for voxels that have labels in atlas_seg_data
    # These are DEFINITIVE and should not be changed
    hemi_mask_definitive = {hemi: np.zeros(mask_data.shape, dtype=int) for hemi in hemi_list}
    for hemi in hemi_list:
        if hemi_labels[hemi]:
            hemi_mask_definitive[hemi][np.isin(atlas_seg_data, hemi_labels[hemi])] = 1
            print(f"  {hemi.upper()}: {np.sum(hemi_mask_definitive[hemi])} voxels from atlas labels (definitive)")
    
    # Create mask of all voxels that have atlas labels (any hemisphere)
    has_atlas_label = np.zeros(mask_data.shape, dtype=int)
    for hemi in hemi_list:
        has_atlas_label = has_atlas_label | hemi_mask_definitive[hemi]
    
    # Find voxels in brain mask but NOT in atlas segmentation - these need hemisphere assignment
    needs_assignment = (mask_data == 1) & (has_atlas_label == 0)
    num_needs_assignment = np.sum(needs_assignment)
    print(f"  {num_needs_assignment} voxels in mask need hemisphere assignment (not in atlas)")

    # Step 2: For voxels needing assignment, dilate from definitive hemisphere regions
    if num_needs_assignment > 0:
        print("  Dilating from definitive regions (5 iterations)...")
        hemi_mask_dilated = {}
        for hemi in hemi_list:
            hemi_mask_dilated[hemi] = scipy.ndimage.binary_dilation(hemi_mask_definitive[hemi], iterations=5)
            # Only keep voxels that need assignment
            hemi_mask_dilated[hemi] = hemi_mask_dilated[hemi] * needs_assignment
        
        # Resolve conflicts: if both claim a voxel, leave it for distance transform
        conflict_mask = hemi_mask_dilated['lh'] * hemi_mask_dilated['rh']
        hemi_mask_from_dilation = {}
        for hemi in hemi_list:
            hemi_mask_from_dilation[hemi] = hemi_mask_dilated[hemi] * (1 - conflict_mask)
    else:
        hemi_mask_from_dilation = {hemi: np.zeros(mask_data.shape, dtype=int) for hemi in hemi_list}
    
    # Merge definitive + dilated masks
    hemi_mask = np.zeros(mask_data.shape, dtype=int)
    for hemi in hemi_list:
        combined = hemi_mask_definitive[hemi] | hemi_mask_from_dilation[hemi]
        hemi_mask[combined == 1] = hemi_dict[hemi]

    # Step 3: Assign unassigned voxels to nearest hemisphere using distance transform
    voxels_unassigned = (mask_data == 1) & (hemi_mask == 0)
    num_unassigned = np.sum(voxels_unassigned)
    
    if num_unassigned > 0:
        print(f"  Assigning {num_unassigned} unassigned voxels to nearest hemisphere...")
        
        # Calculate distance transform from each hemisphere
        distances = {}
        for hemi in hemi_list:
            hemi_binary = (hemi_mask == hemi_dict[hemi])
            if np.any(hemi_binary):
                # Distance transform gives distance to nearest True voxel
                distances[hemi] = scipy.ndimage.distance_transform_edt(~hemi_binary)
        
        # Assign to closer hemisphere
        if 'rh' in distances and 'lh' in distances:
            assign_to_rh = voxels_unassigned & (distances['rh'] < distances['lh'])
            assign_to_lh = voxels_unassigned & (distances['lh'] <= distances['rh'])
            hemi_mask[assign_to_rh] = hemi_dict['rh']
            hemi_mask[assign_to_lh] = hemi_dict['lh']
            print(f"    Assigned {np.sum(assign_to_rh)} to RH, {np.sum(assign_to_lh)} to LH")
        elif 'rh' in distances:
            hemi_mask[voxels_unassigned] = hemi_dict['rh']
            print(f"    Assigned all {num_unassigned} to RH (LH empty)")
        elif 'lh' in distances:
            hemi_mask[voxels_unassigned] = hemi_dict['lh']
            print(f"    Assigned all {num_unassigned} to LH (RH empty)")
    
    # Final statistics
    rh_count = np.sum(hemi_mask == hemi_dict['rh'])
    lh_count = np.sum(hemi_mask == hemi_dict['lh'])
    print(f"  Final: RH={rh_count:,} voxels, LH={lh_count:,} voxels")
    
    return hemi_mask

