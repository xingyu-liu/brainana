#!/usr/bin/env python3
"""
Atlas-Agnostic reduce_to_aseg using ColorLUT aseg_id mapping

Maps labels directly to FreeSurfer aseg IDs according to the aseg_id column in the ColorLUT.
Works with ANY atlas as long as the ColorLUT has region, hemi, and aseg_id columns.

Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
Enhanced for atlas-agnostic aseg_id mapping 2024
"""

from pathlib import Path
from typing import Set, Tuple, Dict

import numpy as np

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
            if col.lower() == "region":
                region_col = col
            elif col.lower() == "hemi":
                hemi_col = col
            elif col.lower() == "aseg_id":
                aseg_col = col

        if region_col is None or hemi_col is None:
            raise ValueError(
                f"ColorLUT {lut_path.name} does not have extended format (missing region/hemi columns). "
                f"Please regenerate the ColorLUT with region and hemi columns."
            )

        # Extract atlas name from LUT path
        self.name = lut_path.stem.replace("_ColorLUT", "").replace("ColorLUT", "")

        # Create mapping from label ID to aseg_id using vectorized operations
        if aseg_col:
            aseg_valid = lut_df[aseg_col].notna()
            self.label_to_aseg = dict(
                zip(
                    lut_df.loc[aseg_valid, "ID"].astype(int),
                    lut_df.loc[aseg_valid, aseg_col].astype(int),
                )
            )
        else:
            self.label_to_aseg = {}

        # Parse labels by region and hemisphere using vectorized operations
        # Create lowercase columns for filtering
        region_lower = lut_df[region_col].str.lower()
        hemi_lower = lut_df[hemi_col].str.lower()

        # Cortex labels
        self.lh_cortex_labels = set(
            lut_df[(region_lower == "cortex") & (hemi_lower == "lh")]["ID"].tolist()
        )
        self.rh_cortex_labels = set(
            lut_df[(region_lower == "cortex") & (hemi_lower == "rh")]["ID"].tolist()
        )

        # Subcortex labels
        self.lh_subcortex_labels = set(
            lut_df[(region_lower == "subcortex") & (hemi_lower == "lh")]["ID"].tolist()
        )
        self.rh_subcortex_labels = set(
            lut_df[(region_lower == "subcortex") & (hemi_lower == "rh")]["ID"].tolist()
        )

        # WM labels
        self.lh_wm_labels = set(
            lut_df[(region_lower == "wm") & (hemi_lower == "lh")]["ID"].tolist()
        )
        self.rh_wm_labels = set(
            lut_df[(region_lower == "wm") & (hemi_lower == "rh")]["ID"].tolist()
        )

        # CSF labels
        self.lh_csf_labels = set(
            lut_df[(region_lower == "csf") & (hemi_lower == "lh")]["ID"].tolist()
        )
        self.rh_csf_labels = set(
            lut_df[(region_lower == "csf") & (hemi_lower == "rh")]["ID"].tolist()
        )

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

        print("\nCortical regions:")
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


def reduce_to_aseg(
    data_inseg: np.ndarray, lut_path: Path, verbose: bool = False
) -> np.ndarray:
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

    if not hasattr(atlas_info, "label_to_aseg") or not atlas_info.label_to_aseg:
        raise ValueError(
            f"ColorLUT {lut_path.name} does not have aseg_id column. "
            f"Please regenerate the ColorLUT with aseg_id column."
        )

    if verbose:
        print(f"\n{'='*70}")
        print(f"Atlas: {atlas_info.name}")
        print(f"{'='*70}")
        print("Reducing to FreeSurfer aseg using aseg_id mapping...")
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
            mask = data_inseg == label_id
            voxel_count = np.sum(mask)
            data_aseg[mask] = aseg_id

            if aseg_id not in mapping_stats:
                mapping_stats[aseg_id] = {"count": 0, "source_labels": []}
            mapping_stats[aseg_id]["count"] += voxel_count
            mapping_stats[aseg_id]["source_labels"].append(label_id)
        else:
            if verbose:
                print(f"  Warning: Label {label_id} not found in ColorLUT, skipping")

    if verbose:
        print("\n  Mapping summary:")
        # Sort by aseg_id for clearer output
        for aseg_id in sorted(mapping_stats.keys()):
            stats = mapping_stats[aseg_id]
            source_labels = [
                int(x) for x in stats["source_labels"]
            ]  # Convert to plain Python ints
            count = stats["count"]
            if len(source_labels) <= 5:
                source_str = str(source_labels)
            else:
                source_str = f"{source_labels[:3]}...{source_labels[-2:]} ({len(source_labels)} labels)"
            print(f"    aseg_id {aseg_id:3d}: {count:>10,} voxels from {source_str}")

        [
            int(x) for x in np.unique(data_aseg[data_aseg != 0])
        ]  # Convert to plain Python ints
        print(f"{'='*70}\n")

    return data_aseg
