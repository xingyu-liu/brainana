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
import tempfile
import shutil

from .mri_plotting import (
    create_overlay_grid_3xN, 
    create_motion_plot, 
    create_grid_mri_image,
    create_surface_mask_from_mesh,
    create_surface_mask_for_multiple_surfaces,
    _crop_white_space,
    _create_colorbar,
    _create_label_image,
    _find_content_width,
    WHITE_THRESHOLD,
    CROP_PADDING,
    MARGIN_PERCENT,
    SURFACE_SPACING,
    SURFACE_PLOT_SIZE,
    SURFACE_PLOT_ZOOM,
    SURFACE_PLOT_DPI,
    CBAR_DPI,
    CBAR_SPACING,
    CBAR_GRADIENT_WIDTH_RATIO,
    CBAR_TARGET_WIDTH_RATIO,
    CBAR_LABEL_FONTSIZE,
    CBAR_TICK_FONTSIZE,
    CBAR_LABEL_PAD
)

# Try to import surfplot
SURFPLOT_AVAILABLE = False
try:
    from surfplot import Plot
    SURFPLOT_AVAILABLE = True
except (ImportError, ValueError, Exception):
    SURFPLOT_AVAILABLE = False

# %%

def create_conform_qc(
    conformed_file: str,
    template_file: str,
    save_f: Union[str, Path],
    modality: str = "anat",
    num_slices: int = 6,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate conform quality control overlays.
    
    Args:
        conformed_file: Path to conformed image (underlay)
        template_file: Path to resampled template image (overlay/contours)
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-conform_T1w.png')
        modality: Imaging modality ("anat" or "func")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} conform overlay")
    
    try:
        # Validate inputs
        for file_path, name in [(conformed_file, "conformed"), (template_file, "template")]:
            if not os.path.exists(file_path):
                logger.error(f"QC: {name} file not found - {os.path.basename(file_path)}")
                return {}
        
        # Create conform overlay (conformed image as underlay, template as contours with 2 levels)
        # Pass file paths directly - let visualization function handle loading and value scaling
        # Only show axial slices
        fig = create_grid_mri_image(
            underlay_data=conformed_file, 
            overlay_data=template_file,
            num_cols=num_slices,
            perspectives=["axial"],
            title="",
            alpha=0.7,
            underlay_cmap='gray',
            overlay_cmap='summer',
            num_contour_levels=3,
            show_title=False
        )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='black')
        plt.close(fig)
        
        logger.info(f"QC: conform overlay saved - {os.path.basename(output_path)}")
        return {f"{modality}_conform_overlay": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: failed to generate conform overlay - {e}")
        return {}


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
    num_slices: int = 6,
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
            show_title=False
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
    num_slices: int = 6,
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
            show_title=False
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
    num_slices: int = 6,
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

def create_atlas_segmentation_qc(
    underlay_file: str,
    atlas_file: str,
    save_f: Union[str, Path],
    modality: str = "anat",
    num_slices: int = 6,
    logger: Optional[logging.Logger] = None,
    
    **kwargs
) -> Dict[str, str]:
    """
    Generate atlas segmentation quality control overlays with multi-label support.
    
    Args:
        underlay_file: Path to underlay image (e.g., T1w brain image with skull)
        atlas_file: Path to atlas segmentation file (multi-label)
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-atlasSegmentation_T1w.png')
        modality: Imaging modality ("anat" or "func")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} atlas segmentation overlay")
    
    try:
        # Validate inputs
        for file_path, name in [(underlay_file, "underlay"), (atlas_file, "atlas")]:
            if not os.path.exists(file_path):
                logger.error(f"QC: {name} file not found - {os.path.basename(file_path)}")
                return {}
        
        # Default colors for multi-label segmentation
        overlay_colors = ['limegreen', 'red', 'blue', 'yellow', 'magenta', 'cyan', 'orange', 'pink',
                         'purple', 'brown', 'gray', 'olive', 'navy', 'teal', 'coral', 'gold']
        
        # Create atlas segmentation overlay with discrete multi-label contours
        # Use axial slices only for better visualization of multi-label segmentation
        fig = create_grid_mri_image(
            underlay_data=underlay_file,
            overlay_data=atlas_file,
            num_cols=num_slices,
            perspectives=["axial"],  # Only axial slices
            contour_type='discrete',
            overlay_colors=overlay_colors,
            show_legend=False,
            alpha=0.7,
            figsize_per_col=(5, 5),  # Larger subplots for better visibility
            col_margin=1  # Extract extra slices on each side but only display middle num_slices
        )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='black')
        plt.close(fig)
        
        logger.info(f"QC: atlas segmentation overlay saved - {os.path.basename(output_path)}")
        return {f"{modality}_atlas_segmentation_overlay": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: atlas segmentation overlay generation failed - {e}")
        return {}


def _create_before_after_comparison(
    before_data: Union[str, Path, np.ndarray],
    after_data: Union[str, Path, np.ndarray], 
    num_cols: int = 6,
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


def create_surf_recon_tissue_seg_qc(
    fs_subject_dir: Union[str, Path],
    save_f: Union[str, Path],
    modality: str = "anat",
    num_slices: int = 6,
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate surface reconstruction tissue segmentation quality control overlays.
    Creates a 3xN grid showing T1w with white and pial surface contours.
    
    Args:
        fs_subject_dir: Path to FreeSurfer subject directory (e.g., 'fastsurfer/sub-XXX')
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-surfReconTissueSeg_T1w.png')
        modality: Imaging modality ("anat" or "func")
        num_slices: Number of slices per orientation
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    fs_subject_dir = Path(fs_subject_dir)
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} surface reconstruction tissue segmentation overlay")
    
    try:
        # Construct file paths from FreeSurfer directory structure
        surf_dir = fs_subject_dir / "surf"
        mri_dir = fs_subject_dir / "mri"
        
        # Surface files
        white_surf_lh = surf_dir / "lh.smoothwm"
        white_surf_rh = surf_dir / "rh.smoothwm"
        pial_surf_lh = surf_dir / "lh.pial"
        pial_surf_rh = surf_dir / "rh.pial"
        
        # T1w brain file
        t1w_brain_file = mri_dir / "brain.finalsurfs.mgz"
        
        # Validate inputs
        for file_path, name in [
            (t1w_brain_file, "T1w"), 
            (white_surf_lh, "white_lh"), (pial_surf_lh, "pial_lh"), 
            (pial_surf_rh, "pial_rh"), (white_surf_rh, "white_rh")
            
        ]:
            if not file_path.exists():
                logger.error(f"QC: {name} file not found - {file_path}")
                return {}
        
        # Load T1w image
        t1w_brain_img = nib.load(str(t1w_brain_file))
        volume_shape = t1w_brain_img.shape[:3]
        
        # Load surfaces
        logger.info("QC: loading surface meshes...")
        white_lh_verts, white_lh_faces = nib.freesurfer.read_geometry(str(white_surf_lh))
        white_rh_verts, white_rh_faces = nib.freesurfer.read_geometry(str(white_surf_rh))
        pial_lh_verts, pial_lh_faces = nib.freesurfer.read_geometry(str(pial_surf_lh))
        pial_rh_verts, pial_rh_faces = nib.freesurfer.read_geometry(str(pial_surf_rh))
        
        # Create masks from surface meshes
        logger.info("QC: creating masks from surface meshes (rasterization approach)...")
        white_mask = create_surface_mask_for_multiple_surfaces(
            [(white_lh_verts, white_lh_faces), (white_rh_verts, white_rh_faces)],
            t1w_brain_img
        )
        pial_mask = create_surface_mask_for_multiple_surfaces(
            [(pial_lh_verts, pial_lh_faces), (pial_rh_verts, pial_rh_faces)],
            t1w_brain_img
        )
        
        # Combine masks into a single multi-label overlay
        # Label 1 = white surface, Label 2 = pial surface
        # If both overlap, pial (label 2) takes precedence
        logger.info("QC: combining white and pial surface masks...")
        combined_mask = np.zeros(volume_shape, dtype=np.uint8)
        combined_mask[white_mask > 0] = 1
        combined_mask[pial_mask > 0] = 2  # Overwrites white where they overlap
        
        # Create combined surface overlay
        logger.info("QC: creating combined surface overlay...")
        fig = create_grid_mri_image(
            underlay_data=str(t1w_brain_file),
            overlay_data=combined_mask,
            num_cols=num_slices,
            perspectives=["axial", "sagittal", "coronal"],
            overlay_colors=['mediumseagreen', 'mediumpurple'],  # Label 1 (white), Label 2 (pial)
            alpha=0.7,
            num_contour_levels=1,
            show_title=False,
            col_margin=1,
            figsize_per_col=(3, 3),
            contour_linewidth=1.0,
            contour_type='discrete'  # Use discrete for multi-label masks to avoid double lines
        )
        
        # Ensure the parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='black')
        plt.close(fig)
        
        logger.info(f"QC: surface reconstruction tissue segmentation overlay saved - {os.path.basename(output_path)}")
        return {f"{modality}_surf_recon_tissue_seg_overlay": str(output_path)}
        
    except Exception as e:
        logger.error(f"QC: surface reconstruction tissue segmentation overlay generation failed - {e}")
        return {}


def create_cortical_surf_and_measures_qc(
    fs_subject_dir: Union[str, Path],
    save_f: Union[str, Path],
    atlas_name: str = "ARM2",
    modality: str = "anat",
    logger: Optional[logging.Logger] = None,
    **kwargs
) -> Dict[str, str]:
    """
    Generate cortical surface and measures quality control plots.
    Creates surface plots showing different data on three surface types:
    - Row 1: smoothwm with curvature
    - Row 2: pial with segmentation (atlas labels)
    - Row 3: inflated with thickness
    
    Args:
        fs_subject_dir: Path to FreeSurfer subject directory (e.g., 'fastsurfer/sub-XXX')
        atlas_name: Name of the atlas without "atlas" suffix (default: "ARM2", will create "ARM2atlas.mapped.annot")
        save_f: Full path for output file (e.g., 'figures/sub-01_desc-corticalSurfAndMeasures_T1w.png')
        modality: Imaging modality ("anat" or "func")
        logger: Logger instance
        
    Returns:
        Dictionary with snapshot file paths
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    if not SURFPLOT_AVAILABLE:
        logger.warning("QC: surfplot not available, skipping cortical surface and measures QC")
        return {}
    
    fs_subject_dir = Path(fs_subject_dir)
    output_path = Path(save_f)
    logger.info(f"QC: creating {modality} cortical surface and measures plot")
    
    try:
        # Normalize atlas name: remove "atlas" suffix if present (for backward compatibility)
        # Then append "atlas" to match FreeSurferRecon naming convention
        normalized_atlas_name = atlas_name.rstrip("atlas") if atlas_name.endswith("atlas") else atlas_name
        
        # Construct file paths from FreeSurfer directory structure
        surf_dir = fs_subject_dir / "surf"
        label_dir = fs_subject_dir / "label"
        
        # Surface files
        smoothwm_surf_lh = surf_dir / "lh.smoothwm"
        smoothwm_surf_rh = surf_dir / "rh.smoothwm"
        pial_surf_lh = surf_dir / "lh.pial"
        pial_surf_rh = surf_dir / "rh.pial"
        inflated_surf_lh = surf_dir / "lh.inflated"
        inflated_surf_rh = surf_dir / "rh.inflated"
        
        # Data files
        curv_lh = surf_dir / "lh.curv"
        curv_rh = surf_dir / "rh.curv"
        thickness_lh = surf_dir / "lh.thickness"
        thickness_rh = surf_dir / "rh.thickness"
        
        # Annotation files (try mapped version first, then fallback)
        atlas_annot_lh = label_dir / f"lh.aparc.{normalized_atlas_name}atlas.mapped.annot"
        atlas_annot_rh = label_dir / f"rh.aparc.{normalized_atlas_name}atlas.mapped.annot"
        if not atlas_annot_lh.exists():
            atlas_annot_lh = label_dir / f"lh.aparc.{normalized_atlas_name}atlas.annot"
        if not atlas_annot_rh.exists():
            atlas_annot_rh = label_dir / f"rh.aparc.{normalized_atlas_name}atlas.annot"
        
        # Validate inputs
        required_files = [
            (smoothwm_surf_lh, "smoothwm_lh"), (smoothwm_surf_rh, "smoothwm_rh"),
            (pial_surf_lh, "pial_lh"), (pial_surf_rh, "pial_rh"),
            (inflated_surf_lh, "inflated_lh"), (inflated_surf_rh, "inflated_rh"),
            (atlas_annot_lh, "atlas_annot_lh"), (atlas_annot_rh, "atlas_annot_rh"),
            (curv_lh, "curv_lh"), (curv_rh, "curv_rh"),
            (thickness_lh, "thickness_lh"), (thickness_rh, "thickness_rh")
        ]
        
        for file_path, name in required_files:
            if not file_path.exists():
                logger.error(f"QC: {name} file not found - {file_path}")
                return {}
        
        logger.info("QC: loading data files...")
        
        # Load annotations (for pial surface)
        try:
            lh_labels, _, lh_names = nib.freesurfer.read_annot(str(atlas_annot_lh))
            rh_labels, _, rh_names = nib.freesurfer.read_annot(str(atlas_annot_rh))
            logger.info(f"QC: loaded annotations: {len(lh_names)} labels for LH, {len(rh_names)} labels for RH")
        except Exception as e:
            logger.error(f"QC: error loading annotations - {e}")
            return {}
        
        # Load curvature (for smoothwm surface)
        try:
            lh_curv = nib.freesurfer.read_morph_data(str(curv_lh))
            rh_curv = nib.freesurfer.read_morph_data(str(curv_rh))
            logger.info("QC: loaded curvature data")
        except Exception as e:
            logger.error(f"QC: error loading curvature - {e}")
            return {}
        
        # Load thickness (for inflated surface)
        try:
            lh_thickness = nib.freesurfer.read_morph_data(str(thickness_lh))
            rh_thickness = nib.freesurfer.read_morph_data(str(thickness_rh))
            logger.info("QC: loaded thickness data")
        except Exception as e:
            logger.error(f"QC: error loading thickness - {e}")
            return {}
        
        logger.info("QC: creating surface plots...")
        
        # Compute curvature distribution and symmetric range centered at 0
        all_curv = np.concatenate([lh_curv, rh_curv])
        curv_abs_max = max(abs(np.percentile(all_curv, 33)), abs(np.percentile(all_curv, 66)))
        curv_vmin = -curv_abs_max
        curv_vmax = curv_abs_max
        
        # Compute thickness percentiles for clipping
        all_thickness = np.concatenate([lh_thickness, rh_thickness])
        thickness_vmin = np.percentile(all_thickness, 5)
        thickness_vmax = np.percentile(all_thickness, 95)
        
        # Surface types with their surfaces and corresponding data
        surface_configs = [
            ('smoothwm', smoothwm_surf_lh, smoothwm_surf_rh, 'curvature', {'left': lh_curv, 'right': rh_curv}),
            ('pial', pial_surf_lh, pial_surf_rh, 'segmentation', {'left': lh_labels, 'right': rh_labels}),
            ('inflated', inflated_surf_lh, inflated_surf_rh, 'thickness', {'left': lh_thickness, 'right': rh_thickness})
        ]
        
        # Views: (hemisphere, view_name)
        views = [
            ('left', 'lateral'),
            ('left', 'medial'),
            ('right', 'lateral'),
            ('right', 'medial')
        ]
        
        # Create individual plots for each surface type and view combination
        temp_dir = Path(tempfile.mkdtemp())
        temp_images = {}  # Dictionary: (surf_name, hemi, view) -> image_path
        
        try:
            for surf_name, surf_lh, surf_rh, data_type, data_dict in surface_configs:
                logger.info(f"QC: creating {surf_name} surface plots with {data_type}...")
                for hemi, view in views:
                    # Create plot for single hemisphere and view
                    plot_kwargs = {'views': view, 'size': SURFACE_PLOT_SIZE, 'zoom': SURFACE_PLOT_ZOOM}
                    if hemi == 'left':
                        plot_kwargs['surf_lh'] = str(surf_lh)
                        data_key = 'left'
                    else:
                        plot_kwargs['surf_rh'] = str(surf_rh)
                        data_key = 'right'
                    
                    p = Plot(**plot_kwargs)
                    
                    # Add data layer based on surface type
                    if data_type == 'curvature':
                        data = np.clip(data_dict[data_key], curv_vmin, curv_vmax)
                        p.add_layer({data_key: data}, cmap='coolwarm_r', cbar=False)
                    elif data_type == 'segmentation':
                        p.add_layer({data_key: data_dict[data_key]}, cmap='tab20', cbar=False)
                    else:  # thickness
                        data = np.clip(data_dict[data_key], thickness_vmin, thickness_vmax)
                        p.add_layer({data_key: data}, cmap='viridis', cbar=False)
                    
                    fig = p.build()
                    temp_path = Path(temp_dir) / f"{surf_name}_{hemi}_{view}.png"
                    fig.savefig(temp_path, dpi=SURFACE_PLOT_DPI, bbox_inches='tight', pad_inches=0.05, facecolor='white')
                    temp_images[(surf_name, hemi, view)] = temp_path
                    plt.close(fig)
            
            # Load and combine images
            logger.info("QC: combining images...")
            
            # Load all images and crop white space
            loaded_images = []
            for surf_name, _, _, _, _ in surface_configs:
                row_images = []
                for hemi, view in views:
                    img = Image.open(temp_images[(surf_name, hemi, view)])
                    img = _crop_white_space(img)
                    row_images.append(img)
                loaded_images.append(row_images)
            
            # Get dimensions - use the maximum width and height from all images
            max_width = max(img.width for row in loaded_images for img in row)
            max_height = max(img.height for row in loaded_images for img in row)
            
            # Create colorbars for curvature (row 0), parcellation label (row 1), and thickness (row 2)
            cbar_target_width = int(max_width * CBAR_TARGET_WIDTH_RATIO)
            cbar_height = max_height
            cbar_fig_width_inches = cbar_target_width / CBAR_DPI
            cbar_fig_height_inches = cbar_height / CBAR_DPI
            
            # Create colorbars using helper functions
            curv_cbar_img = _create_colorbar(
                cmap='coolwarm_r',
                vmin=curv_vmin,
                vmax=curv_vmax,
                label='Curvature',
                fig_width_inches=cbar_fig_width_inches,
                fig_height_inches=cbar_fig_height_inches,
                dpi=CBAR_DPI,
                gradient_width_ratio=CBAR_GRADIENT_WIDTH_RATIO,
                temp_dir=temp_dir
            )
            
            thickness_cbar_img = _create_colorbar(
                cmap='viridis',
                vmin=thickness_vmin,
                vmax=thickness_vmax,
                label='Thickness (mm)',
                fig_width_inches=cbar_fig_width_inches,
                fig_height_inches=cbar_fig_height_inches,
                dpi=CBAR_DPI,
                gradient_width_ratio=CBAR_GRADIENT_WIDTH_RATIO,
                temp_dir=temp_dir
            )
            
            parcellation_label_img = _create_label_image(
                label='Parcellation',
                fig_width_inches=cbar_fig_width_inches,
                fig_height_inches=cbar_fig_height_inches,
                dpi=CBAR_DPI,
                gradient_width_ratio=CBAR_GRADIENT_WIDTH_RATIO,
                temp_dir=temp_dir
            )
            
            base_height = max_height * 3 + SURFACE_SPACING * 2
            
            # Create surface area image (4 columns)
            surface_area_width = 4 * max_width + 3 * SURFACE_SPACING
            surface_img = Image.new('RGB', (surface_area_width + 50, base_height), 'white')
            
            # Paste all surface images into the surface area image
            for row_idx, row_images in enumerate(loaded_images):
                for col_idx, img in enumerate(row_images):
                    img_to_paste = img.copy()
                    
                    # Crop from center if too wide
                    if img_to_paste.width > max_width:
                        excess = img_to_paste.width - max_width
                        img_to_paste = img_to_paste.crop((excess // 2, 0, excess // 2 + max_width, img_to_paste.height))
                    
                    x_pos = col_idx * (max_width + SURFACE_SPACING) + (max_width - img_to_paste.width) // 2
                    y_pos = row_idx * (max_height + SURFACE_SPACING) + (max_height - img_to_paste.height) // 2
                    surface_img.paste(img_to_paste, (x_pos, y_pos))
            
            # Find actual right edge of surface content
            actual_surface_width = _find_content_width(surface_img)
            
            # Create colorbar area image (no white blank space on right)
            left_cbar_width = max(curv_cbar_img.width, parcellation_label_img.width, thickness_cbar_img.width)
            cbar_area_width = left_cbar_width
            cbar_area_img = Image.new('RGB', (cbar_area_width, base_height), 'white')
            
            # Paste colorbars: left side for all labels (aligned)
            max_cbar_height = max(curv_cbar_img.height, parcellation_label_img.height, thickness_cbar_img.height)
            cbar_images = [curv_cbar_img, parcellation_label_img, thickness_cbar_img]
            for row_idx, cbar_img in enumerate(cbar_images):
                cbar_y_pos = row_idx * (max_height + SURFACE_SPACING) + (max_height - max_cbar_height) // 2
                cbar_area_img.paste(cbar_img, (0, cbar_y_pos))
            
            # Crop surface image and create final combined image
            if actual_surface_width < surface_img.width:
                surface_img = surface_img.crop((0, 0, actual_surface_width, surface_img.height))
            
            actual_base_width = actual_surface_width + CBAR_SPACING + cbar_area_width
            actual_margin_x = int(actual_base_width * MARGIN_PERCENT)
            actual_margin_y = int(base_height * MARGIN_PERCENT)
            combined_img = Image.new('RGB', (actual_base_width + 2 * actual_margin_x, base_height + 2 * actual_margin_y), 'white')
            
            combined_img.paste(surface_img, (actual_margin_x, actual_margin_y))
            combined_img.paste(cbar_area_img, (actual_margin_x + actual_surface_width + CBAR_SPACING, actual_margin_y))
            
            # Save combined image
            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined_img.save(output_path, dpi=(150, 150))
            logger.info(f"QC: cortical surface and measures plot saved - {os.path.basename(output_path)}")
            
            return {f"{modality}_cortical_surf_and_measures_overlay": str(output_path)}
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        logger.error(f"QC: cortical surface and measures plot generation failed - {e}")
        return {}

