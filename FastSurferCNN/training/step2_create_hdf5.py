#!/usr/bin/env python3

"""
Generate HDF5 training dataset for Monkey MRI with Flexible Atlas Support
Enhanced version with proper resizing (inspired by macacaMRINN)

Key improvements:
- Proportional resizing using scipy.ndimage.zoom (maintains aspect ratio)
- Padding to exact target dimensions
- Ensures all images have consistent dimensions (e.g., 256×256)
- Uses config_utils for path resolution (single source of truth from YAML)
- Supports any atlas via command line or environment variable

Memory optimizations:
- Memory-mapped file loading (mmap=True) to reduce memory footprint
- Explicit cleanup with del and gc.collect() after processing each volume
- Eliminates duplicate label loading (previously loaded twice)
- Improved HDF5 compression (level 4) and auto-chunking
- Periodic memory monitoring and warnings during processing
- Immediate freeing of intermediate arrays after use
"""

import argparse
import h5py
import nibabel as nib
import numpy as np
import os
import sys
from pathlib import Path
from collections import defaultdict
from multiprocessing import Pool
from scipy import ndimage
import json
import gc
import psutil  # For memory monitoring

# Add parent directory to path for FastSurferCNN imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config utilities for path resolution
from FastSurferCNN.utils.config_utils import load_yaml_config, get_paths_from_config, print_paths_summary

# Import atlas management system
from FastSurferCNN.atlas.atlas_manager import get_atlas_manager

# Import FastSurferCNN utilities
from FastSurferCNN.data_loader.data_utils import (
    create_weight_mask,
    filter_blank_slices_thick,
    get_thick_slices,
    transform_axial,
    transform_sagittal,
)
from FastSurferCNN.data_loader.conform import conform


def resize_volume_proportional(volume, target_size=256, order=1):
    """
    Resize volume proportionally to fit within target_size, then pad to exact dimensions.
    
    This mimics macacaMRINN's approach:
    1. Find max dimension
    2. Calculate scale factor to fit within target
    3. Resize proportionally
    4. Pad to exact target dimensions
    
    Parameters
    ----------
    volume : np.ndarray
        3D volume with shape (height, width, depth) or (height, width, depth, channels)
    target_size : int
        Target size for height and width
    order : int
        Interpolation order (0=nearest, 1=linear, 3=cubic)
        Use order=0 for labels, order=1 for images/weights
    
    Returns
    -------
    np.ndarray
        Resized and padded volume with shape (target_size, target_size, depth) or 
        (target_size, target_size, depth, channels)
    float
        Scale factor applied
    """
    original_shape = volume.shape
    has_channels = len(original_shape) == 4
    
    if has_channels:
        h, w, d, c = original_shape
    else:
        h, w, d = original_shape
    
    # Find maximum spatial dimension (height, width)
    max_dim = max(h, w)
    
    # Calculate scale factor to fit within target_size
    scale_factor = target_size / max_dim
    
    # Calculate new dimensions after proportional scaling
    new_h = int(h * scale_factor)
    new_w = int(w * scale_factor)
    
    # Resize proportionally
    if scale_factor != 1.0:
        if has_channels:
            # Resize each channel separately to preserve label values
            zoom_factors = (new_h/h, new_w/w, 1, 1)  # Don't scale depth or channels
        else:
            zoom_factors = (new_h/h, new_w/w, 1)  # Don't scale depth
        
        resized = ndimage.zoom(volume, zoom_factors, order=order)
    else:
        resized = volume.copy()
    
    # Now pad to exact target dimensions
    if has_channels:
        padded = np.zeros((target_size, target_size, d, c), dtype=volume.dtype)
        padded[:new_h, :new_w, :, :] = resized
    else:
        padded = np.zeros((target_size, target_size, d), dtype=volume.dtype)
        padded[:new_h, :new_w, :] = resized
    
    return padded, scale_factor


def load_and_conform_image(image_path, preprocess_params):
    """
    Load and preprocess image using conform() - EXACT same method as inference!
    
    CRITICAL: Uses conform() with parameters from YAML config to ensure
    identical preprocessing during HDF5 creation, training, and inference.
    
    Parameters
    ----------
    image_path : Path
        Path to image file
    preprocess_params : dict
        Preprocessing parameters from YAML config['DATA']['PREPROCESSING']
        
    Returns
    -------
    np.ndarray
        Preprocessed image data (already in correct orientation, size, dtype)
        Returns None if zoom values are invalid
    np.ndarray
        Voxel sizes from original image header
        Returns None if zoom values are invalid
    """
    # Load with memory mapping to reduce memory footprint
    img = nib.load(image_path, mmap=True)
    
    # Get original voxel sizes before conform (header access is cheap)
    zoom = img.header.get_zooms()[:3]
    
    # ⚠️ VALIDATION: Check for zero or invalid zoom values - SKIP if invalid
    zoom_array = np.asarray(zoom)
    invalid_mask = np.abs(zoom_array) < 1e-6
    if np.any(invalid_mask):
        print(f"  ⚠️  SKIPPING: Invalid zoom values detected in {image_path.name}")
        print(f"      Zoom values: {zoom_array}")
        print(f"      Invalid dimensions: {np.where(invalid_mask)[0]}")
        print(f"      This subject will be excluded from the dataset.")
        del img
        return None, None
    
    # Use conform() - EXACT same function as inference!
    # This handles orientation + resizing + voxel size + dtype conversion
    conformed_img = conform(
        img,
        order=preprocess_params['ORDER_IMAGE'],
        orientation=preprocess_params['ORIENTATION'].lower(),
        img_size=preprocess_params['IMG_SIZE'],
        vox_size=preprocess_params['VOX_SIZE'],
        threshold_1mm=preprocess_params['THRESHOLD_1MM'],
        dtype=np.dtype(preprocess_params['DTYPE_IMAGE']),  # Use DTYPE_IMAGE for images
        rescale=preprocess_params['RESCALE'],
    )
    
    # Extract data
    data = np.asarray(conformed_img.dataobj)
    
    # Free nibabel objects immediately
    del img, conformed_img
    
    # Normalize to [0, 1] for training
    data = data.astype(np.float32)
    if data.max() > 0:
        data = data / data.max()
    
    return data, zoom


def load_and_map_labels(label_path, plane="coronal", atlas_manager=None, preprocess_params=None):
    """
    Load and preprocess labels using conform() - EXACT same method as inference!
    
    CRITICAL: Uses conform() with parameters from YAML config to ensure
    identical preprocessing during HDF5 creation, training, and inference.
    Uses nearest-neighbor interpolation (order=0) to preserve discrete label values.
    
    Parameters
    ----------
    label_path : Path
        Path to segmentation file
    plane : str
        Anatomical plane - sagittal uses hemisphere merging
    atlas_manager : AtlasManager
        Atlas manager instance for label mapping
    preprocess_params : dict
        Preprocessing parameters from YAML config['DATA']['PREPROCESSING']
        
    Returns
    -------
    np.ndarray
        Dense label array (already in correct orientation, size)
    """
    # Load with memory mapping to reduce memory footprint
    img = nib.load(label_path, mmap=True)
    
    # Use conform() for labels - EXACT same function as inference!
    # Uses ORDER_LABEL (nearest neighbor) to preserve discrete values
    # CRITICAL: Use int16/int32 dtype to support NEGATIVE label IDs (e.g., -1 for WM)
    # CRITICAL: NO rescaling for labels (rescale=None) - preserve exact label values!
    conformed_img = conform(
        img,
        order=preprocess_params['ORDER_LABEL'],  # MUST be 0 (nearest neighbor)
        orientation=preprocess_params['ORIENTATION'].lower(),
        img_size=preprocess_params['IMG_SIZE'],
        vox_size=preprocess_params['VOX_SIZE'],
        threshold_1mm=preprocess_params['THRESHOLD_1MM'],
        dtype=np.dtype(preprocess_params['DTYPE_LABEL']),  # Use DTYPE_LABEL (int16/int32) for labels
        rescale=None,  # NO rescaling for labels! Preserve exact values including negatives
    )
    
    # Extract sparse labels
    sparse_labels = np.asarray(conformed_img.dataobj).astype(np.int32)
    
    # Free nibabel objects immediately
    del img, conformed_img
    
    # Use atlas manager for label mapping
    # Sagittal uses special hemisphere merging (bilateral -> single)
    if plane == "sagittal":
        dense_labels = atlas_manager.map_labels_to_sagittal_dense(sparse_labels)
    else:
        # Coronal and axial use full bilateral labels
        dense_labels = atlas_manager.map_labels_to_dense(sparse_labels)
    
    return dense_labels


def process_subject(image_path, label_path, plane, slice_thickness=3, target_size=256, atlas_manager=None, preprocess_params=None, verbose=True):
    """
    Process a single subject's MRI and segmentation using conform() preprocessing.
    
    Parameters
    ----------
    image_path : Path
        Path to T1w image
    label_path : Path
        Path to segmentation
    plane : str
        Anatomical plane (axial, coronal, sagittal)
    slice_thickness : int
        Number of slices before/after middle slice
    target_size : int
        Target size for resizing (e.g., 256 for 256×256)
    atlas_manager : AtlasManager
        Atlas manager instance
    preprocess_params : dict
        Preprocessing parameters from YAML config['DATA']['PREPROCESSING']
    verbose : bool
        Whether to print detailed info
        
    Returns
    -------
    dict
        Dictionary with processed data
    """
    # Load image using conform() - EXACT same as inference!
    image_data, zoom = load_and_conform_image(image_path, preprocess_params)
    
    # Check if loading failed due to invalid zoom values
    if image_data is None:
        gc.collect()
        return None
    
    # Load labels ONCE and process for both statistics and training
    # This eliminates duplicate loading and saves memory
    # Use memory mapping to reduce memory footprint
    img = nib.load(label_path, mmap=True)
    
    # Use conform() for labels - EXACT same function as inference!
    conformed_img = conform(
        img,
        order=preprocess_params['ORDER_LABEL'],
        orientation=preprocess_params['ORIENTATION'].lower(),
        img_size=preprocess_params['IMG_SIZE'],
        vox_size=preprocess_params['VOX_SIZE'],
        threshold_1mm=preprocess_params['THRESHOLD_1MM'],
        dtype=np.dtype(preprocess_params['DTYPE_LABEL']),
        rescale=None,
    )
    
    # Extract sparse labels for statistics
    sparse_labels = np.asarray(conformed_img.dataobj).astype(np.int32)
    
    # Free the nibabel image objects immediately
    del img, conformed_img
    
    # Map sparse labels to dense for training
    if plane == "sagittal":
        label_data = atlas_manager.map_labels_to_sagittal_dense(sparse_labels)
    else:
        label_data = atlas_manager.map_labels_to_dense(sparse_labels)
    
    # Get atlas-specific configuration
    atlas_config = atlas_manager.get_atlas_config(plane)
    
    # Create weight mask BEFORE transforming (needs full 3D volume)
    # Uses metadata-based cortex detection from atlas roiinfo.txt
    weights = create_weight_mask(
        label_data,
        max_weight=5,
        max_edge_weight=5,
        max_hires_weight=5,
        gradient=False,
        cortex_labels=atlas_config.cortex_labels,
        verbose=verbose
    )
    
    # Print weight mask statistics for verification (use sparse labels for accurate counting)
    if verbose:
        total_voxels = sparse_labels.size
        
        # Count voxels by region type using sparse labels (before mapping)
        background_voxels = np.sum(sparse_labels == 0)
        cortex_labels_no_bg = [l for l in atlas_config.cortex_labels if l != 0]
        cortex_voxels = np.sum(np.isin(sparse_labels, cortex_labels_no_bg))
        subcortex_voxels = np.sum(np.isin(sparse_labels, list(atlas_config.subcortex_labels)))
        cerebral_wm_voxels = np.sum(np.isin(sparse_labels, list(atlas_config.cerebral_wm_labels)))
        cerebellar_wm_voxels = np.sum(np.isin(sparse_labels, list(atlas_config.cerebellar_wm_labels)))
        
        # Calculate other (unknown labels not in any category)
        tissue_voxels = cortex_voxels + subcortex_voxels + cerebral_wm_voxels + cerebellar_wm_voxels
        other_voxels = total_voxels - background_voxels - tissue_voxels
        
        print(f"  Weight mask statistics:")
        print(f"    - Weight range: {weights.min():.2f} to {weights.max():.2f}")
        print(f"    - Mean weight: {weights.mean():.2f}")
        print(f"  Label distribution (from sparse labels):")
        print(f"    - Background:     {background_voxels:8d} ({100*background_voxels/total_voxels:5.1f}%)")
        print(f"    - Cortex:         {cortex_voxels:8d} ({100*cortex_voxels/total_voxels:5.1f}%)")
        print(f"    - Subcortex:      {subcortex_voxels:8d} ({100*subcortex_voxels/total_voxels:5.1f}%)")
        print(f"    - Cerebral WM:    {cerebral_wm_voxels:8d} ({100*cerebral_wm_voxels/total_voxels:5.1f}%)")
        print(f"    - Cerebellar WM:  {cerebellar_wm_voxels:8d} ({100*cerebellar_wm_voxels/total_voxels:5.1f}%)")
        if other_voxels > 0:
            print(f"    - Other/Unknown:  {other_voxels:8d} ({100*other_voxels/total_voxels:5.1f}%)")
    
    # Transform to requested plane FIRST
    if plane == "sagittal":
        image_data = transform_sagittal(image_data)
        label_data = transform_sagittal(label_data)
        weights = transform_sagittal(weights)
        zoom_2d = np.asarray(zoom)[::-1][:2]
    elif plane == "axial":
        image_data = transform_axial(image_data)
        label_data = transform_axial(label_data)
        weights = transform_axial(weights)
        zoom_2d = np.asarray(zoom)[[2, 0]]
    else:  # coronal (default - no transformation needed)
        zoom_2d = np.asarray(zoom)[:2]
    
    # NOW resize to target_size proportionally, then pad
    image_data_resized, scale_factor = resize_volume_proportional(image_data, target_size, order=1)
    label_data_resized, _ = resize_volume_proportional(label_data, target_size, order=0)  # Nearest for labels
    weights_resized, _ = resize_volume_proportional(weights, target_size, order=1)
    
    # Free original volumes immediately after resizing
    del image_data, label_data, weights, sparse_labels
    
    # Update zoom to reflect the scaling
    zoom_2d_scaled = zoom_2d / scale_factor
    
    # ⚠️ VALIDATION: Check if final zoom values are valid - SKIP if invalid
    if np.any(np.abs(zoom_2d_scaled) < 1e-6):
        print(f"  ⚠️  SKIPPING: Invalid scaled zoom values detected!")
        print(f"      zoom_2d: {zoom_2d}")
        print(f"      scale_factor: {scale_factor}")
        print(f"      zoom_2d_scaled: {zoom_2d_scaled}")
        print(f"      This subject will be excluded from the dataset.")
        # Free all data and return None (sparse_labels already deleted above)
        del image_data_resized, label_data_resized, weights_resized
        gc.collect()
        return None
    
    if verbose:
        print(f"  Original shape: {image_data_resized.shape[:2]}, Scale: {scale_factor:.3f}")
        print(f"  Zoom values: original={zoom_2d}, scaled={zoom_2d_scaled}")
    
    # Create thick slices
    image_thick = get_thick_slices(image_data_resized, slice_thickness)
    
    # Free resized image data after creating thick slices
    del image_data_resized
    
    # Filter out blank slices
    image_slices, label_slices, weights_final = filter_blank_slices_thick(
        image_thick, label_data_resized, weights_resized, threshold=50
    )
    
    # Free intermediate arrays
    del image_thick, label_data_resized, weights_resized
    
    if image_slices.shape[2] == 0:
        # Trigger garbage collection before returning None
        gc.collect()
        return None
    
    # Transpose back to (slices, height, width, channels) for images
    image_slices = np.transpose(image_slices, (2, 0, 1, 3))
    # Transpose to (slices, height, width) for labels and weights
    label_slices = np.transpose(label_slices, (2, 0, 1))
    weights_final = np.transpose(weights_final, (2, 0, 1))
    
    # Verify shapes are consistent
    assert image_slices.shape[1] == target_size and image_slices.shape[2] == target_size, \
        f"Image shape mismatch: {image_slices.shape}"
    assert label_slices.shape[1] == target_size and label_slices.shape[2] == target_size, \
        f"Label shape mismatch: {label_slices.shape}"
    
    # Prepare output
    result = {
        'images': image_slices,
        'labels': label_slices,
        'weights': weights_final,
        'zooms': np.tile(zoom_2d_scaled, (image_slices.shape[0], 1)),
        'num_slices': image_slices.shape[0],
        'scale_factor': scale_factor
    }
    
    # Force garbage collection to free memory immediately
    gc.collect()
    
    return result

def get_memory_usage():
    """
    Get current memory usage information.
    
    Returns
    -------
    dict
        Dictionary with memory statistics (in GB)
    """
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        virtual_mem = psutil.virtual_memory()
        
        return {
            'process_rss_gb': mem_info.rss / (1024**3),  # Resident Set Size
            'process_vms_gb': mem_info.vms / (1024**3),  # Virtual Memory Size
            'system_available_gb': virtual_mem.available / (1024**3),
            'system_percent': virtual_mem.percent,
            'system_total_gb': virtual_mem.total / (1024**3)
        }
    except Exception as e:
        # If psutil fails, return None
        return None


def check_memory_and_warn(threshold_percent=80, verbose=True):
    """
    Check system memory usage and warn if it's getting high.
    
    Parameters
    ----------
    threshold_percent : float
        Warn if system memory usage exceeds this percentage
    verbose : bool
        Whether to print warnings
    
    Returns
    -------
    bool
        True if memory usage is below threshold, False otherwise
    """
    mem = get_memory_usage()
    if mem is None:
        return True  # Cannot check, assume OK
    
    if mem['system_percent'] > threshold_percent and verbose:
        print(f"\n⚠️  WARNING: High memory usage!")
        print(f"   System: {mem['system_percent']:.1f}% used ({mem['system_available_gb']:.1f} GB available)")
        print(f"   This process: {mem['process_rss_gb']:.2f} GB")
        print(f"   Consider reducing num_workers or processing in smaller batches\n")
        return False
    
    return True


def _create_resizable_dataset(hf_group, name, dtype, shape, compression='gzip', compression_opts=4, chunks=True):
    """
    Helper to create a resizable HDF5 dataset with optimized compression and chunking.
    
    Parameters
    ----------
    hf_group : h5py.Group
        HDF5 group to create dataset in
    name : str
        Dataset name
    dtype : np.dtype
        Data type
    shape : tuple
        Initial shape (first dimension should be 0 for empty dataset)
    compression : str
        Compression algorithm ('gzip', 'lzf', or None)
    compression_opts : int
        Compression level (1-9 for gzip, higher = more compression but slower)
        Default 4 balances compression ratio and speed
    chunks : bool or tuple
        Enable automatic chunking (True) or specify chunk shape
        Chunking improves memory efficiency for large datasets
    
    Returns
    -------
    h5py.Dataset
        Created dataset
    """
    return hf_group.create_dataset(
        name, 
        data=np.empty(shape, dtype=dtype), 
        maxshape=(None,) + shape[1:],
        compression=compression, 
        compression_opts=compression_opts,
        chunks=chunks  # Auto-chunking for memory efficiency
    )


def create_hdf5_dataset(
    data_dir,
    output_hdf5,
    plane="coronal",
    image_suffix="_T1w.nii.gz",
    label_suffix=None,
    target_size=256,
    slice_thickness=3,
    atlas_manager=None,
    preprocess_params=None,
    subject_filter=None,
    num_workers=1,
    problematic_zooms=None  # List to collect subjects with zoom issues
):
    """
    Create HDF5 dataset using conform() preprocessing - EXACT same as inference!
    
    All images will be preprocessed using conform() with parameters from YAML config,
    ensuring identical preprocessing during HDF5 creation, training, and inference.
    
    Parameters
    ----------
    target_size : int
        Target dimension for all images (e.g., 256 for 256×256)
    preprocess_params : dict
        Preprocessing parameters from YAML config['DATA']['PREPROCESSING']
    """
    image_dir = Path(data_dir) / "T1w_images"
    # Get atlas name from the atlas manager's directory name to preserve case
    atlas_name = atlas_manager.atlas_dir.name.replace('atlas-', '')
    label_dir = Path(data_dir) / f"T1w_atlas-{atlas_name}"
    
    # Generate label suffix dynamically based on atlas
    if label_suffix is None:
        label_suffix = f"_T1w_atlas-{atlas_name}.nii.gz"
    
    # Find all label files first (use label_dir as the total pool)
    all_label_files = sorted(label_dir.glob(f"*{label_suffix}"))
    
    # Find corresponding image files for each label file
    all_image_files = []
    for label_file in all_label_files:
        # Extract subject name from label file
        subject_name = label_file.name.replace(label_suffix, "")
        # Find corresponding image file
        image_file = image_dir / f"{subject_name}{image_suffix}"
        if image_file.exists():
            all_image_files.append(image_file)
        else:
            print(f"Warning: No image file found for label {label_file.name}")
    
    # Filter by subject_filter if provided
    if subject_filter is not None:
        image_files = []
        for img_file in all_image_files:
            subject_name = img_file.name.replace(image_suffix, "")
            if subject_name in subject_filter:
                image_files.append(img_file)
        print(f"Filtered {len(image_files)}/{len(all_image_files)} subjects based on data split")
    else:
        image_files = all_image_files
        print(f"Found {len(image_files)} subjects (based on {len(all_label_files)} label files)")
    
    print(f"Processing plane: {plane}")
    print(f"Target size: {target_size}×{target_size} (with proportional resizing + padding)")
    print(f"Output: {output_hdf5}")
    if num_workers > 1:
        print(f"Using {num_workers} parallel workers")
    
    # Display initial memory status
    mem = get_memory_usage()
    if mem:
        print(f"\n📊 Initial memory status:")
        print(f"   System: {mem['system_total_gb']:.1f} GB total, "
              f"{mem['system_available_gb']:.1f} GB available ({100-mem['system_percent']:.1f}% free)")
        print(f"   This process: {mem['process_rss_gb']:.2f} GB")
        
        # Warn if starting with high memory usage
        if mem['system_percent'] > 70:
            print(f"   ⚠️  Warning: System already using {mem['system_percent']:.1f}% of memory")
            print(f"   Consider closing other applications or reducing num_workers")
    
    # Collect all data (single size bin since everything will be target_size × target_size)
    # Removed all_data dictionary for incremental HDF5 writing

    # Process subjects
    total_subjects = len(image_files)

    print(f"\nWriting HDF5 file: {output_hdf5}")
    output_hdf5.parent.mkdir(parents=True, exist_ok=True)

    # Check if HDF5 file already exists (resume capability)
    already_processed_subjects = set()
    file_mode = 'w'  # Default: create new file
    
    if output_hdf5.exists():
        print(f"✓ Found existing HDF5 file, checking for resume...")
        try:
            with h5py.File(output_hdf5, 'r') as hf_check:
                if str(target_size) in hf_check and 'subject' in hf_check[str(target_size)]:
                    # Read list of already processed subjects
                    subjects_in_hdf5 = hf_check[str(target_size)]['subject'][:]
                    # Convert bytes to strings if needed (HDF5 may store as bytes)
                    already_processed_subjects = set(
                        s.decode('utf-8') if isinstance(s, bytes) else s 
                        for s in subjects_in_hdf5
                    )
                    num_existing_slices = len(subjects_in_hdf5)
                    
                    print(f"  Found {len(already_processed_subjects)} subjects already processed ({num_existing_slices} slices)")
                    
                    # Verify preprocessing metadata matches
                    if 'preprocessing_metadata' in hf_check:
                        meta = hf_check['preprocessing_metadata']
                        for key, expected_value in preprocess_params.items():
                            if key in meta.attrs:
                                existing_value = meta.attrs[key]
                                if existing_value != expected_value:
                                    print(f"  ⚠️  Warning: Preprocessing parameter '{key}' differs!")
                                    print(f"      Existing: {existing_value}, Current: {expected_value}")
                                    print(f"      Recommend starting fresh or using same config.")
                    
                    file_mode = 'a'  # Append mode for resume
                    print(f"  ✓ Resume mode enabled - will skip already processed subjects")
                else:
                    print(f"  No valid data found in existing file, will overwrite")
        except Exception as e:
            print(f"  ⚠️  Could not read existing file ({e}), will overwrite")
    
    # Filter out already processed subjects
    if already_processed_subjects:
        original_count = len(image_files)
        image_files = [img for img in image_files 
                      if img.name.replace(image_suffix, "") not in already_processed_subjects]
        print(f"  Filtered: {original_count} → {len(image_files)} subjects remaining to process")
        
        if len(image_files) == 0:
            print(f"\n✅ All subjects already processed! Nothing to do.")
            return
    
    # Update total_subjects to reflect actual number to process (after filtering)
    total_subjects = len(image_files)

    num_samples_written = 0 # Initialize counter for samples written

    with h5py.File(output_hdf5, file_mode) as hf:
        # Handle preprocessing metadata (create or verify existing)
        if 'preprocessing_metadata' not in hf:
            # Save preprocessing metadata for validation during training!
            # This ensures training can verify HDF5 was created with correct parameters
            preprocess_metadata = hf.create_group('preprocessing_metadata')
            for key, value in preprocess_params.items():
                preprocess_metadata.attrs[key] = value
            preprocess_metadata.attrs['created_with_conform'] = True
            preprocess_metadata.attrs['version'] = '1.0'
            
            print(f"✓ Saved preprocessing metadata to HDF5 (for validation during training)")
        else:
            print(f"✓ Using existing preprocessing metadata")
        
        # Get or create group for the target size
        if str(target_size) not in hf:
            grp = hf.create_group(str(target_size))
            
            # --- Initialize resizable datasets ---
            # Dummy shapes for initial creation. They will be resized dynamically.
            # Images: (slices, height, width, channels)
            # Labels/Weights: (slices, height, width)
            # Zooms: (slices, 2)

            # The 'slice_thickness * 2 + 1' determines the number of channels for images (thick slices)
            initial_img_shape = (0, target_size, target_size, slice_thickness * 2 + 1)
            initial_label_weight_shape = (0, target_size, target_size)
            initial_zoom_shape = (0, 2)

            images_ds = _create_resizable_dataset(grp, 'orig_dataset', np.float32, initial_img_shape)
            labels_ds = _create_resizable_dataset(grp, 'aseg_dataset', np.int32, initial_label_weight_shape)
            weights_ds = _create_resizable_dataset(grp, 'weight_dataset', np.float32, initial_label_weight_shape)
            zooms_ds = _create_resizable_dataset(grp, 'zoom_dataset', np.float32, initial_zoom_shape)
            
            # Subject dataset (variable length string) needs special handling
            subjects_ds = grp.create_dataset('subject', (0,), maxshape=(None,), dtype=h5py.string_dtype(encoding='utf-8'))
            
            print(f"✓ Created new datasets for size {target_size}")
        else:
            # Append mode - get existing datasets
            grp = hf[str(target_size)]
            images_ds = grp['orig_dataset']
            labels_ds = grp['aseg_dataset']
            weights_ds = grp['weight_dataset']
            zooms_ds = grp['zoom_dataset']
            subjects_ds = grp['subject']
            
            print(f"✓ Appending to existing datasets (current size: {images_ds.shape[0]} slices)")

        # Prepare arguments for parallel processing
        process_args = [
            (idx, image_file, image_suffix, label_suffix, label_dir, plane, 
             slice_thickness, target_size, atlas_manager, preprocess_params, total_subjects)
            for idx, image_file in enumerate(image_files, 1)
        ]
        
        if num_workers > 1:
            # Parallel processing
            subjects_processed = 0
            with Pool(processes=num_workers) as pool:
                for result_data, msg in pool.imap_unordered(_process_single_subject_wrapper, process_args):
                    print(msg)
                    if result_data is not None:
                        result, subject_name = result_data
                        num_slices = result['num_slices']
                        
                        # Resize datasets and append
                        current_len = images_ds.shape[0]
                        images_ds.resize(current_len + num_slices, axis=0)
                        images_ds[current_len:current_len + num_slices] = result['images']

                        labels_ds.resize(current_len + num_slices, axis=0)
                        labels_ds[current_len:current_len + num_slices] = result['labels']

                        weights_ds.resize(current_len + num_slices, axis=0)
                        weights_ds[current_len:current_len + num_slices] = result['weights']

                        zooms_ds.resize(current_len + num_slices, axis=0)
                        zooms_ds[current_len:current_len + num_slices] = result['zooms']

                        subjects_ds.resize(current_len + num_slices, axis=0)
                        subjects_ds[current_len:current_len + num_slices] = [subject_name] * num_slices

                        num_samples_written += num_slices
                        subjects_processed += 1
                        
                        # Check memory every 10 subjects
                        if subjects_processed % 10 == 0:
                            check_memory_and_warn(threshold_percent=85, verbose=True)
        else:
            # Serial processing
            subjects_processed = 0
            for args in process_args:
                result_data, msg = _process_single_subject_wrapper(args)
                print(msg)
                if result_data is not None:
                    result, subject_name = result_data
                    num_slices = result['num_slices']
                    
                    # Resize datasets and append
                    current_len = images_ds.shape[0]
                    images_ds.resize(current_len + num_slices, axis=0)
                    images_ds[current_len:current_len + num_slices] = result['images']

                    labels_ds.resize(current_len + num_slices, axis=0)
                    labels_ds[current_len:current_len + num_slices] = result['labels']

                    weights_ds.resize(current_len + num_slices, axis=0)
                    weights_ds[current_len:current_len + num_slices] = result['weights']

                    zooms_ds.resize(current_len + num_slices, axis=0)
                    zooms_ds[current_len:current_len + num_slices] = result['zooms']

                    subjects_ds.resize(current_len + num_slices, axis=0)
                    subjects_ds[current_len:current_len + num_slices] = [subject_name] * num_slices
                    
                    num_samples_written += num_slices
                    subjects_processed += 1
                    
                    # Check memory every 10 subjects
                    if subjects_processed % 10 == 0:
                        check_memory_and_warn(threshold_percent=85, verbose=True)

    # After the loop, the HDF5 file is closed.
    # Re-open in read mode to get final shapes and subject list for printing.
    with h5py.File(output_hdf5, 'r') as hf:
        grp = hf[str(target_size)]
        
        # Get the actual number of unique subjects from the HDF5 dataset
        # This will load all subjects into memory, but only for reporting, not processing.
        unique_subjects = len(set(grp['subject'][:]))
        total_slices_in_file = grp['orig_dataset'].shape[0]

        skipped_count = len(image_files) - subjects_processed
        
        if file_mode == 'a' and num_samples_written > 0:
            print(f"Newly added: {num_samples_written} slices from {subjects_processed} subjects")
            if skipped_count > 0:
                print(f"Skipped: {skipped_count} subjects (invalid zoom values or no valid slices)")
            print(f"Total in file: {total_slices_in_file} slices from {unique_subjects} subjects")
        elif file_mode == 'a' and num_samples_written == 0:
            # Resume mode but no new data (either all failed or all were already done)
            if len(image_files) > 0:
                print("⚠️  Warning: No new data added! All subjects in this run failed processing.")
            print(f"Total in file: {total_slices_in_file} slices from {unique_subjects} subjects")
        else:
            print(f"Successfully processed: {subjects_processed} subjects → {num_samples_written} slices")
            if skipped_count > 0:
                print(f"Skipped: {skipped_count} subjects (invalid zoom values or no valid slices)")
            print(f"Total: {num_samples_written} slices from {unique_subjects} subjects")
        print(f"All images are exactly {target_size}×{target_size}")
        
        if total_slices_in_file == 0:
            print("⚠️  Warning: HDF5 file is empty! No valid data was processed.")
            return
        
        print(f"Final array shapes:")
        print(f"  Images: {grp['orig_dataset'].shape}")
        print(f"  Labels: {grp['aseg_dataset'].shape}")
        print(f"  Weights: {grp['weight_dataset'].shape}")
        
        # Verify all dimensions are correct
        assert grp['orig_dataset'].shape[1] == target_size and grp['orig_dataset'].shape[2] == target_size
        assert grp['aseg_dataset'].shape[1] == target_size and grp['aseg_dataset'].shape[2] == target_size
        
        # ⚠️ VALIDATION: Check for problematic zoom values in the final HDF5 file
        print(f"\n{'='*80}")
        print(f"ZOOM VALUE VALIDATION")
        print(f"{'='*80}")
        zooms_array = grp['zoom_dataset'][:]
        subjects_array = grp['subject'][:]
        
        # Find slices with zero or near-zero zoom values
        invalid_mask = np.any(np.abs(zooms_array) < 1e-6, axis=1)
        num_invalid = np.sum(invalid_mask)
        
        if num_invalid > 0:
            print(f"⚠️  WARNING: Found {num_invalid} slices with invalid zoom values!")
            print(f"   Total slices: {len(zooms_array)}")
            print(f"   Invalid percentage: {100*num_invalid/len(zooms_array):.2f}%")
            
            # Get unique subjects with problematic zoom values
            invalid_subjects = np.unique(subjects_array[invalid_mask])
            print(f"\n   Affected subjects ({len(invalid_subjects)}):")
            for subj in invalid_subjects[:20]:  # Show first 20
                if isinstance(subj, bytes):
                    subj_str = subj.decode('utf-8')
                else:
                    subj_str = str(subj)
                
                # Get a sample zoom value from this subject
                subj_mask = subjects_array == subj
                sample_zoom = zooms_array[subj_mask & invalid_mask][0]
                print(f"     - {subj_str}: zoom = {sample_zoom}")
            
            if len(invalid_subjects) > 20:
                print(f"     ... and {len(invalid_subjects) - 20} more")
            
            print(f"\n   These invalid zoom values will be handled during training,")
            print(f"   but you should investigate the source NIfTI files.")
        else:
            print(f"✓ All zoom values are valid!")
            print(f"  Total slices checked: {len(zooms_array)}")
            # Show zoom value statistics
            print(f"  Zoom range: [{np.min(zooms_array):.4f}, {np.max(zooms_array):.4f}]")
            print(f"  Zoom mean: {np.mean(zooms_array):.4f}")
        print(f"{'='*80}\n")
        
    print(f"✅ Done! HDF5 file created: {output_hdf5}")
    print(f"   All slices are exactly {target_size}×{target_size} (no dimension mismatches!)")
    
    # Display final memory status
    mem = get_memory_usage()
    if mem:
        print(f"\n📊 Final memory status:")
        print(f"   System: {mem['system_available_gb']:.1f} GB available ({100-mem['system_percent']:.1f}% free)")
        print(f"   This process: {mem['process_rss_gb']:.2f} GB")


# Module-level function for multiprocessing (must be picklable)
def _process_single_subject_wrapper(args):
    """
    Wrapper function for parallel processing.
    Must be at module level to be picklable by multiprocessing.
    """
    idx, image_file, image_suffix, label_suffix, label_dir, plane, slice_thickness, target_size, atlas_manager, preprocess_params, total_subjects = args
    
    subject_name = image_file.name.replace(image_suffix, "")
    label_file = label_dir / f"{subject_name}{label_suffix}"
    
    if not label_file.exists():
        return None, f"Warning: No label file for {subject_name}, skipping"
    
    try:
        # Only show verbose output for every 10th subject to avoid clutter
        show_details = (idx % 50 == 0)
        result = process_subject(image_file, label_file, plane, slice_thickness, target_size, atlas_manager, preprocess_params, verbose=show_details)
        
        if result is None:
            # Could be skipped due to invalid zoom or no valid slices
            return None, f"Processing ({idx}/{total_subjects}): {subject_name} → Skipped"
        
        status_msg = f"Processing ({idx}/{total_subjects}): {subject_name} → {result['num_slices']} slices (scale={result['scale_factor']:.3f})"
        return (result, subject_name), status_msg
        
    except Exception as e:
        return None, f"Error processing {subject_name}: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate HDF5 dataset with proportional resizing (macacaMRINN-style)"
    )
    
    parser.add_argument(
        "--config", type=str, required=True,
        help="Path to YAML config file (SINGLE SOURCE OF TRUTH)"
    )
    parser.add_argument(
        "--split_type", type=str, required=True, choices=["train", "val"],
        help="Which split to generate: train or val"
    )
    parser.add_argument(
        "--atlas", type=str, default=None,
        help="Atlas name (e.g., ARM2, ARM3). If not provided, uses ATLAS_NAME env var or defaults to ARM2"
    )
    
    args = parser.parse_args()
    
    # Load ALL parameters from YAML using unified config utilities
    cfg = load_yaml_config(args.config)
    paths = get_paths_from_config(cfg)
    
    # Determine atlas name from YAML config (CLASS_OPTIONS) or command line
    atlas_name = args.atlas or cfg['DATA']['CLASS_OPTIONS'][0] or os.environ.get('ATLAS_NAME', 'ARM2')
    print(f"Using atlas: {atlas_name}")
    
    # Initialize atlas manager
    atlas_manager = get_atlas_manager(atlas_name)
    
    # Extract parameters from YAML
    data_dir = paths['data_dir']
    plane = cfg['DATA']['PLANE']
    target_size = cfg['DATA']['SIZES'][0]  # First size from list
    thickness = (cfg['MODEL']['NUM_CHANNELS'] - 1) // 2  # Derive from num channels
    num_workers = cfg['TRAIN'].get('NUM_WORKERS', 4)
    
    # Extract preprocessing parameters - SINGLE SOURCE OF TRUTH!
    # These EXACT same parameters will be saved in checkpoint and used in inference
    preprocess_params = cfg['DATA']['PREPROCESSING']
    print(f"\n{'='*80}")
    print(f"PREPROCESSING PARAMETERS (Single Source of Truth)")
    print(f"{'='*80}")
    print(f"  Orientation:      {preprocess_params['ORIENTATION']}")
    print(f"  Image size:       {preprocess_params['IMG_SIZE']}")
    print(f"  Voxel size:       {preprocess_params['VOX_SIZE']}")
    print(f"  Threshold 1mm:    {preprocess_params['THRESHOLD_1MM']}")
    print(f"  Dtype (images):   {preprocess_params['DTYPE_IMAGE']}")
    print(f"  Dtype (labels):   {preprocess_params['DTYPE_LABEL']} (supports negative IDs!)")
    print(f"  Rescale (images): {preprocess_params['RESCALE']}")
    print(f"  Order (image):    {preprocess_params['ORDER_IMAGE']}")
    print(f"  Order (label):    {preprocess_params['ORDER_LABEL']}")
    print(f"{'='*80}\n")
    
    # Select appropriate HDF5 output path based on split type
    output_hdf5 = paths['train_hdf5'] if args.split_type == 'train' else paths['val_hdf5']
    
    # Load split JSON
    split_json = data_dir / "data_split.json"
    subject_filter = None
    if split_json.exists():
        with open(split_json) as f:
            split = json.load(f)
            subject_filter = set(split[args.split_type])
    
    print(f"Configuration from YAML: {args.config}")
    print(f"  Data dir:      {data_dir}")
    print(f"  Plane:         {plane}")
    print(f"  Target size:   {target_size}×{target_size}")
    print(f"  Thickness:     {thickness}")
    print(f"  Workers:       {num_workers}")
    print(f"  Split:         {args.split_type}")
    print(f"  Output HDF5:   {output_hdf5}")
    print()
    
    create_hdf5_dataset(
        data_dir=data_dir,
        output_hdf5=output_hdf5,
        plane=plane,
        target_size=target_size,
        slice_thickness=thickness,
        atlas_manager=atlas_manager,
        preprocess_params=preprocess_params,  # Pass preprocessing params from YAML
        subject_filter=subject_filter,
        num_workers=num_workers
    )


if __name__ == "__main__":
    main()

