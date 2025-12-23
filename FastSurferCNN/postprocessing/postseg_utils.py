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
from typing import List, Optional

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
        # Pre-compute other hemisphere WM mask once per hemisphere (not per label/island)
        other_wm_mask = np.zeros_like(aseg_data, dtype=bool)
        if other_wm_labels:
            for other_label in other_wm_labels:
                other_wm_mask |= (aseg_data == other_label)
        
        # Pre-compute other hemisphere center of mass once per hemisphere
        other_com = None
        if np.any(other_wm_mask):
            other_com = scipy.ndimage.center_of_mass(other_wm_mask)
            if other_com is not None:
                other_com = np.array(other_com)
        
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
            
            # Pre-compute main body center of mass once per WM label (not per island)
            main_body_mask = (labeled_wm == largest)
            main_com = scipy.ndimage.center_of_mass(main_body_mask)
            if main_com is None:
                continue
            main_com = np.array(main_com)
            
            # Check each island
            for i, component_id in enumerate(unique):
                if component_id == largest:
                    continue
                
                # Get island voxels
                island_mask = (labeled_wm == component_id)
                island_size = np.sum(island_mask)
                
                # Find center of mass of island using efficient scipy function
                island_com = scipy.ndimage.center_of_mass(island_mask)
                if island_com is None:
                    continue
                island_com = np.array(island_com)
                
                # Skip if other hemisphere mask is empty
                if other_com is None:
                    continue
                
                # If island is closer to other hemisphere, flip it to the most common other WM label
                dist_to_main = np.linalg.norm(island_com - main_com)
                dist_to_other = np.linalg.norm(island_com - other_com)
                
                if dist_to_other < dist_to_main:
                    # Use the first other WM label as target
                    target_label = other_wm_labels[0]
                    print(f"    {i+1} / {len(unique)} island (size={island_size}) is closer to other hemisphere, flipping to label {target_label}")
                    aseg_data[island_mask] = target_label
                else:
                    print(f"    {i+1} / {len(unique)} island (size={island_size}) is in the correct hemisphere")
    
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


def create_mask(seg_data: npt.NDArray[int], dnum: int, enum: int, rounds: int = 1, voxel_size: Optional[tuple[float, float, float]] = None) -> npt.NDArray[int]:
    """
    Create brain mask from aseg.
    
    Extract largest component, fill holes, then apply dilation/erosion.
    The process can be repeated multiple rounds for better results.
    
    Strategy for multiple rounds:
    - Intermediate rounds (before the last): Apply closing operation
      (dilate by dnum, then erode by dnum) to smooth the mask.
    - Final round: Apply the specified dilation/erosion (dilate by dnum,
      then erode by enum) for final refinement.
    
    Parameters
    ----------
    seg_data : np.ndarray
        Segmentation data (can be binary or multi-class)
    dnum : int
        Number of dilation iterations
    enum : int
        Number of erosion iterations (applied only in the final round)
    rounds : int, optional
        Number of processing rounds to apply (default: 1)
    voxel_size : Optional[tuple[float, float, float]], optional
        Voxel dimensions in mm (x, y, z). If provided, brain volume in mL will be calculated and printed.
        
    Returns
    -------
    np.ndarray
        Binary mask (1 = brain, 0 = background) with dtype int
    """
    if rounds < 1:
        raise ValueError(f"rounds must be >= 1, got {rounds}")
    
    print(f"Creating mask (dilate {dnum}, erode {enum}, rounds {rounds})...")
    
    # Log input data statistics
    unique_vals = np.unique(seg_data)
    num_unique = len(unique_vals)
    print(f"  Input: shape={seg_data.shape}, dtype={seg_data.dtype}, "
          f"range=[{seg_data.min()}, {seg_data.max()}], "
          f"unique values={num_unique}")
    
    if num_unique == 2 and set(unique_vals) == {0, 1}:
        print(f"  Input is binary (0/1)")
    elif num_unique <= 10:
        print(f"  Input is multi-class with {num_unique} classes")
    else:
        print(f"  Input has {num_unique} unique values (may be continuous/probability map)")
    
    # Get initial mask (before dilation or erosion)
    mask = (seg_data != 0).astype(int)
    initial_voxels = np.sum(mask)
    print(f"  Initial mask: {initial_voxels:,} voxels ({100 * initial_voxels / mask.size:.2f}% of volume)")
    
    for round_idx in range(rounds):
        if rounds > 1:
            print(f"  Round {round_idx + 1}/{rounds}:")

        # 1. Extract largest component and fill holes
        mask = extract_largest_component(mask)
        voxels_after_component = np.sum(mask)
        print(f"    After extracting largest component: {voxels_after_component:,} voxels")
        
        mask = fill_label_holes(mask)
        voxels_after_holes = np.sum(mask)
        print(f"    After filling holes: {voxels_after_holes:,} voxels")
        
        # 2. Apply morphological operations (dilation then erosion)
        # Use padding to avoid boundary effects where dilation is constrained
        # but erosion still applies fully, causing over-erosion
        # Strategy: In intermediate rounds, use closing (dilate+erode by same amount)
        # to smooth the mask. In the final round, use the specified erosion value.
        if round_idx == 0:
            enum_this_round = enum  # Final refinement with specified erosion
        else:
            enum_this_round = dnum  # Closing operation for smoothing

        if dnum > 0 or enum_this_round > 0:
            # Pad by the maximum of dilation/erosion iterations to ensure enough space
            pad_size = max(dnum, enum_this_round)
            
            # Pad the mask (works for any number of dimensions)
            padded_mask = np.pad(mask, pad_size, mode='constant', constant_values=0)
            
            # Apply dilation on padded mask
            if dnum > 0:
                padded_mask = scipy.ndimage.binary_dilation(padded_mask, iterations=dnum)
                voxels_after_dilate = np.sum(padded_mask)
                print(f"    After dilation ({dnum} iterations): {voxels_after_dilate:,} voxels")
            
            # Apply erosion on padded mask
            if enum_this_round > 0:
                padded_mask = scipy.ndimage.binary_erosion(padded_mask, iterations=enum_this_round)
                voxels_after_erode = np.sum(padded_mask)
                if round_idx < rounds - 1:
                    print(f"    After closing erosion ({enum_this_round} iterations): {voxels_after_erode:,} voxels")
                else:
                    print(f"    After final erosion ({enum_this_round} iterations): {voxels_after_erode:,} voxels")
            
            # Crop back to original size using tuple slicing (works for any dimension)
            slices = tuple(slice(pad_size, -pad_size) if pad_size > 0 else slice(None) 
                          for _ in range(mask.ndim))
            mask = padded_mask[slices]
    
    final_voxels = np.sum(mask)
    volume_pct = 100 * final_voxels / mask.size
    print(f"  Final mask: {final_voxels:,} voxels ({volume_pct:.2f}% of volume)", end="")
    
    # Calculate and display brain volume in mL if voxel size is provided
    if voxel_size is not None:
        voxel_volume_mm3 = np.prod(voxel_size)  # mm³ per voxel
        brain_volume_mL = (final_voxels * voxel_volume_mm3) / 1000.0  # Convert mm³ to mL
        print(f" ({brain_volume_mL:.2f} mL)")
    else:
        print()
    
    if final_voxels == 0:
        print("  Warning: Final mask is empty!")
    
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

    # Step 3: Assign unassigned voxels to nearest hemisphere using iterative flood-fill
    # This is much faster than distance transform - we iteratively expand from assigned regions
    voxels_unassigned = (mask_data == 1) & (hemi_mask == 0)
    num_unassigned = np.sum(voxels_unassigned)
    
    if num_unassigned > 0:
        print(f"  Assigning {num_unassigned} unassigned voxels to nearest hemisphere (flood-fill)...")
        
        # Create working masks for each hemisphere (only assigned regions)
        hemi_working = {}
        for hemi in hemi_list:
            hemi_working[hemi] = (hemi_mask == hemi_dict[hemi]).astype(bool)
        
        # Check if both hemispheres exist
        has_rh = np.any(hemi_working['rh'])
        has_lh = np.any(hemi_working['lh'])
        
        if has_rh and has_lh:
            # Iterative flood-fill: expand from each hemisphere until all unassigned voxels are covered
            max_iterations = 200  # Safety limit to prevent infinite loops
            iteration = 0
            num_assigned_rh = 0
            num_assigned_lh = 0
            
            while num_unassigned > 0 and iteration < max_iterations:
                iteration += 1
                
                # Dilate each hemisphere by 1 voxel
                new_rh = scipy.ndimage.binary_dilation(hemi_working['rh'], iterations=1)
                new_lh = scipy.ndimage.binary_dilation(hemi_working['lh'], iterations=1)
                
                # Find newly reached unassigned voxels (not already assigned to either hemisphere)
                new_rh_unassigned = new_rh & voxels_unassigned & ~new_lh
                new_lh_unassigned = new_lh & voxels_unassigned & ~new_rh
                
                # Handle conflicts: if both reach a voxel simultaneously, assign to RH (arbitrary but consistent)
                # This is rare and the flood-fill naturally assigns to nearest hemisphere
                conflicts = new_rh & new_lh & voxels_unassigned
                if np.any(conflicts):
                    new_rh_unassigned = new_rh_unassigned | conflicts
                
                # Update working masks and hemi_mask
                hemi_working['rh'] = hemi_working['rh'] | new_rh_unassigned
                hemi_working['lh'] = hemi_working['lh'] | new_lh_unassigned
                hemi_mask[new_rh_unassigned] = hemi_dict['rh']
                hemi_mask[new_lh_unassigned] = hemi_dict['lh']
                
                # Update unassigned mask
                voxels_unassigned = (mask_data == 1) & (hemi_mask == 0)
                num_unassigned = np.sum(voxels_unassigned)
                
                num_assigned_rh += np.sum(new_rh_unassigned)
                num_assigned_lh += np.sum(new_lh_unassigned)
                
                # Early exit if no progress
                if np.sum(new_rh_unassigned) == 0 and np.sum(new_lh_unassigned) == 0:
                    break
            
            print(f"    Assigned {num_assigned_rh} to RH, {num_assigned_lh} to LH (after {iteration} iterations)")
            if num_unassigned > 0:
                print(f"    Warning: {num_unassigned} voxels remain unassigned")
        elif has_rh:
            # Only RH exists, assign all unassigned to RH
            hemi_mask[voxels_unassigned] = hemi_dict['rh']
            print(f"    Assigned all {num_unassigned} to RH (LH empty)")
        elif has_lh:
            # Only LH exists, assign all unassigned to LH
            hemi_mask[voxels_unassigned] = hemi_dict['lh']
            print(f"    Assigned all {num_unassigned} to LH (RH empty)")
    
    # Final statistics
    rh_count = np.sum(hemi_mask == hemi_dict['rh'])
    lh_count = np.sum(hemi_mask == hemi_dict['lh'])
    print(f"  Final: RH={rh_count:,} voxels, LH={lh_count:,} voxels")
    
    return hemi_mask

