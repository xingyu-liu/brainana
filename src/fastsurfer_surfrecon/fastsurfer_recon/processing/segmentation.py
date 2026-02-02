"""
Segmentation processing utilities.

Provides functions for:
- White matter segmentation from aseg
- Corpus callosum labeling

Based on original wm_segmentation.py and paint_cc_from_pred.py from FastSurfer.
"""

# Copyright 2019-2025 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from typing import Dict
import logging

import nibabel as nib
import numpy as np
import numpy.typing as npt
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# White Matter Segmentation
# =============================================================================

def load_wm_lut(lut_path: Path) -> Dict[int, int]:
    """
    Load ColorLUT and create aseg_id → wm_id mapping.

    The LUT file should be a TSV with at least 'aseg_id' and 'wm_id' columns.

    Parameters
    ----------
    lut_path : Path
        Path to ColorLUT.tsv file

    Returns
    -------
    Dict[int, int]
        Mapping from aseg_id to wm_id

    Raises
    ------
    FileNotFoundError
        If LUT file doesn't exist
    ValueError
        If required columns are missing
    """
    if not lut_path.exists():
        raise FileNotFoundError(f"ColorLUT file not found: {lut_path}")

    # Load TSV file
    lut_df = pd.read_csv(lut_path, sep='\t', comment='#', engine='python')

    # Verify required columns
    required_cols = ['aseg_id', 'wm_id']
    missing_cols = [col for col in required_cols if col not in lut_df.columns]
    if missing_cols:
        raise ValueError(
            f"ColorLUT is missing required columns: {missing_cols}. "
            f"Found columns: {list(lut_df.columns)}"
        )

    # Convert to numeric, coercing errors to NaN
    lut_df['aseg_id'] = pd.to_numeric(lut_df['aseg_id'], errors='coerce')
    lut_df['wm_id'] = pd.to_numeric(lut_df['wm_id'], errors='coerce')

    # Filter out rows with NaN values
    lut_df = lut_df.dropna(subset=['aseg_id', 'wm_id'])

    # Get unique aseg_id rows
    unique_aseg = lut_df.drop_duplicates(subset=['aseg_id'])

    aseg_to_wm = {}
    for _, row in unique_aseg.iterrows():
        aseg_to_wm[int(row['aseg_id'])] = int(row['wm_id'])

    return aseg_to_wm


def create_wm_segmentation(
    input_seg: npt.ArrayLike,
    aseg_to_wm: Dict[int, int],
) -> np.ndarray:
    """
    Create white matter segmentation by mapping aseg_id to wm_id.

    WM segmentation values:
    - 250: Lateral ventricles
    - 110: Subcortical white matter
    - 0: Background/cerebellum

    Parameters
    ----------
    input_seg : array-like
        Input segmentation with aseg_id values
    aseg_to_wm : Dict[int, int]
        Mapping from aseg_id to wm_id

    Returns
    -------
    np.ndarray
        WM segmentation (uint8)
    """
    input_seg = np.asarray(input_seg)
    wm_seg = np.zeros_like(input_seg, dtype=np.uint8)

    # Get unique aseg_id values (excluding background)
    unique_ids = np.unique(input_seg)
    unique_ids = unique_ids[unique_ids != 0]

    logger.debug(f"Found {len(unique_ids)} unique labels in input")

    # Map each label
    stats = {0: 0, 110: 0, 250: 0}
    unmapped = []

    for aseg_id in unique_ids:
        mask = input_seg == aseg_id
        voxel_count = np.sum(mask)

        if aseg_id in aseg_to_wm:
            wm_id = aseg_to_wm[aseg_id]
            wm_seg[mask] = wm_id
            stats[wm_id] = stats.get(wm_id, 0) + voxel_count
        else:
            unmapped.append(aseg_id)

    logger.info(f"WM segmentation: BG={stats[0]}, WM(110)={stats[110]}, Vent(250)={stats[250]}")
    if unmapped:
        logger.warning(f"Unmapped aseg labels: {unmapped[:10]}{'...' if len(unmapped) > 10 else ''}")

    return wm_seg


def create_wm_from_file(
    input_path: Path,
    output_path: Path,
    lut_path: Path,
) -> None:
    """
    Create WM segmentation from file.

    Parameters
    ----------
    input_path : Path
        Input aseg segmentation file
    output_path : Path
        Output WM segmentation file
    lut_path : Path
        Path to ColorLUT with wm_id column
    """
    logger.info(f"Loading LUT: {lut_path}")
    aseg_to_wm = load_wm_lut(lut_path)

    logger.info(f"Loading segmentation: {input_path}")
    input_img = nib.load(input_path)
    input_seg = np.asarray(input_img.dataobj)

    logger.info("Creating WM segmentation...")
    wm_seg = create_wm_segmentation(input_seg, aseg_to_wm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_img = nib.MGHImage(wm_seg, input_img.affine, input_img.header)
    nib.save(output_img, output_path)
    logger.info(f"Saved: {output_path}")


# =============================================================================
# Corpus Callosum Painting
# =============================================================================

def paint_corpus_callosum(
    target_seg: npt.ArrayLike,
    source_seg: npt.ArrayLike,
) -> np.ndarray:
    """
    Paint corpus callosum labels from source into target segmentation.

    Copies labels 251-255 (CC subdivisions) from source to target.

    Parameters
    ----------
    target_seg : array-like
        Target segmentation (will be modified)
    source_seg : array-like
        Source segmentation containing CC labels

    Returns
    -------
    np.ndarray
        Modified target segmentation with CC labels
    """
    target_seg = np.asarray(target_seg).copy()
    source_seg = np.asarray(source_seg)

    # CC labels are 251-255
    cc_mask = (source_seg >= 251) & (source_seg <= 255)
    cc_voxels = np.sum(cc_mask)

    target_seg[cc_mask] = source_seg[cc_mask]

    logger.info(f"Painted {cc_voxels} CC voxels")
    return target_seg


def paint_cc_from_pred(
    target_path: Path,
    source_path: Path,
    output_path: Path,
) -> None:
    """
    Paint CC from source file into target file.

    Parameters
    ----------
    target_path : Path
        Target segmentation file
    source_path : Path
        Source segmentation file with CC labels
    output_path : Path
        Output file path
    """
    logger.info(f"Loading target: {target_path}")
    target_img = nib.load(target_path)
    target_seg = np.asarray(target_img.dataobj)

    logger.info(f"Loading source (CC): {source_path}")
    source_seg = np.asarray(nib.load(source_path).dataobj)

    logger.info("Painting corpus callosum...")
    result = paint_corpus_callosum(target_seg, source_seg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_img = nib.MGHImage(result, target_img.affine, target_img.header)
    nib.save(output_img, output_path)
    logger.info(f"Saved: {output_path}")

# =============================================================================
# Aseg Processing
# =============================================================================

def reduce_to_aseg(
    aparc_aseg: npt.ArrayLike,
    fix_wm: bool = True,
) -> np.ndarray:
    """
    Reduce aparc+aseg segmentation to aseg labels only.

    Maps cortical labels (1000-2999) back to generic cortex labels (3, 42).

    Parameters
    ----------
    aparc_aseg : array-like
        aparc+aseg segmentation
    fix_wm : bool, default=True
        Fix white matter labels

    Returns
    -------
    np.ndarray
        aseg-only segmentation
    """
    aparc_aseg = np.asarray(aparc_aseg).copy()

    # Map left cortex (1000-1999) to 3
    lh_ctx = (aparc_aseg >= 1000) & (aparc_aseg < 2000)
    aparc_aseg[lh_ctx] = 3

    # Map right cortex (2000-2999) to 42
    rh_ctx = (aparc_aseg >= 2000) & (aparc_aseg < 3000)
    aparc_aseg[rh_ctx] = 42

    logger.info(f"Reduced cortical labels: LH={np.sum(lh_ctx)}, RH={np.sum(rh_ctx)}")

    return aparc_aseg


__all__ = [
    # WM segmentation
    "create_wm_segmentation",
    "create_wm_from_file",
    # Corpus callosum
    "paint_corpus_callosum",
    "paint_cc_from_pred",
    # Note: reduce_to_aseg is kept for potential future use but not exported
    # Note: load_wm_lut is internal to create_wm_from_file
    # Note: paint_cc_from_pred is internal to paint_cc_from_pred
]

