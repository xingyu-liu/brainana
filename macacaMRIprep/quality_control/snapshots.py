"""
Quality Control Snapshot Generation

This module creates visual snapshots for assessing preprocessing quality,
including registration overlays, motion parameter plots, and brain extraction results.
All snapshots are generated using clean, publication-ready visualizations.
"""

import os
import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import nibabel as nib
from pathlib import Path
from typing import Dict, Any, Union, List, Optional
from PIL import Image

from .mri_plotting import (
    create_overlay_grid_3xN, 
    create_motion_plot, 
    create_grid_mri_image
)

# %%
def create_motion_correction_qc(
    motion_params: str,
    save_f: Union[str, Path],
    input_file: Union[str, Path],
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate motion correction quality control plots.
    
    Args:
        motion_params: Path to motion parameters file (.tsv or .par format)
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-motion_bold.png')
        input_file: Path to input file for BIDS-compliant naming (used for fallback naming)
        logger: Logger instance
        **kwargs: Additional arguments
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating motion correction overlay - {output_path}")
    
    try:
        if not os.path.exists(motion_params):
            logger.error(f"Data: motion parameters file not found - {motion_params}")
            return {}
            
        # Load and analyze motion parameters
        # Handle both old .par format (no headers) and new .tsv format (with headers)
        if motion_params.endswith('.tsv'):
            motion_df = pd.read_csv(motion_params, sep='\t')
            # Ensure we have the expected columns in the right order
            expected_cols = ['trans_x', 'trans_y', 'trans_z', 'rot_x', 'rot_y', 'rot_z']
            if all(col in motion_df.columns for col in expected_cols):
                motion_data = motion_df[expected_cols].values
            else:
                logger.warning(f"Data: expected columns {expected_cols} not found in {motion_params} - using all columns")
                motion_data = motion_df.values
        else:
            # Legacy .par format
            motion_data = np.loadtxt(motion_params)
            
        if motion_data.ndim == 1:
            motion_data = motion_data.reshape(1, -1)
            
        # Calculate motion statistics
        trans_rms = np.sqrt(np.mean(motion_data[:, :3]**2, axis=0))
        rot_rms = np.sqrt(np.mean(motion_data[:, 3:]**2, axis=0))
        
        logger.info(f"Data: motion RMS - translation {trans_rms.mean():.3f}mm, rotation {np.degrees(rot_rms.mean()):.3f}°")
        
        # Create motion plot
        fig = create_motion_plot(motion_data, title="")
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logger.info(f"Output: motion QC plot saved - {output_path}")
        return {"motion_plot": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: failed to generate motion overlay - {e}")
        return {}


def create_skullstripping_qc(
    underlay_file: str,
    mask_file: str,
    save_f: Union[str, Path],
    modality: str = "anat",
    num_slices: int = 7,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate skullstripping quality control overlays.
    
    Args:
        underlay_file: Path to underlay image (e.g., T1w brain image)
        mask_file: Path to brain mask file
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-skullStripping_T1w.png')
        modality: Imaging modality ("anat" or "func")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} skullstripping overlay")
    
    try:
        # Validate inputs
        for file_path, name in [(underlay_file, "underlay"), (mask_file, "mask")]:
            if not os.path.exists(file_path):
                logger.error(f"QC: {name} file not found - {os.path.basename(file_path)}")
                return {}
        
        # Create brain extraction overlay (underlay as background, mask contours)
        # Pass file paths directly - let visualization function handle loading
        fig = create_overlay_grid_3xN(
            underlay_file, 
            mask_file,
            num_cols=num_slices,
            title="",
            alpha=0.7,
            underlay_cmap='gray',
            overlay_cmap='Reds',
            num_contour_levels=1,
            show_title=False,
            show_row_labels=False
        )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='black')
        plt.close(fig)
        
        logger.info(f"QC: skullstripping overlay saved - {os.path.basename(output_path)}")
        return {f"{modality}_skullstripping_overlay": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: skullstripping overlay generation failed - {e}")
        return {}


def create_registration_qc(
    image_file: str,
    template_file: str,
    save_f: Union[str, Path],
    modality: str,
    num_slices: int = 7,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate registration quality control overlays.
    
    Args:
        image_file: Path to registered image (underlay)
        template_file: Path to template image (overlay/contours)
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-func2anat_bold.png')
        modality: Registration type ("anat2template", "func2template", "func2anat")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} registration overlay")
    
    try:
        # Validate inputs
        for file_path, name in [(image_file, "image"), (template_file, "template")]:
            if not os.path.exists(file_path):
                logger.error(f"QC: {name} file not found - {os.path.basename(file_path)}")
                return {}
        
        # Create registration overlay (image as underlay, template as contours)
        # Pass file paths directly - let visualization function handle loading and value scaling
        fig = create_overlay_grid_3xN(
            image_file, 
            template_file,
            num_cols=num_slices,
            title="",
            alpha=0.7,
            underlay_cmap='gray',
            overlay_cmap='summer',
            num_contour_levels=6,
            show_title=False,
            show_row_labels=False
        )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='black')
        plt.close(fig)
        
        logger.info(f"QC: registration overlay saved - {os.path.basename(output_path)}")
        return {f"{modality}_registration_overlay": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: failed to generate registration overlay - {e}")
        return {}


def create_bias_correction_qc(
    image_original: str,
    image_corrected: str,
    save_f: Union[str, Path],
    modality: str = "anat",
    num_slices: int = 7,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate bias correction quality control overlays.
    
    Args:
        image_original: Path to original image (before bias correction)
        image_corrected: Path to corrected image (after bias correction)
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-biasCorrection_T1w.png')
        modality: Imaging modality ("anat" or "func")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} bias correction comparison")
    
    try:
        # Validate inputs
        for file_path, name in [(image_original, "original"), (image_corrected, "corrected")]:
            if not os.path.exists(file_path):
                logger.error(f"QC: {name} file not found - {os.path.basename(file_path)}")
                return {}
        
        # Create before/after comparison with two 3xN grids stacked vertically
        # Pass file paths directly - let visualization function handle loading and voxel sizes
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        _create_before_after_comparison(
            image_original, 
            image_corrected,
            num_cols=num_slices,
            perspectives=["axial"],
            save_f=output_path,
            logger=logger
        )
        
        logger.info(f"QC: bias correction comparison saved - {os.path.basename(output_path)}")
        return {f"{modality}_bias_correction_comparison": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: bias correction comparison generation failed - {e}")
        return {}

def _create_before_after_comparison(
    before_data: Union[str, Path, np.ndarray],
    after_data: Union[str, Path, np.ndarray], 
    num_cols: int = 7,
    perspectives: List[str] = ["axial"],
    save_f: Union[str, Path] = None,
    logger: Optional[logging.Logger] = None,
) -> plt.Figure:
    """
    Create a before/after comparison of two images using the generic grid function.
    
    Args:
        before_data: Path to before image or numpy array
        after_data: Path to after image or numpy array
        num_cols: Number of columns (slices per orientation)
        perspectives: List of orientations to show
        
    Returns:
        Matplotlib figure with before/after comparison
    """
    # Common parameters for both figures
    grid_params = {
        'num_cols': num_cols,
        'perspectives': perspectives,
        'figsize_per_col': (3, 3),
        'show_title': False,
        'show_row_labels': False,
        'overlay_data': None,
        'underlay_cmap': 'gray'
    }

    # Create before and after figures
    fig_before = create_grid_mri_image(underlay_data=before_data, **grid_params)
    fig_after = create_grid_mri_image(underlay_data=after_data, **grid_params)
    
    # Add labels to figures and save them as temporary files
    temp_files = []
    saved_images = []
    
    for fig, label in zip([fig_before, fig_after], ["Before", "After"]):
        # Add label to figure
        if fig.axes:
            ax = fig.axes[0]
            ax.text(-0.08, 0.5, label, transform=ax.transAxes,
                   fontsize=12, fontweight='bold', color='white',
                   rotation=90, ha='center', va='center')
        
        # Save figure as temporary file
        temp_file = str(save_f).replace(".png", f"_{label.lower()}.png")
        fig.savefig(temp_file, dpi=150, bbox_inches='tight', facecolor='black')
        temp_files.append(temp_file)
        
        if logger:
            logger.info(f"Output: bias correction QC {label.lower()} saved - {temp_file}")
        
        # Load the saved image
        saved_images.append(Image.open(temp_file))
    
    # Create a new image with combined height
    img_before, img_after = saved_images
    total_width = max(img_before.width, img_after.width)
    total_height = img_before.height + img_after.height
    
    combined_img = Image.new('RGB', (total_width, total_height), color='black')
    combined_img.paste(img_before, (0, 0))
    combined_img.paste(img_after, (0, img_before.height))
    
    # Save the combined image
    combined_img.save(str(save_f), dpi=(150, 150))
    
    if logger:
        logger.info(f"Output: bias correction QC comparison saved - {save_f}")
    
    # Clean up temporary files
    for temp_file in temp_files:
        os.remove(temp_file)
    
    # Close figures
    for fig in [fig_before, fig_after]:
        plt.close(fig)
    
    return None  # Function doesn't need to return a figure anymore

