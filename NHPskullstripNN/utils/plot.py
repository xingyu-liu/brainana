"""
General plotting utilities for macacaMRINN.
"""

import matplotlib.pyplot as plt
import numpy as np
import torch
import nibabel as nib
from typing import Optional, Tuple, List, Union
from pathlib import Path


def get_opposite_orientation(direction: str) -> str:
    """
    Get the opposite anatomical direction.
    
    Args:
        direction: One of 'R', 'L', 'A', 'P', 'S', 'I'
        
    Returns:
        Opposite direction (e.g., 'R' -> 'L', 'A' -> 'P')
    """
    opposites = {'R': 'L', 'L': 'R', 'A': 'P', 'P': 'A', 'S': 'I', 'I': 'S'}
    return opposites.get(direction, direction)


def get_image_orientation_from_affine(
    affine: Union[np.ndarray, nib.spatialimages.SpatialImage],
) -> str:
    """Get orientation code from an affine matrix.
    
    Args:
        affine: Affine matrix (4x4 numpy array) or nibabel image object
        
    Returns:
        Orientation code string (e.g., 'RAS', 'LPI', 'RPS')
        
    Raises:
        ValueError: If aff2axcodes returns unexpected type
        AttributeError: If affine cannot be extracted from input
    """
    # Extract affine matrix if input is a nibabel image
    if isinstance(affine, nib.spatialimages.SpatialImage):
        affine_matrix = affine.affine
    else:
        affine_matrix = affine
    
    # Get orientation code from affine matrix
    axes_codes = nib.aff2axcodes(affine_matrix)
    if not isinstance(axes_codes, (list, tuple)):
        raise ValueError(
            f"aff2axcodes returned unexpected type: {type(axes_codes)}, value: {axes_codes}"
        )
    
    orientation_code = "".join(axes_codes)
    return orientation_code


def plot_slice(slice_data, title="Slice", cmap="gray", figsize=(8, 6)):
    """
    Plot a single 2D slice.
    
    Args:
        slice_data: 2D numpy array or torch tensor
        title: Plot title
        cmap: Colormap for the plot
        figsize: Figure size (width, height)
    """
    if torch.is_tensor(slice_data):
        slice_data = slice_data.detach().cpu().numpy()
    
    plt.figure(figsize=figsize)
    plt.imshow(slice_data, cmap=cmap)
    plt.title(title)
    plt.colorbar()
    plt.axis('off')
    plt.tight_layout()
    return plt.gcf()

def plot_volume(volume_data, 
                slice_idx=None, title="Volume", cmap="gray", figsize=(12, 8)):
    """
    Plot a 3D volume as multiple slices.
    
    Args:
        volume_data: 3D numpy array or torch tensor
        slice_idx: List of slice indices to plot, or None for middle slices
        title: Plot title
        cmap: Colormap for the plots
        figsize: Figure size (width, height)
    """
    if torch.is_tensor(volume_data):
        volume_data = volume_data.detach().cpu().numpy()
    
    if slice_idx is None:
        # Plot middle slices from each dimension
        slice_idx = [
            volume_data.shape[0] // 2,
            volume_data.shape[1] // 2,
            volume_data.shape[2] // 2
        ]
    
    fig, axes = plt.subplots(1, len(slice_idx), figsize=figsize)
    if len(slice_idx) == 1:
        axes = [axes]
    
    for i, idx in enumerate(slice_idx):
        if i == 0:
            slice_data = volume_data[idx, :, :]
            axis_label = f"Slice {idx} (X)"
        elif i == 1:
            slice_data = volume_data[:, idx, :]
            axis_label = f"Slice {idx} (Y)"
        else:
            slice_data = volume_data[:, :, idx]
            axis_label = f"Slice {idx} (Z)"
        
        axes[i].imshow(slice_data, cmap=cmap)
        axes[i].set_title(axis_label)
        axes[i].axis('off')
    
    plt.suptitle(title)
    plt.tight_layout()
    return fig


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


def _plot_labeled_data(ax, data_slice, colors, plot_type='contour', alpha=0.7):
    """Unified function to plot overlay or contour with automatic multi-label handling"""
    # Force data to int and get unique non-zero labels
    data_slice = data_slice.astype(int)
    unique_labels = np.unique(data_slice[data_slice != 0])
    
    plotted_labels = []
    for i, label_val in enumerate(unique_labels):
        mask = (data_slice == label_val).astype(float)
        color = colors[i % len(colors)]
        
        if plot_type == 'overlay':
            # Filled contour for overlay
            ax.contourf(mask, levels=[0.5, 1.5], colors=[color], alpha=alpha)
        elif plot_type == 'contour':
            # Line contour only
            ax.contour(mask, levels=[0.5], colors=[color], linewidths=2, alpha=alpha)
        
        plotted_labels.append((label_val, color))
    
    return plotted_labels


def create_mri_image(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Optional[Union[np.ndarray, str, Path]] = None, 
    contour_data: Optional[Union[np.ndarray, str, Path]] = None,
    num_cols: int = 7, 
    perspectives: List[str] = ["axial", "sagittal", "coronal"],
    title: str = "", 
    underlay_cmap: str = 'gray',
    overlay_alpha: float = 0.7,
    overlay_colors: Optional[List[str]] = None,
    contour_alpha: float = 0.7,
    contour_colors: Optional[List[str]] = None,
    figsize_per_col: Tuple[int, int] = (3, 3),
    show_title: bool = True,
    show_row_labels: bool = True,
    underlay_vmin: Optional[float] = None,
    underlay_vmax: Optional[float] = None,
    show_legend: bool = True
) -> plt.Figure:
    """
    Create a flexible grid of MRI images with optional overlay and contour data.
    
    Args:
        underlay_data: 3D underlay image data array or path to NIfTI file
        overlay_data: Optional 3D overlay image data array or path to NIfTI file (filled contours)
        contour_data: Optional 3D contour image data array or path to NIfTI file (contour lines)
        num_cols: Number of columns (slices per orientation)
        perspectives: List of orientations to show (from "axial", "sagittal", "coronal")
        title: Figure title
        underlay_cmap: Colormap for underlay
        overlay_alpha: Transparency of overlay (filled contours)
        overlay_colors: List of colors for overlay labels (cycles through for multiple labels)
        contour_alpha: Transparency of contour lines
        contour_colors: List of colors for contour labels (cycles through for multiple labels)
        figsize_per_col: Size per column in inches (width, height)
        show_title: Whether to show the main title
        show_row_labels: Whether to show orientation labels on rows
        underlay_vmin: Minimum value for underlay intensity scaling
        underlay_vmax: Maximum value for underlay intensity scaling
        show_legend: Whether to show a legend for labeled data
        
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
    
    # Handle contour (optional)
    contour = None
    if contour_data is not None:
        if isinstance(contour_data, (str, Path)):
            contour, contour_voxel_sizes, contour_orientation_code = _load_image(contour_data)
            # if 4d, get tmean image
            if contour.ndim == 4:
                contour = np.nanmean(contour, axis=-1)
            # Use contour voxel sizes if others didn't provide them
            if voxel_sizes is None:
                voxel_sizes = contour_voxel_sizes
            # Use contour orientation code if others didn't provide it
            if orientation_code is None:
                orientation_code = contour_orientation_code
            has_file_path = True
        else:
            contour = contour_data
    
    # Set default colors if not provided
    if overlay_colors is None:
        overlay_colors = ['limegreen', 'red', 'blue', 'yellow', 'magenta', 'cyan', 'orange', 'pink']
    if contour_colors is None:
        contour_colors = ['limegreen', 'red', 'blue', 'yellow', 'magenta', 'cyan', 'orange', 'pink']
    
    # Create figure with dynamic size based on number of perspectives
    num_rows = len(perspectives)
    fig = plt.figure(figsize=(num_cols * figsize_per_col[0], num_rows * figsize_per_col[1]))
    
    # Calculate consistent value range for underlay if not provided
    if underlay_vmin is None or underlay_vmax is None:
        # Convert boolean arrays to float for percentile calculation
        underlay_for_percentile = underlay.astype(float) if underlay.dtype == bool else underlay
        # Use percentile-based scaling to avoid outliers
        underlay_vmin = np.percentile(underlay_for_percentile, 1) if underlay_vmin is None else underlay_vmin
        underlay_vmax = np.percentile(underlay_for_percentile, 99) if underlay_vmax is None else underlay_vmax
    
    # Get orientation information with proper aspect ratios
    all_orientations = _get_slice_orientations(underlay, voxel_sizes, orientation_code)
    
    # Filter orientations based on selected perspectives
    selected_orientations = [(name, all_orientations[name]) for name in perspectives if name in all_orientations]
    orientation_names = [name.capitalize() for name in perspectives]
    
    # Collect all labels for legend
    all_overlay_labels = []
    all_contour_labels = []
    
    for row, (orient_name, orient_info) in enumerate(selected_orientations):
        # Calculate rotation needed to orient slice correctly
        rotation = 0
        if has_file_path and orientation_code is not None:
            shown_axes = orient_info.get('shown_axes', (0, 1))
            rotation = _get_rotation_for_perspective(orient_name, orientation_code, shown_axes)
        
        # Calculate N evenly spaced slice indices
        max_dim = orient_info['max_dim']
        # Ensure indices are within bounds [0, max_dim-1]
        start_idx = max(0, int(0.15 * max_dim))
        end_idx = min(max_dim - 1, int(0.85 * max_dim))
        slice_indices = np.linspace(start_idx, end_idx, num_cols, dtype=int)
        
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
            
            # Handle overlay if provided
            if overlay is not None:
                # Extract overlay slice using the same pattern as underlay
                slice_axis = orient_info['axis']
                if slice_axis == 0:
                    overlay_slice = overlay[slice_idx, :, :]
                elif slice_axis == 1:
                    overlay_slice = overlay[:, slice_idx, :]
                else:  # slice_axis == 2
                    overlay_slice = overlay[:, :, slice_idx]
                
                # Apply the same rotation as underlay
                if rotation > 0:
                    overlay_slice = np.rot90(overlay_slice, k=rotation)
                
                if np.any(overlay_slice != 0):
                    plotted_labels = _plot_labeled_data(ax, overlay_slice, overlay_colors, 
                                                      'overlay', overlay_alpha)
                    # Collect labels for legend (only from first slice to avoid duplicates)
                    if row == 0 and col == 0:
                        all_overlay_labels = plotted_labels
            
            # Handle contour if provided
            if contour is not None:
                # Extract contour slice using the same pattern as underlay
                slice_axis = orient_info['axis']
                if slice_axis == 0:
                    contour_slice = contour[slice_idx, :, :]
                elif slice_axis == 1:
                    contour_slice = contour[:, slice_idx, :]
                else:  # slice_axis == 2
                    contour_slice = contour[:, :, slice_idx]
                
                # Apply the same rotation as underlay
                if rotation > 0:
                    contour_slice = np.rot90(contour_slice, k=rotation)
                
                if np.any(contour_slice != 0):
                    plotted_labels = _plot_labeled_data(ax, contour_slice, contour_colors, 
                                                      'contour', contour_alpha)
                    # Collect labels for legend (only from first slice to avoid duplicates)
                    if row == 0 and col == 0:
                        all_contour_labels = plotted_labels
            
            ax.axis('off')
            
            # Add orientation label only for the first column
            if col == 0 and show_row_labels:
                ax.text(-0.1, 0.5, orientation_names[row], transform=ax.transAxes,
                       rotation=90, ha='center', va='center', fontsize=12, fontweight='bold')
    
    if title and show_title:
        fig.suptitle(title, fontsize=16, fontweight='bold')
    
    # Add legend for labeled data if enabled
    if show_legend and (all_overlay_labels or all_contour_labels):
        legend_handles = []
        from matplotlib.patches import Patch
        
        # Add overlay labels to legend
        for label_val, color in all_overlay_labels:
            legend_handles.append(Patch(color=color, label=f'Overlay {label_val}'))
        
        # Add contour labels to legend  
        for label_val, color in all_contour_labels:
            legend_handles.append(Patch(facecolor='none', edgecolor=color, linewidth=2, 
                                      label=f'Contour {label_val}'))
        
        if legend_handles:
            fig.legend(handles=legend_handles, loc='upper right', bbox_to_anchor=(0.98, 0.98),
                      facecolor='black', edgecolor='white', fontsize=10)
    
    fig.subplots_adjust(hspace=0, wspace=0)
    fig.patch.set_facecolor('black')

    return fig


def create_mri_image_3xN(
    underlay_data: Union[np.ndarray, str, Path], 
    overlay_data: Union[np.ndarray, str, Path], 
    contour_data: Optional[Union[np.ndarray, str, Path]] = None,
    num_cols: int = 7, 
    **kwargs
) -> plt.Figure:
    """
    Backward compatibility function for create_mri_image_3xN.
    Creates a 3xN grid of overlay images (3 orientations, N slices each).
    
    This function calls the new generic create_mri_image function.
    """
    return create_mri_image(
        underlay_data=underlay_data,
        overlay_data=overlay_data,
        contour_data=contour_data,
        num_cols=num_cols,
        perspectives=["axial", "sagittal", "coronal"],
        **kwargs
    )
