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

# %%
import numpy as np
import matplotlib.pyplot as plt
import nibabel as nib
from typing import Optional, Tuple, List, Union, Set
from pathlib import Path
from PIL import Image
from ..utils.mri import get_opposite_orientation, get_image_orientation_from_affine

# %%
def _load_image(image_path: Union[str, Path]) -> Tuple[np.ndarray, np.ndarray, str]:
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
        orientation_code = get_image_orientation_from_affine(affine)
        
        return data, voxel_sizes, orientation_code
        
    except Exception as e:
        raise RuntimeError(f"Error loading/orienting image {image_path}: {str(e)}") from e


def _get_slice_orientations(data: np.ndarray, voxel_sizes: Optional[np.ndarray] = None, 
                           orientation_code: Optional[str] = None) -> dict:
    """
    Get slice functions and aspect ratios for different orientations.
    Determines which axis to slice based on orientation_code.
    
    Args:
        data: 3D image data
        voxel_sizes: Array of voxel dimensions [x, y, z] in mm. If None, assumes isotropic voxels.
        orientation_code: 3-letter orientation code from NIfTI (e.g., 'RAS', 'LPS'). 
                         If None, defaults to RAS.
        
    Returns:
        Dictionary with orientation information
    """
    x_dim, y_dim, z_dim = data.shape[:3]
    
    # Use isotropic voxels (1.0 mm) if voxel sizes not provided
    if voxel_sizes is None:
        voxel_sizes = np.array([1.0, 1.0, 1.0])
    
    voxel_x, voxel_y, voxel_z = voxel_sizes[:3]
    
    # Default to RAS if orientation_code not provided
    if orientation_code is None or len(orientation_code) != 3:
        orientation_code = 'RAS'
    
    # Find which axis corresponds to each direction
    # orientation_code[i] tells us what direction axis i points
    si_axis = None  # Superior-Inferior axis (for axial slices)
    ap_axis = None  # Anterior-Posterior axis (for coronal slices)
    lr_axis = None  # Left-Right axis (for sagittal slices)
    
    for i, direction in enumerate(orientation_code):
        if direction in ['S', 'I']:
            si_axis = i
        elif direction in ['A', 'P']:
            ap_axis = i
        elif direction in ['L', 'R']:
            lr_axis = i
    
    # Default to RAS if axes not found
    if si_axis is None:
        si_axis = 2
    if ap_axis is None:
        ap_axis = 1
    if lr_axis is None:
        lr_axis = 0
    
    # Determine which axes are shown in each slice (the two axes perpendicular to slice axis)
    def get_slice_info(slice_axis, max_dim, dims):
        """Get slice information for a given slice axis."""
        # The two axes shown in the slice are the ones not being sliced
        shown_axes = [i for i in range(3) if i != slice_axis]
        axis0_idx, axis1_idx = shown_axes[0], shown_axes[1]
        
        # Create slice function based on which axis we're slicing
        if slice_axis == 0:
            slice_func = lambda i: data[i, :, :]
        elif slice_axis == 1:
            slice_func = lambda i: data[:, i, :]
        else:  # slice_axis == 2
            slice_func = lambda i: data[:, :, i]
        
        # Calculate aspect ratio based on voxel sizes of shown axes
        # aspect = dy/dx where dy is the unit size in y-direction (rows, axis0) 
        # and dx is the unit size in x-direction (cols, axis1)
        # In imshow: rows (axis0) are y-axis, cols (axis1) are x-axis
        aspect = voxel_sizes[axis0_idx] / voxel_sizes[axis1_idx]
        
        return {
            'axis': slice_axis,
            'max_dim': max_dim,
            'slice_func': slice_func,
            'aspect': aspect,
            'shown_axes': (axis0_idx, axis1_idx)  # axes shown in the 2D slice
        }
    
    orientations = {
        'axial': get_slice_info(si_axis, data.shape[si_axis], (x_dim, y_dim, z_dim)),
        'sagittal': get_slice_info(lr_axis, data.shape[lr_axis], (x_dim, y_dim, z_dim)),
        'coronal': get_slice_info(ap_axis, data.shape[ap_axis], (x_dim, y_dim, z_dim))
    }
    
    return orientations


def _get_rotation_for_perspective(perspective: str, orientation_code: str, shown_axes: Tuple[int, int]) -> int:
    """
    Determine the rotation (in 90-degree steps, counterclockwise) needed to orient
    the slice so that the desired direction is at the top.
    
    Requirements:
    - Axial: A (Anterior) should be at top
    - Sagittal: S (Superior) should be at top
    - Coronal: S (Superior) should be at top
    
    Args:
        perspective: One of 'axial', 'sagittal', 'coronal'
        orientation_code: 3-letter orientation code from NIfTI
        shown_axes: Tuple of (axis0_idx, axis1_idx) indicating which axes are shown
        
    Returns:
        Number of 90-degree counterclockwise rotations needed (0, 1, 2, or 3)
    """
    if len(orientation_code) != 3:
        orientation_code = 'RAS'  # Fallback
    
    axis0_idx, axis1_idx = shown_axes
    axis0_dir = orientation_code[axis0_idx]  # direction of axis shown as rows
    axis1_dir = orientation_code[axis1_idx]  # direction of axis shown as cols
    
    # Determine what direction is currently at the top (row 0)
    current_top = get_opposite_orientation(axis0_dir)
    
    # Determine what direction should be at the top
    if perspective == 'axial':
        desired_top = 'A'
    elif perspective == 'sagittal':
        desired_top = 'S'
    else:  # coronal
        desired_top = 'S'
    
    # If already correct, no rotation needed
    if current_top == desired_top:
        return 0
    
    # Check if desired_top is in the slice (either as axis0_dir, opposite(axis0_dir), axis1_dir, or opposite(axis1_dir))
    possible_directions = {
        'top': current_top,
        'bottom': axis0_dir,
        'left': get_opposite_orientation(axis1_dir),
        'right': axis1_dir
    }
    
    # Find where desired_top currently is
    current_position = None
    for pos, direction in possible_directions.items():
        if direction == desired_top:
            current_position = pos
            break
    
    if current_position is None:
        # Desired direction not found in slice, return 0 (no rotation)
        return 0
    
    # Map current position to rotation needed to move it to top
    # Rotations are counterclockwise: 0=no rotation, 1=90°, 2=180°, 3=270°
    rotation_map = {
        'top': 0,      # Already at top
        'right': 1,    # Rotate 90° CCW to move right to top
        'bottom': 2,   # Rotate 180° to move bottom to top
        'left': 3      # Rotate 270° CCW (or -90° CW) to move left to top
    }
    
    return rotation_map.get(current_position, 0)


def _plot_labeled_data(ax, data_slice: np.ndarray, label_to_color: dict, 
                      plot_type: str = 'contour', alpha: float = 0.7, 
                      linewidth: float = 1.5) -> List[Tuple[int, str]]:
    """
    Plot multi-label segmentation data with different colors for each label.
    Uses a consistent label-to-color mapping to ensure same label gets same color across slices.
    
    Args:
        ax: Matplotlib axis
        data_slice: 2D slice of segmentation data (integer labels)
        label_to_color: Dictionary mapping label_value -> color (ensures consistency)
        plot_type: 'contour' for line contours, 'overlay' for filled
        alpha: Transparency
        
    Returns:
        List of (label_value, color) tuples for legend
    """
    # Force data to int and get unique non-zero labels
    data_slice = data_slice.astype(int)
    unique_labels = np.unique(data_slice[data_slice != 0])
    
    plotted_labels = []
    for label_val in unique_labels:
        # Use consistent color mapping
        color = label_to_color.get(label_val)
        if color is None:
            continue  # Skip if label not in mapping
        
        mask = (data_slice == label_val).astype(float)
        
        if plot_type == 'overlay':
            # Filled contour for overlay
            ax.contourf(mask, levels=[0.5, 1.5], colors=[color], alpha=alpha)
        elif plot_type == 'contour':
            # Line contour only
            ax.contour(mask, levels=[0.5], colors=[color], linewidths=linewidth, alpha=alpha)
        
        plotted_labels.append((label_val, color))
    
    return plotted_labels


def _get_anatomical_labels(perspective: str, orientation_code: str, shown_axes: Tuple[int, int], rotation: int = 0) -> dict:
    """
    Get anatomical direction labels for each perspective based on NIfTI orientation code.
    
    Uses shown_axes to determine which axes are displayed in the 2D slice, then maps
    their directions to display positions based on NIfTI convention.
    
    In NIfTI convention, orientation_code[i] tells us what direction axis i points
    when index INCREASES. Therefore:
    - Low index (0) = opposite direction
    - High index (N-1) = same direction
    
    In 2D slice displayed with matplotlib imshow:
    - Rows go top to bottom: row 0 = top, row N-1 = bottom
    - Cols go left to right: col 0 = left, col M-1 = right
    
    Therefore, the actual directions at each display position are:
    - Top (row 0) = opposite(axis0_dir)
    - Bottom (row N-1) = axis0_dir
    - Left (col 0) = opposite(axis1_dir)
    - Right (col M-1) = axis1_dir
    
    The labels should indicate what anatomical direction is actually at each position.
    
    Args:
        perspective: One of 'axial', 'sagittal', 'coronal'
        orientation_code: 3-letter orientation code from NIfTI (e.g., 'RAS', 'LPS', 'RSA')
        shown_axes: Tuple of (axis0_idx, axis1_idx) indicating which axes are shown in the slice
                   axis0_idx corresponds to rows, axis1_idx corresponds to cols
        
    Returns:
        Dictionary with 'top', 'bottom', 'left', 'right' labels
    """
    if len(orientation_code) != 3:
        orientation_code = 'RAS'  # Fallback
    
    # Get directions of the shown axes
    axis0_idx, axis1_idx = shown_axes
    axis0_dir = orientation_code[axis0_idx]  # direction of axis shown as rows
    axis1_dir = orientation_code[axis1_idx]  # direction of axis shown as cols
    
    # First, determine what direction is actually at each display position
    # based on NIfTI convention (low index = opposite, high index = same)
    # Before rotation:
    actual_top_before = get_opposite_orientation(axis0_dir)      # row 0 = opposite of axis0 direction
    actual_bottom_before = axis0_dir                 # row N-1 = same as axis0 direction
    actual_left_before = get_opposite_orientation(axis1_dir)    # col 0 = opposite of axis1 direction
    actual_right_before = axis1_dir                  # col M-1 = same as axis1 direction
    
    # Apply rotation: each 90° CCW rotation moves directions counterclockwise around the display
    # rotation 0: top, right, bottom, left stay the same
    # rotation 1: right -> top, bottom -> right, left -> bottom, top -> left
    # rotation 2: bottom -> top, left -> right, top -> bottom, right -> left
    # rotation 3: left -> top, top -> right, right -> bottom, bottom -> left
    # Original order: [top, right, bottom, left]
    # After rotation k: [right, bottom, left, top] for k=1, etc.
    directions = [actual_top_before, actual_right_before, actual_bottom_before, actual_left_before]
    if rotation > 0:
        rotated_directions = directions[rotation:] + directions[:rotation]
    else:
        rotated_directions = directions
    
    return {
        'top': rotated_directions[0],
        'right': rotated_directions[1],
        'bottom': rotated_directions[2],
        'left': rotated_directions[3]
    }


def create_grid_mri_image(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Optional[Union[np.ndarray, str, Path]] = None, 
    num_cols: int = 7, 
    perspectives: List[str] = ["axial", "sagittal", "coronal"],
    title: str = "", 
    alpha: float = 0.7,
    underlay_cmap: str = 'gray',
    overlay_color: str = 'limegreen',  # For backward compatibility
    overlay_colors: Optional[List[str]] = None,  # For multi-label segmentation
    overlay_cmap: Optional[str] = None,
    num_contour_levels: int = 1,
    figsize_per_col: Tuple[int, int] = (3, 3),
    show_title: bool = True,
    underlay_vmin: Optional[float] = None,
    underlay_vmax: Optional[float] = None,
    contour_type: str = 'continuous',  # 'discrete' or 'continuous'
    show_legend: bool = False,  # Show legend for multi-label segmentation
    show_row_labels: bool = False,  # Show orientation names on left
    col_margin: int = 0,  # Extract extra slices on each side but only display middle num_cols
    contour_linewidth: float = 1.5  # Line width for contour overlays
) -> plt.Figure:
    """
    Create a flexible grid of MRI images with optional overlay and customizable perspectives.
    Supports multi-label segmentation with automatic color assignment.
    
    Args:
        underlay_data: 3D underlay image data array or path to NIfTI file
        overlay_data: Optional 3D overlay image data array or path to NIfTI file
        num_cols: Number of columns (slices per orientation)
        perspectives: List of orientations to show (from "axial", "sagittal", "coronal")
        title: Figure title
        alpha: Transparency of overlay contours
        underlay_cmap: Colormap for underlay
        overlay_color: Color for single-color overlay (backward compatibility)
        overlay_colors: List of colors for multi-label segmentation (required if contour_type='discrete')
        overlay_cmap: Colormap for continuous overlay (overrides overlay_color)
        num_contour_levels: Number of contour levels for continuous overlay
        figsize_per_col: Size per column in inches (width, height)
        show_title: Whether to show the main title
        underlay_vmin: Minimum value for underlay intensity scaling
        underlay_vmax: Maximum value for underlay intensity scaling
        contour_type: 'discrete' (integer labels) or 'continuous'
        show_legend: Whether to show legend for multi-label segmentation
        show_row_labels: Whether to show orientation names on left side
        col_margin: Extract extra slices on each side (total slices = num_cols + 2*col_margin), 
                   but only display the middle num_cols slices
        
    Returns:
        Matplotlib figure object
    """
    # Handle input - either numpy arrays or file paths
    voxel_sizes = None
    orientation_code = None
    has_file_path = False
    if isinstance(underlay_data, (str, Path)):
        underlay, voxel_sizes, orientation_code = _load_image(underlay_data)
        # if 4d, get tmean image
        if underlay.ndim == 4:
            underlay = np.nanmean(underlay, axis=-1)
        has_file_path = True
    else:
        underlay = underlay_data
        
    # Handle overlay (optional)
    overlay = None
    if overlay_data is not None:
        if isinstance(overlay_data, (str, Path)):
            overlay, overlay_voxel_sizes, overlay_orientation_code = _load_image(overlay_data)
            # if 4d, get tmean image
            if overlay.ndim == 4:
                overlay = np.nanmean(overlay, axis=-1)
            # Use overlay voxel sizes if underlay didn't provide them
            if voxel_sizes is None:
                voxel_sizes = overlay_voxel_sizes
            # Use overlay orientation code if underlay didn't provide it
            if orientation_code is None:
                orientation_code = overlay_orientation_code
            has_file_path = True
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
    all_orientations = _get_slice_orientations(underlay, voxel_sizes, orientation_code)
    
    # Filter orientations based on selected perspectives
    selected_orientations = [(name, all_orientations[name]) for name in perspectives if name in all_orientations]
    orientation_names = [name.capitalize() for name in perspectives]
    
    # Collect labels for legend (only from first slice)
    all_overlay_labels = []
    
    # Pre-compute consistent label-to-color mapping for discrete overlays
    # This ensures the same label gets the same color across all slices
    label_to_color_map = {}
    if overlay is not None and contour_type == 'discrete':
        if overlay_colors is None:
            raise ValueError("overlay_colors must be provided when contour_type='discrete'")
        # Get all unique labels from the entire overlay volume
        all_unique_labels = np.unique(overlay[overlay != 0])
        # Sort labels to ensure consistent ordering
        all_unique_labels = np.sort(all_unique_labels)
        # Create mapping: label_value -> color
        for i, label_val in enumerate(all_unique_labels):
            label_to_color_map[int(label_val)] = overlay_colors[i % len(overlay_colors)]
    
    # Helper function to create oriented slice (reused for consistency)
    def create_oriented_slice(data, orient_info, slice_idx, rotation):
        """Extract and rotate slice consistently."""
        slice_axis = orient_info['axis']
        if slice_axis == 0:
            slice_data = data[slice_idx, :, :]
        elif slice_axis == 1:
            slice_data = data[:, slice_idx, :]
        else:  # slice_axis == 2
            slice_data = data[:, :, slice_idx]
        
        # Apply the same rotation as underlay
        if rotation > 0:
            slice_data = np.rot90(slice_data, k=rotation)
        
        return slice_data
    
    for row, (orient_name, orient_info) in enumerate(selected_orientations):
        # Calculate rotation needed to orient slice correctly
        rotation = 0
        if has_file_path and orientation_code is not None:
            shown_axes = orient_info.get('shown_axes', (0, 1))
            rotation = _get_rotation_for_perspective(orient_name, orientation_code, shown_axes)
        
        # Calculate slice indices with margin
        max_dim = orient_info['max_dim']
        # Total slices to extract: num_cols + 2*col_margin
        total_slices = num_cols + 2 * col_margin
        # Ensure indices are within bounds [0, max_dim-1]
        start_idx = max(0, int(0.15 * max_dim))
        end_idx = min(max_dim - 1, int(0.85 * max_dim))
        # Extract all slices (including margins)
        all_slice_indices = np.linspace(start_idx, end_idx, total_slices, dtype=int)
        # Only display the middle num_cols slices (skip margin slices on each side)
        slice_indices = all_slice_indices[col_margin:col_margin + num_cols]
        
        # Adjust aspect ratio if rotation is 90° or 270° (swaps rows/cols)
        # After rotation, the row/col dimensions are swapped, so aspect ratio is inverted
        aspect = orient_info['aspect']
        if rotation in [1, 3]:
            aspect = 1.0 / aspect if aspect != 0 else 1.0
        
        for col, slice_idx in enumerate(slice_indices):
            ax = plt.subplot(num_rows, num_cols, row * num_cols + col + 1)
            
            # Get the slices
            underlay_slice = orient_info['slice_func'](slice_idx)
            
            # Apply rotation to orient correctly
            if rotation > 0:
                underlay_slice = np.rot90(underlay_slice, k=rotation)
            
            # Display underlay with proper aspect ratio and consistent value range
            ax.imshow(underlay_slice, cmap=underlay_cmap, aspect=aspect, 
                     vmin=underlay_vmin, vmax=underlay_vmax)
            
            # Handle overlay contours if overlay is provided
            if overlay is not None:
                overlay_slice = create_oriented_slice(overlay, orient_info, slice_idx, rotation)
                
                # Check if overlay has any non-zero values
                overlay_nonzero = overlay_slice[overlay_slice != 0]
                if len(overlay_nonzero) == 0:
                    # No overlay data to plot, skip contours
                    pass
                else:
                    # Determine if this is discrete or continuous
                    is_discrete = (contour_type == 'discrete')
                    
                    if is_discrete:
                        # Multi-label segmentation: plot each label with consistent color mapping
                        plotted_labels = _plot_labeled_data(ax, overlay_slice, label_to_color_map, 
                                                           plot_type='contour', alpha=alpha, 
                                                           linewidth=contour_linewidth)
                        # Collect labels for legend (only from first slice to avoid duplicates)
                        if row == 0 and col == 0:
                            all_overlay_labels = plotted_labels
                    else:
                        # Continuous overlay: use original approach
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
                                                colors=[color], linewidths=contour_linewidth, alpha=alpha)
                            else:
                                # Multiple levels
                                if max_val > min_val:
                                    levels = np.linspace(min_val, max_val, num_contour_levels)
                                    
                                    if overlay_cmap is not None:
                                        # Use colormap for multiple levels
                                        cs = ax.contour(overlay_slice, levels=levels, 
                                                        cmap=overlay_cmap, linewidths=contour_linewidth, alpha=alpha)
                                    else:
                                        # Use single color for multiple levels
                                        ax.contour(overlay_slice, levels=levels, 
                                                    colors=overlay_color, linewidths=contour_linewidth, alpha=alpha)
            
            ax.axis('off')
            
            # Add orientation label only for the first column
            if col == 0 and show_row_labels:
                ax.text(-0.1, 0.5, orientation_names[row], transform=ax.transAxes,
                       rotation=90, ha='center', va='center', fontsize=12, fontweight='bold',
                       color='greenyellow')
            
            # Add anatomical direction labels on middle subplot of each row when file path is provided
            middle_col = num_cols // 2
            if col == middle_col and has_file_path and orientation_code is not None:
                shown_axes = orient_info.get('shown_axes', (0, 1))
                labels = _get_anatomical_labels(orient_name, orientation_code, shown_axes, rotation)
                # Top label (5% margin from top)
                ax.text(0.5, 0.95, labels['top'], transform=ax.transAxes,
                       ha='center', va='top', fontsize=10, fontweight='bold', color='greenyellow')
                # Bottom label (5% margin from bottom)
                ax.text(0.5, 0.05, labels['bottom'], transform=ax.transAxes,
                       ha='center', va='bottom', fontsize=10, fontweight='bold', color='greenyellow')
                # Left label (5% margin from left)
                ax.text(0.05, 0.5, labels['left'], transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, fontweight='bold', color='greenyellow')
                # Right label (5% margin from right)
                ax.text(0.95, 0.5, labels['right'], transform=ax.transAxes,
                       ha='center', va='center', fontsize=10, fontweight='bold', color='greenyellow')
    
    if title and show_title:
        fig.suptitle(title, fontsize=16, fontweight='bold')
    
    # Add legend if requested and we have labels
    if show_legend and len(all_overlay_labels) > 0:
        # Create legend from collected labels
        legend_elements = [plt.Line2D([0], [0], color=color, lw=2, label=f'Label {label}') 
                          for label, color in all_overlay_labels]
        fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98),
                  framealpha=0.9, fontsize=8)
    
    fig.subplots_adjust(hspace=0.05, wspace=0.05)
    fig.patch.set_facecolor('black')

    return fig


def create_overlay_grid_3xN(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Union[np.ndarray, str, Path], 
    num_cols: int = 7, 
    overlay_colors: Optional[List[str]] = None,  # For multi-label segmentation (required if contour_type='discrete')
    contour_type: str = 'continuous',  # 'discrete' or 'continuous'
    show_legend: bool = False,  # Show legend for multi-label
    **kwargs
) -> plt.Figure:
    """
    Creates a 3xN grid of overlay images (3 orientations, N slices each).
    Supports multi-label segmentation with different colored contours for each label.
    
    Args:
        underlay_data: Underlay image data or path
        overlay_data: Overlay/segmentation data or path
        num_cols: Number of slices per orientation
        overlay_colors: List of colors for multi-label segmentation (required if contour_type='discrete')
        contour_type: 'discrete' (integer labels) or 'continuous'
        show_legend: Whether to show legend for multi-label segmentation
        **kwargs: Additional arguments passed to create_grid_mri_image
        
    Returns:
        Matplotlib figure
    """
    return create_grid_mri_image(
        underlay_data=underlay_data,
        overlay_data=overlay_data,
        num_cols=num_cols,
        perspectives=["axial", "sagittal", "coronal"],
        overlay_colors=overlay_colors,
        contour_type=contour_type,
        show_legend=show_legend,
        **kwargs
    )


def create_motion_plot(
    motion_data: np.ndarray,
    title: str = "Head Motion Parameters",
    figsize: Tuple[int, int] = (15, 6)
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
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)

    colors = ['#636295', '#7EA3A8', '#C86043']
    
    # Plot translations (mm)
    ax1.plot(motion_data[:, 0], label='X', color=colors[0], lw=2)
    ax1.plot(motion_data[:, 1], label='Y', color=colors[1], lw=2)
    ax1.plot(motion_data[:, 2], label='Z', color=colors[2], lw=2)
    ax1.set_ylabel('Translation (mm)')
    yrange = np.max(np.abs(motion_data[:, :3])) * 1.1
    ax1.set_ylim(-yrange, yrange)
    
    # Plot rotations (radians to degrees)
    ax2.plot(np.degrees(motion_data[:, 3]), label='X', color=colors[0], lw=2)
    ax2.plot(np.degrees(motion_data[:, 4]), label='Y', color=colors[1], lw=2)
    ax2.plot(np.degrees(motion_data[:, 5]), label='Z', color=colors[2], lw=2)
    ax2.set_ylabel('Rotation (degrees)')
    yrange = np.max(np.abs(np.degrees(motion_data[:, 3:]))) * 1.1
    ax2.set_ylim(-yrange, yrange)

    ax1.set_title(title)
    ax1.legend()
    ax2.set_xlabel('Timepoint')

    # show 10 xticks if there are more than 10 timepoints
    if motion_data.shape[0] > 10:
        xticks = np.linspace(0, motion_data.shape[0], 10).astype(int)
    for ax in [ax1, ax2]:
        ax.set_xticks(xticks)
        ax.set_xticklabels([f'{i:d}' for i in xticks])

    # add a horizontal line at 0 for the y-axis
    for ax in [ax1, ax2]:
        ax.axhline(0, color='gray', linestyle='--')
    
    # add grid
    for ax in [ax1, ax2]:
        ax.grid(True, alpha=0.1)
    
    plt.tight_layout()
    # sns.despine(right=True, top=True, trim=False, offset=0)

    return fig


# Surface rasterization functions for surface contour visualization
def rasterize_line_3d_bresenham(
    p0: np.ndarray, 
    p1: np.ndarray, 
    shape: Tuple[int, int, int]
) -> List[Tuple[int, int, int]]:
    """
    Rasterize a 3D line using 3D Bresenham algorithm.
    Ensures single-voxel thickness to avoid double contours.
    
    Args:
        p0: Start point as (x, y, z) array
        p1: End point as (x, y, z) array
        shape: Volume shape (x, y, z) for bounds checking
        
    Returns:
        List of voxel coordinates (x, y, z) along the line
    """
    p0 = np.array(p0, dtype=int)
    p1 = np.array(p1, dtype=int)
    
    # Handle degenerate case (same point)
    if np.all(p0 == p1):
        if (0 <= p0[0] < shape[0] and 0 <= p0[1] < shape[1] and 0 <= p0[2] < shape[2]):
            return [tuple(p0)]
        return []
    
    points = []
    dx = abs(p1[0] - p0[0])
    dy = abs(p1[1] - p0[1])
    dz = abs(p1[2] - p0[2])
    
    xs = 1 if p1[0] > p0[0] else -1
    ys = 1 if p1[1] > p0[1] else -1
    zs = 1 if p1[2] > p0[2] else -1
    
    # Determine which dimension has the largest change (driving axis)
    if dx >= dy and dx >= dz:
        # X is the driving axis
        p1_err = 2 * dy - dx
        p2_err = 2 * dz - dx
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dx + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if p1_err > 0:
                y += ys
                p1_err -= 2 * dx
            if p2_err > 0:
                z += zs
                p2_err -= 2 * dx
            p1_err += 2 * dy
            p2_err += 2 * dz
            x += xs
            if x == p1[0]:
                break
    elif dy >= dx and dy >= dz:
        # Y is the driving axis
        p1_err = 2 * dx - dy
        p2_err = 2 * dz - dy
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dy + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if p1_err > 0:
                x += xs
                p1_err -= 2 * dy
            if p2_err > 0:
                z += zs
                p2_err -= 2 * dy
            p1_err += 2 * dx
            p2_err += 2 * dz
            y += ys
            if y == p1[1]:
                break
    else:
        # Z is the driving axis
        p1_err = 2 * dy - dz
        p2_err = 2 * dx - dz
        x, y, z = p0[0], p0[1], p0[2]
        for _ in range(dz + 1):
            if (0 <= x < shape[0] and 0 <= y < shape[1] and 0 <= z < shape[2]):
                points.append((x, y, z))
            if p1_err > 0:
                y += ys
                p1_err -= 2 * dz
            if p2_err > 0:
                x += xs
                p2_err -= 2 * dz
            p1_err += 2 * dy
            p2_err += 2 * dx
            z += zs
            if z == p1[2]:
                break
    
    return points


def _compute_vertex_neighbors(faces: np.ndarray, n_vertices: int) -> List[Set[int]]:
    """
    Compute 1-ring neighbors for each vertex from face connectivity.
    
    Args:
        faces: Face array of shape (n_faces, 3) with vertex indices
        n_vertices: Total number of vertices
        
    Returns:
        List of sets, where each set contains neighbor vertex indices
    """
    neighbors = [set() for _ in range(n_vertices)]
    
    for face in faces:
        v0_idx, v1_idx, v2_idx = face
        # Validate indices before accessing
        if (0 <= v0_idx < n_vertices and 
            0 <= v1_idx < n_vertices and 
            0 <= v2_idx < n_vertices):
            # Add bidirectional edges (each face contributes 3 edges)
            neighbors[v0_idx].update([v1_idx, v2_idx])
            neighbors[v1_idx].update([v0_idx, v2_idx])
            neighbors[v2_idx].update([v0_idx, v1_idx])
    
    return neighbors


def create_surface_mask_from_mesh(
    surface_vertices: np.ndarray, 
    surface_faces: np.ndarray, 
    volume_img: nib.Nifti1Image
) -> np.ndarray:
    """
    Create a boundary mask from surface mesh using rasterization approach.
    Computes neighbors from faces and rasterizes edges only between neighbor pairs.
    Uses 3D Bresenham algorithm for single-voxel-thick lines.
    
    Args:
        surface_vertices: Vertex coordinates in RAS space, shape (n_vertices, 3)
        surface_faces: Face connectivity, shape (n_faces, 3)
        volume_img: Nibabel image object for transformation and shape reference
        
    Returns:
        Binary mask array of shape matching volume_img.shape[:3]
    """
    volume_shape = volume_img.shape[:3]
    
    # Get TkReg RAS to voxel transformation
    try:
        vox2ras_tkr = volume_img.header.get_vox2ras_tkr()
    except AttributeError:
        vox2ras_tkr = volume_img.affine
    
    # Transform vertices from TkReg RAS to voxel space
    inv_affine = np.linalg.inv(vox2ras_tkr)
    vertices_ras = np.column_stack([surface_vertices, np.ones(len(surface_vertices))])
    vertices_vox = (inv_affine @ vertices_ras.T).T[:, :3]
    
    # Create output mask
    surface_mask = np.zeros(volume_shape, dtype=np.uint8)
    
    # Compute neighbors from faces (1-ring neighbors)
    n_vertices = len(vertices_vox)
    neighbors = _compute_vertex_neighbors(surface_faces, n_vertices)
    
    # Rasterize edges only between neighbor pairs (avoid duplicate edges)
    drawn_edges: set = set()
    for v_idx in range(n_vertices):
        for neighbor_idx in neighbors[v_idx]:
            # Use canonical edge representation (smaller index first)
            edge_key = (min(v_idx, neighbor_idx), max(v_idx, neighbor_idx))
            if edge_key not in drawn_edges:
                drawn_edges.add(edge_key)
                v0 = np.round(vertices_vox[v_idx]).astype(int)
                v1 = np.round(vertices_vox[neighbor_idx]).astype(int)
                line_points = rasterize_line_3d_bresenham(v0, v1, volume_shape)
                # Set mask voxels using tuple unpacking
                for x, y, z in line_points:
                    surface_mask[x, y, z] = 1
    
    return surface_mask


def create_surface_mask_for_multiple_surfaces(
    surface_pairs: List[Tuple[np.ndarray, np.ndarray]], 
    volume_img: nib.Nifti1Image
) -> np.ndarray:
    """
    Create a combined mask from multiple surface meshes.
    
    Args:
        surface_pairs: List of (vertices, faces) tuples
        volume_img: Nibabel image object for transformation reference
        
    Returns:
        Combined binary mask
    """
    volume_shape = volume_img.shape[:3]
    combined_mask = np.zeros(volume_shape, dtype=np.uint8)
    
    for verts, faces in surface_pairs:
        mask = create_surface_mask_from_mesh(verts, faces, volume_img)
        combined_mask = np.maximum(combined_mask, mask)
    
    return combined_mask


# Surface atlas plot helper functions
WHITE_THRESHOLD = 250
CROP_PADDING = 5
MARGIN_PERCENT = 0.03
SURFACE_SPACING = 2
SURFACE_PLOT_SIZE = (400, 200)
SURFACE_PLOT_ZOOM = 1.2
SURFACE_PLOT_DPI = 150
CBAR_DPI = 300
CBAR_SPACING = 20
CBAR_GRADIENT_WIDTH_RATIO = 0.5
CBAR_TARGET_WIDTH_RATIO = 0.25
CBAR_LABEL_FONTSIZE = 6
CBAR_TICK_FONTSIZE = 5
CBAR_LABEL_PAD = 5


def _crop_white_space(img: Image.Image, threshold: int = WHITE_THRESHOLD, padding: int = CROP_PADDING) -> Image.Image:
    """Crop white space from image edges."""
    img_array = np.array(img)
    if img_array.size == 0:
        return img
    
    mask = np.any(img_array < threshold, axis=2) if len(img_array.shape) == 3 else img_array < threshold
    if not np.any(mask):
        return img
    
    coords = np.argwhere(mask)
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    return img.crop((
        max(0, x_min - padding),
        max(0, y_min - padding),
        min(img_array.shape[1], x_max + padding),
        min(img_array.shape[0], y_max + padding)
    ))


def _create_colorbar(
    cmap: str,
    vmin: float,
    vmax: float,
    label: str,
    fig_width_inches: float,
    fig_height_inches: float,
    dpi: int,
    gradient_width_ratio: float,
    temp_dir: Path
) -> Image.Image:
    """Create a colorbar image with specified parameters."""
    fig, ax = plt.subplots(figsize=(fig_width_inches, fig_height_inches), dpi=dpi)
    fig.patch.set_facecolor('white')
    pos = ax.get_position()
    ax.set_position([pos.x0, pos.y0, pos.width * gradient_width_ratio, pos.height])
    
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = plt.colorbar(sm, cax=ax, orientation='vertical')
    cbar.set_label(label, rotation=90, labelpad=CBAR_LABEL_PAD, fontsize=CBAR_LABEL_FONTSIZE)
    cbar.ax.yaxis.set_label_position('left')
    ax.tick_params(labelsize=CBAR_TICK_FONTSIZE)
    fig.tight_layout()
    
    temp_path = temp_dir / f"{label.lower().replace(' ', '_')}_colorbar.png"
    fig.savefig(temp_path, dpi=dpi, bbox_inches='tight', pad_inches=0.1, facecolor='white')
    plt.close(fig)
    
    cbar_img = Image.open(temp_path)
    aspect = cbar_img.height / cbar_img.width if cbar_img.width > 0 else 1
    target_height = int(fig_height_inches * dpi)
    return cbar_img.resize((int(target_height / aspect), target_height), Image.Resampling.LANCZOS)


def _create_label_image(
    label: str,
    fig_width_inches: float,
    fig_height_inches: float,
    dpi: int,
    gradient_width_ratio: float,
    temp_dir: Path
) -> Image.Image:
    """Create a label-only image (no gradient)."""
    fig, ax = plt.subplots(figsize=(fig_width_inches, fig_height_inches), dpi=dpi)
    fig.patch.set_facecolor('white')
    pos = ax.get_position()
    ax.set_position([pos.x0, pos.y0, pos.width * gradient_width_ratio, pos.height])
    ax.set_ylabel(label, rotation=90, labelpad=CBAR_LABEL_PAD, fontsize=CBAR_LABEL_FONTSIZE)
    ax.yaxis.set_label_position('left')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    
    temp_path = temp_dir / f"{label.lower()}_label.png"
    fig.savefig(temp_path, dpi=dpi, bbox_inches='tight', pad_inches=0.1, facecolor='white')
    plt.close(fig)
    
    label_img = Image.open(temp_path)
    aspect = label_img.height / label_img.width if label_img.width > 0 else 1
    target_height = int(fig_height_inches * dpi)
    return label_img.resize((int(target_height / aspect), target_height), Image.Resampling.LANCZOS)


def _find_content_width(img: Image.Image, threshold: int = WHITE_THRESHOLD) -> int:
    """Find the rightmost non-white pixel in an image."""
    img_array = np.array(img)
    is_not_white = np.any(img_array < threshold, axis=(0, 2)) if len(img_array.shape) == 3 else img_array < threshold
    if np.any(is_not_white):
        rightmost_col = np.where(is_not_white)[0].max() if len(np.where(is_not_white)[0]) > 0 else img.width
        return min(rightmost_col + 10, img.width)
    return img.width

