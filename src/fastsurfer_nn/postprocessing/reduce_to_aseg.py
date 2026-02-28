#!/usr/bin/env python3
"""
Atlas-Agnostic reduce_to_aseg using ColorLUT aseg_id mapping

Maps labels directly to FreeSurfer aseg IDs according to the aseg_id column in the ColorLUT.
Works with ANY atlas as long as the ColorLUT has region, hemi, and aseg_id columns.

Usage:
    # Basic usage
    python postseg_1_reduce_to_aseg.py -i input.mgz -o output.mgz --lut /path/to/ColorLUT.tsv
    
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
from pathlib import Path
from typing import Set, Tuple, Dict

import nibabel as nib
import numpy as np
import pandas as pd

from fastsurfer_nn.data_loader.data_utils import read_classes_from_lut


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

    # Save output
    print(f"\nSaving: {options.output}")
    out_img = nib.MGHImage(data_reduced.astype(np.int16), img.affine, img.header)
    nib.save(out_img, options.output)
    
    print("\n" + "="*70)
    print("✅ Done!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()

