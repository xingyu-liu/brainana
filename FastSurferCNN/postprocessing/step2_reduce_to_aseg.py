#!/usr/bin/env python3
"""
Atlas-Agnostic reduce_to_aseg using ColorLUT aseg_id mapping

Maps labels directly to FreeSurfer aseg IDs according to the aseg_id column in the ColorLUT.
Works with ANY atlas as long as the ColorLUT has region, hemi, and aseg_id columns.

Usage:
    # Basic usage
    python postseg_1_reduce_to_aseg.py -i input.mgz -o output.mgz --lut /path/to/ColorLUT.tsv
    
    # With WM island fixing
    python postseg_1_reduce_to_aseg.py -i input.mgz -o output.mgz --lut /path/to/ColorLUT.tsv --fixwm
    
    # With V1 WM fixing using template registration
    python postseg_1_reduce_to_aseg.py -i input.mgz -o output.mgz --lut /path/to/ColorLUT.tsv \
        --fixv1 --t1w t1w.mgz --mask mask.mgz --hemi_mask hemi_mask.mgz \
        --tpl_t1w template_t1w.nii.gz --tpl_seg template_seg.nii.gz --tpl_wm template_wm.nii.gz
    
    # With mask output
    python postseg_1_reduce_to_aseg.py -i input.mgz -o output.mgz --lut /path/to/ColorLUT.tsv --outmask mask.mgz

Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
Enhanced for atlas-agnostic aseg_id mapping 2024
"""

import optparse
import sys
from pathlib import Path
from typing import Set, Tuple, Dict, List

import nibabel as nib
import numpy as np
import pandas as pd
import scipy.ndimage
from numpy import typing as npt
from skimage.measure import label

# Add parent directory to path for data_loader imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from FastSurferCNN.data_loader.data_utils import read_classes_from_lut


class AtlasInfo:
    """
    Atlas information parsed from extended ColorLUT.
    
    Stores mapping from label IDs to aseg_ids and organizes labels by region type and hemisphere.
    """
    
    def __init__(self, lut_path: Path):
        self.name = "Unknown"
        self.lut_path = lut_path
        
        # Mapping from label ID to aseg_id
        self.label_to_aseg: Dict[int, int] = {}
        
        # Sets of label IDs by region type and hemisphere
        self.lh_cortex_labels: Set[int] = set()
        self.rh_cortex_labels: Set[int] = set()
        self.lh_subcortex_labels: Set[int] = set()
        self.rh_subcortex_labels: Set[int] = set()
        self.lh_wm_labels: Set[int] = set()
        self.rh_wm_labels: Set[int] = set()
        self.lh_csf_labels: Set[int] = set()
        self.rh_csf_labels: Set[int] = set()
        
        # Load from extended LUT
        if lut_path.exists():
            self._parse_from_lut(lut_path)
        else:
            raise FileNotFoundError(f"ColorLUT file not found: {lut_path}")
    
    def _parse_from_lut(self, lut_path: Path):
        """
        Parse atlas info from an extended ColorLUT.
        
        Raises ValueError if LUT doesn't have extended format.
        """
        lut_df = read_classes_from_lut(lut_path)
        
        # Check for extended format columns (case-insensitive)
        # Support both 'Region'/'Hemi' and 'region'/'hemi'
        region_col = None
        hemi_col = None
        aseg_col = None
        
        for col in lut_df.columns:
            if col.lower() == 'region':
                region_col = col
            elif col.lower() == 'hemi':
                hemi_col = col
            elif col.lower() == 'aseg_id':
                aseg_col = col
        
        if region_col is None or hemi_col is None:
            raise ValueError(
                f"ColorLUT {lut_path.name} does not have extended format (missing region/hemi columns). "
                f"Please regenerate the ColorLUT with region and hemi columns."
            )
        
        # Extract atlas name from LUT path
        self.name = lut_path.stem.replace('_ColorLUT', '').replace('ColorLUT', '')
        
        # Create mapping from label ID to aseg_id using vectorized operations
        if aseg_col:
            aseg_valid = lut_df[aseg_col].notna()
            self.label_to_aseg = dict(zip(
                lut_df.loc[aseg_valid, 'ID'].astype(int),
                lut_df.loc[aseg_valid, aseg_col].astype(int)
            ))
        else:
            self.label_to_aseg = {}
        
        # Parse labels by region and hemisphere using vectorized operations
        # Create lowercase columns for filtering
        region_lower = lut_df[region_col].str.lower()
        hemi_lower = lut_df[hemi_col].str.lower()
        
        # Cortex labels
        self.lh_cortex_labels = set(lut_df[(region_lower == 'cortex') & (hemi_lower == 'lh')]['ID'].tolist())
        self.rh_cortex_labels = set(lut_df[(region_lower == 'cortex') & (hemi_lower == 'rh')]['ID'].tolist())
        
        # Subcortex labels
        self.lh_subcortex_labels = set(lut_df[(region_lower == 'subcortex') & (hemi_lower == 'lh')]['ID'].tolist())
        self.rh_subcortex_labels = set(lut_df[(region_lower == 'subcortex') & (hemi_lower == 'rh')]['ID'].tolist())
        
        # WM labels
        self.lh_wm_labels = set(lut_df[(region_lower == 'wm') & (hemi_lower == 'lh')]['ID'].tolist())
        self.rh_wm_labels = set(lut_df[(region_lower == 'wm') & (hemi_lower == 'rh')]['ID'].tolist())
        
        # CSF labels
        self.lh_csf_labels = set(lut_df[(region_lower == 'csf') & (hemi_lower == 'lh')]['ID'].tolist())
        self.rh_csf_labels = set(lut_df[(region_lower == 'csf') & (hemi_lower == 'rh')]['ID'].tolist())
        
        print(f"✓ Loaded atlas info from extended ColorLUT: {lut_path.name}")
        print(f"  Found {len(self.label_to_aseg)} label → aseg_id mappings")
    
    def is_lh_cortex(self, label: int) -> bool:
        """Check if label is left hemisphere cortex."""
        return label in self.lh_cortex_labels
    
    def is_rh_cortex(self, label: int) -> bool:
        """Check if label is right hemisphere cortex."""
        return label in self.rh_cortex_labels
    
    def get_cortex_count(self) -> Tuple[int, int]:
        """Get counts of cortical regions."""
        return len(self.lh_cortex_labels), len(self.rh_cortex_labels)
    
    def print_summary(self):
        """Print atlas summary."""
        print(f"\n{'='*70}")
        print(f"Atlas: {self.name}")
        print(f"{'='*70}")
        
        lh_count, rh_count = self.get_cortex_count()
        
        print(f"\nCortical regions:")
        print(f"  LH: {lh_count} regions")
        if self.lh_cortex_labels:
            lh_sorted = sorted(self.lh_cortex_labels)
            if len(lh_sorted) <= 10:
                print(f"      Labels: {lh_sorted}")
            else:
                print(f"      Labels: {lh_sorted[:5]}...{lh_sorted[-3:]}")
        
        print(f"  RH: {rh_count} regions")
        if self.rh_cortex_labels:
            rh_sorted = sorted(self.rh_cortex_labels)
            if len(rh_sorted) <= 10:
                print(f"      Labels: {rh_sorted}")
            else:
                print(f"      Labels: {rh_sorted[:5]}...{rh_sorted[-3:]}")
        
        subcortex_count = len(self.lh_subcortex_labels) + len(self.rh_subcortex_labels)
        if subcortex_count > 0:
            print(f"\nSubcortical regions: {subcortex_count} total")
        
        print(f"{'='*70}\n")


def reduce_to_aseg(data_inseg: np.ndarray, lut_path: Path, verbose: bool = False) -> np.ndarray:
    """
    Reduce segmentation to FreeSurfer-compatible aseg format using aseg_id from ColorLUT.
    
    Maps each label to its corresponding aseg_id as specified in the ColorLUT.
    This is the most direct and atlas-agnostic approach.
    
    Parameters
    ----------
    data_inseg : np.ndarray
        Input segmentation with atlas-specific labels
    lut_path : Path
        Path to the extended ColorLUT file (must have aseg_id column).
    verbose : bool
        Print progress information
        
    Returns
    -------
    np.ndarray
        FreeSurfer-compatible aseg with labels mapped according to aseg_id
        
    Raises
    ------
    ValueError
        If ColorLUT doesn't have extended format with aseg_id column
    """
    lut_path = Path(lut_path)
    
    # Load from extended LUT
    atlas_info = AtlasInfo(lut_path=lut_path)
    
    if not hasattr(atlas_info, 'label_to_aseg') or not atlas_info.label_to_aseg:
        raise ValueError(
            f"ColorLUT {lut_path.name} does not have aseg_id column. "
            f"Please regenerate the ColorLUT with aseg_id column."
        )
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"Atlas: {atlas_info.name}")
        print(f"{'='*70}")
        print(f"Reducing to FreeSurfer aseg using aseg_id mapping...")
        print(f"Found {len(atlas_info.label_to_aseg)} label → aseg_id mappings")
    
    # Start with zeros
    data_aseg = np.zeros_like(data_inseg, dtype=np.int16)
    
    # Get unique labels in the input (excluding background 0)
    unique_labels = np.unique(data_inseg)
    unique_labels = unique_labels[unique_labels != 0]
    
    # Map each label to its aseg_id
    mapping_stats = {}
    for label_id in unique_labels:
        if label_id in atlas_info.label_to_aseg:
            aseg_id = atlas_info.label_to_aseg[label_id]
            mask = (data_inseg == label_id)
            voxel_count = np.sum(mask)
            data_aseg[mask] = aseg_id
            
            if aseg_id not in mapping_stats:
                mapping_stats[aseg_id] = {'count': 0, 'source_labels': []}
            mapping_stats[aseg_id]['count'] += voxel_count
            mapping_stats[aseg_id]['source_labels'].append(label_id)
        else:
            if verbose:
                print(f"  Warning: Label {label_id} not found in ColorLUT, skipping")
    
    if verbose:
        print(f"\n  Mapping summary:")
        # Sort by aseg_id for clearer output
        for aseg_id in sorted(mapping_stats.keys()):
            stats = mapping_stats[aseg_id]
            source_labels = [int(x) for x in stats['source_labels']]  # Convert to plain Python ints
            count = stats['count']
            if len(source_labels) <= 5:
                source_str = str(source_labels)
            else:
                source_str = f"{source_labels[:3]}...{source_labels[-2:]} ({len(source_labels)} labels)"
            print(f"    aseg_id {aseg_id:3d}: {count:>10,} voxels from {source_str}")
        
        final_labels = [int(x) for x in np.unique(data_aseg[data_aseg != 0])]  # Convert to plain Python ints
        print(f"{'='*70}\n")
    
    return data_aseg


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


def create_mask(aseg_data: npt.NDArray[int], dnum: int, enum: int) -> npt.NDArray[int]:
    """
    Create brain mask from aseg.
    
    Dilate, erode, and select largest component.
    """
    print(f"Creating mask (dilate {dnum}, erode {enum})...")
    
    # Dilate
    aseg_dilate = scipy.ndimage.binary_dilation(aseg_data, iterations=dnum)
    
    # Erode
    aseg_erode = scipy.ndimage.binary_erosion(aseg_dilate, iterations=enum)
    
    # Connected components
    labels, num_labels = label(aseg_erode, return_num=True, connectivity=3)
    
    if num_labels == 0:
        print("⚠️  Warning: No components found in mask")
        return aseg_erode.astype(int)
    
    # Find largest component
    unique, counts = np.unique(labels, return_counts=True)
    if len(counts) == 1:
        largest_component = 1
    else:
        # Exclude background (0)
        largest_component = unique[np.argmax(counts[1:]) + 1]
    
    mask = (labels == largest_component).astype(int)
    print(f"  Kept largest component: {np.sum(mask):,} voxels")
    
    return mask


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


def options_parse():
    """Parse command line options."""
    parser = optparse.OptionParser(
        usage="%prog -i <input> -o <output> --lut <colorlut> [options]",
        description="Atlas-agnostic reduce_to_aseg using ColorLUT with aseg_id mapping"
    )
    
    parser.add_option("-i", "--input", dest="input",
                      help="path to input segmentation", metavar="FILE")
    parser.add_option("-o", "--output", dest="output",
                      help="path to output segmentation", metavar="FILE")
    parser.add_option("--lut", dest="lut",
                      help="path to ColorLUT file (with aseg_id column)", metavar="FILE")
    parser.add_option("--outmask", dest="outmask",
                      help="path to output mask (hemisphere mask will also be generated)", metavar="FILE")
    parser.add_option("--fixwm", dest="fixwm", action="store_true",
                      help="fix disconnected WM islands", default=False)
    parser.add_option("--fixv1", dest="fixv1", action="store_true",
                      help="fix missing thin WM in V1 using template registration", default=False)
    parser.add_option("--t1w", dest="t1w",
                      help="path to T1w image (required for --fixv1)", metavar="FILE")
    parser.add_option("--mask", dest="mask",
                      help="path to brain mask (required for --fixv1)", metavar="FILE")
    parser.add_option("--hemi_mask", dest="hemi_mask",
                      help="path to hemisphere mask (required for --fixv1)", metavar="FILE")
    parser.add_option("--tpl_t1w", dest="tpl_t1w",
                      help="path to template T1w cropped to V1 (required for --fixv1)", metavar="FILE")
    parser.add_option("--tpl_wm", dest="tpl_wm",
                      help="path to template V1 WM probability map (required for --fixv1)", metavar="FILE")
    
    options, args = parser.parse_args()
    
    if not options.input or not options.output or not options.lut:
        parser.error("Options -i/--input, -o/--output, and --lut are required")
    
    if options.fixv1:
        required_v1_opts = ['t1w', 'mask', 'hemi_mask', 'tpl_t1w', 'tpl_wm']
        missing_opts = [opt for opt in required_v1_opts if not getattr(options, opt)]
        if missing_opts:
            parser.error(f"--fixv1 requires these options: {', '.join('--' + opt for opt in missing_opts)}")
    
    return options

def main():
    """Main entry point."""
    options = options_parse()
    
    print("\n" + "="*70)
    print("Atlas-Agnostic reduce_to_aseg using ColorLUT aseg_id mapping")
    print("="*70 + "\n")
    
    # 0. fix V1 if requested
    if options.fixv1:
        from postprocessing.step1_fix_v1_wm import fix_v1_wm
        
        print("Step 0: Fixing V1 WM before reduce_to_aseg...")
        fix_v1_wm(
            seg_f=options.input,
            t1w_f=options.t1w,
            mask_f=options.mask,
            hemi_mask_f=options.hemi_mask,
            lut_path=options.lut,
            tpl_t1w_f=options.tpl_t1w,
            tpl_wm_f=options.tpl_wm,
            roi_name='V1',
            wm_thr=0.5,
            backup_original=True,
            verbose=True
        )

    # Load input
    print(f"Loading: {options.input}")
    img = nib.load(options.input)
    data_atlas = np.asarray(img.dataobj).astype(int)
    
    unique_labels = np.unique(data_atlas)
    print(f"  Shape: {data_atlas.shape}")
    print(f"  Unique labels: {len(unique_labels)}")
    print(f"  Label range: {unique_labels.min()} - {unique_labels.max()}")
    
    # Verify LUT path
    lut_path = Path(options.lut)
    if not lut_path.exists():
        print(f"❌ Error: ColorLUT file not found: {lut_path}")
        sys.exit(1)
    
    print(f"\nUsing ColorLUT: {lut_path}")
    
    # 1. Reduce to aseg
    data_reduced = reduce_to_aseg(data_atlas, lut_path=lut_path, verbose=True)
    
    # 2. Fix WM islands if requested
    if options.fixwm:
        data_reduced = flip_wm_islands_auto(data_reduced, lut_path=lut_path)

    # Save output
    print(f"\nSaving: {options.output}")
    out_img = nib.MGHImage(data_reduced.astype(np.int16), img.affine, img.header)
    nib.save(out_img, options.output)
    
    print("\n" + "="*70)
    print("✅ Done!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()

