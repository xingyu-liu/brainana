"""
Visualization utilities for macacaMRIprep.

This module provides tools for visualizing MRI data, including:
- Single slice plotting
- Multi-slice grid plotting
- Overlay visualization
- Motion parameter plotting

General MRI plotting utilities using matplotlib.

This module provides reusable functions for visualizing MRI data including
single images, overlays, grids, and motion parameters. All functions properly
handle image orientation and voxel dimensions from NIfTI headers.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import nibabel as nib
from typing import Optional, Tuple, List, Union
from pathlib import Path


def _load_and_orient_image(image_path: Union[str, Path]) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Load image and get properly oriented data with voxel dimensions.
    
    Args:
        image_path: Path to NIfTI image file
        
    Returns:
        Tuple of (image_data, voxel_sizes, orientation_code)
    """
    try:
        # Load the NIfTI image
        img = nib.load(image_path)
        
        # Get image data and header information
        data = img.get_fdata()
        affine = img.affine
        
        # Get voxel sizes from header
        voxel_sizes = np.array(img.header.get_zooms()[:3])
        
        # Get orientation code from affine matrix  
        axes_codes = nib.aff2axcodes(affine)
        if not isinstance(axes_codes, (list, tuple)):
            raise ValueError(f"aff2axcodes returned unexpected type: {type(axes_codes)}, value: {axes_codes}")
        
        orientation_code = "".join(axes_codes)
        
        # Apply orientation corrections if needed
        # Standard neurological convention is RAS (Right-Anterior-Superior)
        data = _apply_orientation_corrections(data, orientation_code)
        
        return data, voxel_sizes, orientation_code
        
    except Exception as e:
        raise RuntimeError(f"Error loading/orienting image {image_path}: {str(e)}") from e


def _apply_orientation_corrections(data: np.ndarray, orientation_code: str) -> np.ndarray:
    """
    Apply flips and rotations to convert image to RAS+ orientation for display.
    
    Args:
        data: 3D image data
        orientation_code: 3-letter orientation code (e.g., 'RAS', 'LPS')
        
    Returns:
        Corrected image data
    """
    corrected_data = data.copy()
    
    # Apply corrections based on orientation code
    # First character: Left/Right
    if orientation_code[0] == 'L':
        corrected_data = np.flip(corrected_data, axis=0)
    
    # Second character: Posterior/Anterior  
    if orientation_code[1] == 'P':
        corrected_data = np.flip(corrected_data, axis=1)
        
    # Third character: Inferior/Superior
    if orientation_code[2] == 'I':
        corrected_data = np.flip(corrected_data, axis=2)
    
    return corrected_data


def _get_slice_orientations(data: np.ndarray, voxel_sizes: Optional[np.ndarray] = None) -> dict:
    """
    Get slice functions and aspect ratios for different orientations.
    
    Args:
        data: 3D image data
        voxel_sizes: Array of voxel dimensions [x, y, z] in mm. If None, assumes isotropic voxels.
        
    Returns:
        Dictionary with orientation information
    """
    x_dim, y_dim, z_dim = data.shape[:3]
    
    # Use isotropic voxels (1.0 mm) if voxel sizes not provided
    if voxel_sizes is None:
        voxel_sizes = np.array([1.0, 1.0, 1.0])
    
    voxel_x, voxel_y, voxel_z = voxel_sizes[:3]
    
    orientations = {
        'axial': {
            'axis': 2,
            'max_dim': z_dim,
            'slice_func': lambda i: np.rot90(data[:, :, i], k=1),  # 90° counterclockwise
            'aspect': voxel_y / voxel_x
        },
        'sagittal': {
            'axis': 0, 
            'max_dim': x_dim,
            'slice_func': lambda i: np.rot90(data[i, :, :], k=1),  # 90° counterclockwise
            'aspect': voxel_z / voxel_y
        },
        'coronal': {
            'axis': 1,
            'max_dim': y_dim, 
            'slice_func': lambda i: np.rot90(data[:, i, :], k=1),  # 90° counterclockwise
            'aspect': voxel_z / voxel_x
        }
    }
    
    return orientations

def create_grid_mri_image(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Optional[Union[np.ndarray, str, Path]] = None, 
    num_cols: int = 7, 
    perspectives: List[str] = ["axial", "sagittal", "coronal"],
    title: str = "", 
    alpha: float = 0.7,
    underlay_cmap: str = 'gray',
    overlay_color: str = 'limegreen',
    overlay_cmap: Optional[str] = None,
    num_contour_levels: int = 1,
    figsize_per_col: Tuple[int, int] = (3, 3),
    show_title: bool = True,
    show_row_labels: bool = True,
    underlay_vmin: Optional[float] = None,
    underlay_vmax: Optional[float] = None
) -> plt.Figure:
    """
    Create a flexible grid of MRI images with optional overlay and customizable perspectives.
    
    Args:
        underlay_data: 3D underlay image data array or path to NIfTI file
        overlay_data: Optional 3D overlay image data array or path to NIfTI file
        num_cols: Number of columns (slices per orientation)
        perspectives: List of orientations to show (from "axial", "sagittal", "coronal")
        title: Figure title
        alpha: Transparency of overlay contours
        underlay_cmap: Colormap for underlay
        overlay_color: Color for overlay contours (used if overlay_cmap is None)
        overlay_cmap: Colormap for overlay contours (overrides overlay_color)
        num_contour_levels: Number of contour levels for overlay
        figsize_per_col: Size per column in inches (width, height)
        show_title: Whether to show the main title
        show_row_labels: Whether to show orientation labels on rows
        underlay_vmin: Minimum value for underlay intensity scaling
        underlay_vmax: Maximum value for underlay intensity scaling
        
    Returns:
        Matplotlib figure object
    """
    # Handle input - either numpy arrays or file paths
    voxel_sizes = None
    if isinstance(underlay_data, (str, Path)):
        underlay, voxel_sizes, _ = _load_and_orient_image(underlay_data)
    else:
        underlay = underlay_data
        
    # Handle overlay (optional)
    overlay = None
    if overlay_data is not None:
        if isinstance(overlay_data, (str, Path)):
            overlay, overlay_voxel_sizes, _ = _load_and_orient_image(overlay_data)
            # Use overlay voxel sizes if underlay didn't provide them
            if voxel_sizes is None:
                voxel_sizes = overlay_voxel_sizes
        else:
            overlay = overlay_data
    
    # Create figure with dynamic size based on number of perspectives
    num_rows = len(perspectives)
    fig = plt.figure(figsize=(num_cols * figsize_per_col[0], num_rows * figsize_per_col[1]))
    
    # Calculate consistent value range for underlay if not provided
    if underlay_vmin is None or underlay_vmax is None:
        # Use percentile-based scaling to avoid outliers
        underlay_vmin = np.percentile(underlay, 1) if underlay_vmin is None else underlay_vmin
        underlay_vmax = np.percentile(underlay, 99) if underlay_vmax is None else underlay_vmax
    
    # Get orientation information with proper aspect ratios
    all_orientations = _get_slice_orientations(underlay, voxel_sizes)
    
    # Filter orientations based on selected perspectives
    selected_orientations = [(name, all_orientations[name]) for name in perspectives if name in all_orientations]
    orientation_names = [name.capitalize() for name in perspectives]
    
    for row, (orient_name, orient_info) in enumerate(selected_orientations):
        # Calculate N evenly spaced slice indices
        max_dim = orient_info['max_dim']
        # Ensure indices are within bounds [0, max_dim-1]
        start_idx = max(0, int(0.15 * max_dim))
        end_idx = min(max_dim - 1, int(0.85 * max_dim))
        slice_indices = np.linspace(start_idx, end_idx, num_cols, dtype=int)
        
        for col, slice_idx in enumerate(slice_indices):
            ax = plt.subplot(num_rows, num_cols, row * num_cols + col + 1)
            
            # Get the slices
            underlay_slice = orient_info['slice_func'](slice_idx)
            
            # Display underlay with proper aspect ratio and consistent value range
            ax.imshow(underlay_slice, cmap=underlay_cmap, aspect=orient_info['aspect'], 
                     vmin=underlay_vmin, vmax=underlay_vmax)
            
            # Handle overlay contours if overlay is provided
            if overlay is not None:
                # For overlay, we need to use the same slicing pattern with rotation
                if orient_name == 'axial':
                    overlay_slice = np.rot90(overlay[:, :, slice_idx], k=1)
                elif orient_name == 'sagittal':
                    overlay_slice = np.rot90(overlay[slice_idx, :, :], k=1)
                else:  # coronal
                    overlay_slice = np.rot90(overlay[:, slice_idx, :], k=1)
                
                # Create contour overlay 
                # Get contour levels and colors
                # Check if overlay has any non-zero values
                overlay_nonzero = overlay_slice[overlay_slice != 0]
                if len(overlay_nonzero) == 0:
                    # No overlay data to plot, skip contours
                    pass
                else:
                    # set outliers (values < or > 3IQR) to nan
                    q1 = np.percentile(overlay_nonzero, 25)
                    q3 = np.percentile(overlay_nonzero, 75)
                    iqr = q3 - q1
                    if iqr > 0:
                        overlay_slice[overlay_slice < q1 - 3 * iqr] = np.nan
                        overlay_slice[overlay_slice > q3 + 3 * iqr] = np.nan
                    
                    min_val = np.nanmin(overlay_slice)
                    max_val = np.nanmax(overlay_slice)
                    
                    # Check if we have valid values to plot
                    if not (np.isnan(min_val) or np.isnan(max_val)):
                        if num_contour_levels == 1:
                            # Single level - use edge detection approach
                            if overlay_cmap is not None:
                                # Use colormap for single level
                                cmap = plt.colormaps[overlay_cmap]
                                color = cmap(0.5)
                            else:
                                color = overlay_color
                            
                            unique_vals = np.unique(overlay_slice[~np.isnan(overlay_slice)])
                            if len(unique_vals) > 0:
                                if len(unique_vals) == 1:
                                    level = unique_vals[0] * 0.5
                                else:
                                    level = (min_val + max_val) / 2
                                
                                ax.contour(overlay_slice, levels=[level], 
                                            colors=[color], linewidths=2, alpha=alpha)
                        else:
                            # Multiple levels
                            if max_val > min_val:
                                levels = np.linspace(min_val, max_val, num_contour_levels)
                                
                                if overlay_cmap is not None:
                                    # Use colormap for multiple levels
                                    cs = ax.contour(overlay_slice, levels=levels, 
                                                    cmap=overlay_cmap, linewidths=2, alpha=alpha)
                                else:
                                    # Use single color for multiple levels
                                    ax.contour(overlay_slice, levels=levels, 
                                                colors=overlay_color, linewidths=2, alpha=alpha)
            
            ax.axis('off')
            
            # Add orientation label only for the first column
            if col == 0 and show_row_labels:
                ax.text(-0.1, 0.5, orientation_names[row], transform=ax.transAxes,
                       rotation=90, ha='center', va='center', fontsize=12, fontweight='bold')
    
    if title and show_title:
        fig.suptitle(title, fontsize=16, fontweight='bold')
    
    fig.subplots_adjust(hspace=0, wspace=0)
    fig.patch.set_facecolor('black')

    return fig


def create_overlay_grid_3xN(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Union[np.ndarray, str, Path], 
    num_cols: int = 7, 
    **kwargs
) -> plt.Figure:
    """
    Backward compatibility function for create_overlay_grid_3xN.
    Creates a 3xN grid of overlay images (3 orientations, N slices each).
    
    This function calls the new generic create_grid_mri_image function.
    """
    return create_grid_mri_image(
        underlay_data=underlay_data,
        overlay_data=overlay_data,
        num_cols=num_cols,
        perspectives=["axial", "sagittal", "coronal"],
        **kwargs
    )


def create_motion_plot(
    motion_data: np.ndarray,
    title: str = "Head Motion Parameters",
    figsize: Tuple[int, int] = (12, 8)
) -> plt.Figure:
    """
    Create motion parameter plots.
    
    Args:
        motion_data: Motion parameters array (n_timepoints x 6)
                    First 3 columns: translations (mm)
                    Last 3 columns: rotations (radians)
        title: Plot title
        figsize: Figure size
        
    Returns:
        Matplotlib figure object
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)
    
    # Plot translations (mm)
    ax1.plot(motion_data[:, 0], label='X (mm)', color='red')
    ax1.plot(motion_data[:, 1], label='Y (mm)', color='green')
    ax1.plot(motion_data[:, 2], label='Z (mm)', color='blue')
    ax1.set_ylabel('Translation (mm)')
    ax1.set_title(title)
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot rotations (radians to degrees)
    ax2.plot(np.degrees(motion_data[:, 3]), label='X (deg)', color='red')
    ax2.plot(np.degrees(motion_data[:, 4]), label='Y (deg)', color='green')
    ax2.plot(np.degrees(motion_data[:, 5]), label='Z (deg)', color='blue')
    ax2.set_ylabel('Rotation (degrees)')
    ax2.set_xlabel('Volume')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig

