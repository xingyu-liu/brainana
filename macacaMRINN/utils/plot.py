"""
General plotting utilities for macacaMRINN.
"""

import matplotlib.pyplot as plt
import numpy as np
import torch
import nibabel as nib
from typing import Optional, Tuple, List, Union
from pathlib import Path


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
    
    # Handle contour (optional)
    contour = None
    if contour_data is not None:
        if isinstance(contour_data, (str, Path)):
            contour, contour_voxel_sizes, _ = _load_and_orient_image(contour_data)
            # Use contour voxel sizes if others didn't provide them
            if voxel_sizes is None:
                voxel_sizes = contour_voxel_sizes
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
    all_orientations = _get_slice_orientations(underlay, voxel_sizes)
    
    # Filter orientations based on selected perspectives
    selected_orientations = [(name, all_orientations[name]) for name in perspectives if name in all_orientations]
    orientation_names = [name.capitalize() for name in perspectives]
    
    # Collect all labels for legend
    all_overlay_labels = []
    all_contour_labels = []
    
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
            
            # Helper function to create oriented slice
            def create_oriented_slice(data, orient_name, slice_idx):
                if orient_name == 'axial':
                    return np.rot90(data[:, :, slice_idx], k=1)
                elif orient_name == 'sagittal':
                    return np.rot90(data[slice_idx, :, :], k=1)
                else:  # coronal
                    return np.rot90(data[:, slice_idx, :], k=1)
            
            # Display overlay if provided using unified function
            if overlay is not None:
                overlay_slice = create_oriented_slice(overlay, orient_name, slice_idx)
                if np.any(overlay_slice != 0):
                    plotted_labels = _plot_labeled_data(ax, overlay_slice, overlay_colors, 
                                                      'overlay', overlay_alpha)
                    # Collect labels for legend (only from first slice to avoid duplicates)
                    if row == 0 and col == 0:
                        all_overlay_labels = plotted_labels
            
            # Display contour if provided using unified function
            if contour is not None:
                contour_slice = create_oriented_slice(contour, orient_name, slice_idx)
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
