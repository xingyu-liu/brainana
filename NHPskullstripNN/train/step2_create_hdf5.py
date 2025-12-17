#!/usr/bin/env python3

"""
Generate HDF5 training dataset for NHPskullstripNN.

This script preprocesses NIfTI volumes, extracts slices from three orientations
(axial, sagittal, coronal), and stores them in HDF5 format for faster training.
"""

import argparse
import h5py
import nibabel as nib
import numpy as np
import os
import sys
import signal
from pathlib import Path
from multiprocessing import Pool
import json
import gc
import psutil
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).parent.parent))

from NHPskullstripNN.config import TrainingConfig


# Global flag for graceful shutdown
_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    print(f"\n⚠️  Received {signal_name} signal. Initiating graceful shutdown...")
    print("  → Finishing current operations and closing HDF5 file properly...")
    _shutdown_requested = True


def resize_volume_proportional(volume, target_size=256, order=1):
    """
    Resize volume proportionally to fit within target_size, then pad to exact dimensions.
    
    Args:
        volume: 3D numpy array [H, W, D]
        target_size: Target size for each dimension
        order: Interpolation order (0=nearest, 1=linear)
        
    Returns:
        resized_volume: Resized and padded volume [target_size, target_size, D']
        scale_factor: Scale factor used for resizing
    """
    # Find max dimension
    max_dim = max(volume.shape)
    scale_factor = target_size / max_dim
    
    # Calculate new dimensions
    new_shape = [int(d * scale_factor) for d in volume.shape]
    
    # Convert to tensor for interpolation
    volume_tensor = torch.from_numpy(volume).float()
    
    # Add batch and channel dimensions for interpolation
    if volume_tensor.dim() == 3:
        volume_tensor = volume_tensor.unsqueeze(0).unsqueeze(0)  # [1, 1, H, W, D]
    
    # Resize using trilinear (order=1) or nearest (order=0) interpolation
    mode = 'trilinear' if order == 1 else 'nearest'
    align_corners = False if order == 1 else None
    
    resized = F.interpolate(
        volume_tensor,
        size=new_shape,
        mode=mode,
        align_corners=align_corners
    )
    
    # Remove batch and channel dimensions
    resized = resized.squeeze(0).squeeze(0).numpy()
    
    # Pad to target_size
    padded = np.zeros((target_size, target_size, target_size), dtype=resized.dtype)
    pad_h = (target_size - resized.shape[0]) // 2
    pad_w = (target_size - resized.shape[1]) // 2
    pad_d = (target_size - resized.shape[2]) // 2
    
    padded[
        pad_h:pad_h + resized.shape[0],
        pad_w:pad_w + resized.shape[1],
        pad_d:pad_d + resized.shape[2]
    ] = resized
    
    return padded, scale_factor


def get_thick_slices(volume, slice_thickness=3):
    """
    Extract thick slices from volume (concatenate consecutive slices).
    
    Args:
        volume: 3D numpy array [H, W, D]
        slice_thickness: Number of consecutive slices to combine
        
    Returns:
        thick_slices: 4D array [H, W, D, channels] where channels = slice_thickness * 2 + 1
    """
    H, W, D = volume.shape
    num_channels = slice_thickness * 2 + 1
    thick_slices = np.zeros((H, W, D, num_channels), dtype=volume.dtype)
    
    for d in range(D):
        # Collect slices around current position
        slices = []
        for offset in range(-slice_thickness, slice_thickness + 1):
            idx = d + offset
            if idx < 0:
                slices.append(volume[:, :, 0])
            elif idx >= D:
                slices.append(volume[:, :, D - 1])
            else:
                slices.append(volume[:, :, idx])
        
        thick_slices[:, :, d, :] = np.stack(slices, axis=-1)
    
    return thick_slices


def filter_blank_slices(image_slices, label_slices, threshold=10):
    """
    Filter out slices with too few label pixels.
    
    Args:
        image_slices: 4D array [H, W, D, channels]
        label_slices: 3D array [H, W, D]
        threshold: Minimum number of non-zero label pixels per slice
        
    Returns:
        filtered_image: Filtered image slices [H, W, D', channels]
        filtered_label: Filtered label slices [H, W, D']
    """
    # Calculate label sum per slice
    label_sum_per_slice = np.sum(label_slices > 0, axis=(0, 1))
    valid_mask = label_sum_per_slice > threshold
    
    if np.sum(valid_mask) == 0:
        return np.zeros((image_slices.shape[0], image_slices.shape[1], 0, image_slices.shape[3])), \
               np.zeros((label_slices.shape[0], label_slices.shape[1], 0))
    
    filtered_image = image_slices[:, :, valid_mask, :]
    filtered_label = label_slices[:, :, valid_mask]
    
    return filtered_image, filtered_label


def extract_slices_from_volume(volume, label, num_slices=3, rescale_dim=256):
    """
    Extract slices from volume in three orientations (axial, sagittal, coronal).
    Matches the behavior of BlockDataset.
    
    Args:
        volume: 3D numpy array [H, W, D]
        label: 3D numpy array [H, W, D]
        num_slices: Number of consecutive slices to combine
        rescale_dim: Target dimension for rescaling
        
    Returns:
        all_image_slices: List of 3D arrays [num_slices, H, W] for each orientation
        all_label_slices: List of 2D arrays [H, W] for each orientation
    """
    # Resize volume and label proportionally
    volume_resized, scale_factor = resize_volume_proportional(volume, rescale_dim, order=1)
    label_resized, _ = resize_volume_proportional(label, rescale_dim, order=0)
    
    # Convert to torch for processing
    volume_tensor = torch.from_numpy(volume_resized).float()
    label_tensor = torch.from_numpy(label_resized).long()
    
    # Get rescaled dimensions
    H, W, D = volume_resized.shape
    
    # Create slice lists for each orientation (matching BlockDataset logic)
    # Axial slices (along first dimension)
    slice_list_0 = []
    for i in range(H - num_slices + 1):
        slice_list_0.append(range(i, i + num_slices))
    
    # Sagittal slices (along second dimension)
    slice_list_1 = []
    for i in range(W - num_slices + 1):
        slice_list_1.append(range(i, i + num_slices))
    
    # Coronal slices (along third dimension)
    slice_list_2 = []
    for i in range(D - num_slices + 1):
        slice_list_2.append(range(i, i + num_slices))
    
    all_image_slices = []
    all_label_slices = []
    
    # Extract axial slices
    for slice_range in slice_list_0:
        image_tmp = volume_tensor[slice_range, :, :]  # [num_slices, W, D]
        label_tmp = label_tensor[slice_range, :, :]   # [num_slices, W, D]
        
        # Pad to rescale_dim
        image_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.float32)
        label_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.long)
        
        slice_h, slice_w = image_tmp.shape[1], image_tmp.shape[2]
        image_block[:, :slice_h, :slice_w] = image_tmp
        label_block[:, :slice_h, :slice_w] = label_tmp
        
        # Filter blank slices
        if torch.sum(label_block > 0) > 10:
            all_image_slices.append(image_block.numpy())
            all_label_slices.append(label_block[0].numpy())  # Use middle slice for label
    
    # Extract sagittal slices
    for slice_range in slice_list_1:
        image_tmp = volume_tensor[:, slice_range, :]  # [H, num_slices, D]
        image_tmp = image_tmp.permute([1, 0, 2])      # [num_slices, H, D]
        label_tmp = label_tensor[:, slice_range, :]    # [H, num_slices, D]
        label_tmp = label_tmp.permute([1, 0, 2])      # [num_slices, H, D]
        
        # Pad to rescale_dim
        image_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.float32)
        label_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.long)
        
        slice_h, slice_w = image_tmp.shape[1], image_tmp.shape[2]
        image_block[:, :slice_h, :slice_w] = image_tmp
        label_block[:, :slice_h, :slice_w] = label_tmp
        
        # Filter blank slices
        if torch.sum(label_block > 0) > 10:
            all_image_slices.append(image_block.numpy())
            all_label_slices.append(label_block[0].numpy())  # Use middle slice for label
    
    # Extract coronal slices
    for slice_range in slice_list_2:
        image_tmp = volume_tensor[:, :, slice_range]  # [H, W, num_slices]
        image_tmp = image_tmp.permute([2, 0, 1])       # [num_slices, H, W]
        label_tmp = label_tensor[:, :, slice_range]   # [H, W, num_slices]
        label_tmp = label_tmp.permute([2, 0, 1])      # [num_slices, H, W]
        
        # Pad to rescale_dim
        image_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.float32)
        label_block = torch.zeros([num_slices, rescale_dim, rescale_dim], dtype=torch.long)
        
        slice_h, slice_w = image_tmp.shape[1], image_tmp.shape[2]
        image_block[:, :slice_h, :slice_w] = image_tmp
        label_block[:, :slice_h, :slice_w] = label_tmp
        
        # Filter blank slices
        if torch.sum(label_block > 0) > 10:
            all_image_slices.append(image_block.numpy())
            all_label_slices.append(label_block[0].numpy())  # Use middle slice for label
    
    return all_image_slices, all_label_slices


def process_subject(image_path, label_path, num_slices=3, rescale_dim=256, verbose=False):
    """Process a single subject's MRI and segmentation."""
    try:
        # Load image
        image_nifti = nib.load(image_path)
        image_data = np.array(image_nifti.get_fdata(), dtype=np.float32)
        
        # Normalize to [0, 1]
        img_min, img_max = image_data.min(), image_data.max()
        if img_max > img_min:
            image_data = (image_data - img_min) / (img_max - img_min)
        
        # Load label
        label_nifti = nib.load(label_path)
        label_data = np.array(label_nifti.get_fdata(), dtype=np.int64)
        
        # Extract slices
        image_slices, label_slices = extract_slices_from_volume(
            image_data, label_data, num_slices, rescale_dim
        )
        
        if len(image_slices) == 0:
            return None
        
        # Stack slices - images are [num_slices, H, W], labels are [H, W]
        images_array = np.stack(image_slices, axis=0)  # [N, num_slices, H, W]
        labels_array = np.stack(label_slices, axis=0)  # [N, H, W]
        
        # Ensure all slices are exactly rescale_dim x rescale_dim
        # (they should already be from extract_slices_from_volume, but double-check)
        assert images_array.shape[2] == rescale_dim and images_array.shape[3] == rescale_dim
        assert labels_array.shape[1] == rescale_dim and labels_array.shape[2] == rescale_dim
        
        result = {
            'images': images_array,
            'labels': labels_array,
            'num_slices': len(image_slices)
        }
        
        del image_data, label_data, image_slices, label_slices
        gc.collect()
        
        return result
        
    except Exception as e:
        if verbose:
            print(f"  ⚠️  Error processing {image_path.name}: {e}")
        return None


def _create_resizable_dataset(hf_group, name, dtype, shape, compression='gzip', compression_opts=4, chunks=True):
    """Create a resizable HDF5 dataset with compression."""
    return hf_group.create_dataset(
        name, 
        data=np.empty(shape, dtype=dtype), 
        maxshape=(None,) + shape[1:],
        compression=compression, 
        compression_opts=compression_opts,
        chunks=chunks
    )


def _append_to_datasets(datasets, result, subject_name):
    """Append processed subject data to HDF5 datasets."""
    images_ds, labels_ds, subjects_ds = datasets
    num_slices = result['num_slices']
    current_len = images_ds.shape[0]
    
    images_ds.resize(current_len + num_slices, axis=0)
    images_ds[current_len:current_len + num_slices] = result['images']
    
    labels_ds.resize(current_len + num_slices, axis=0)
    labels_ds[current_len:current_len + num_slices] = result['labels']
    
    subjects_ds.resize(current_len + num_slices, axis=0)
    subjects_ds[current_len:current_len + num_slices] = [subject_name] * num_slices
    
    return num_slices


def _check_resume_capability(output_hdf5, num_slices, rescale_dim):
    """Check if HDF5 file exists and can be resumed."""
    already_processed = set()
    file_mode = 'w'
    
    if output_hdf5.exists():
        file_size = output_hdf5.stat().st_size
        print(f"Found existing HDF5 file: {output_hdf5.name} ({file_size / (1024**2):.1f} MB)")
        
        try:
            with h5py.File(output_hdf5, 'r') as hf_check:
                if 'images' in hf_check and 'subject' in hf_check:
                    subjects_in_hdf5 = hf_check['subject'][:]
                    already_processed = set(
                        str(s.decode('utf-8') if isinstance(s, bytes) else s).strip()
                        for s in subjects_in_hdf5
                    )
                    print(f"✓ Found {len(already_processed)} subjects already processed")
                    file_mode = 'a'
                else:
                    print(f"  ⚠️  Existing file doesn't contain expected datasets, will overwrite")
        except (OSError, IOError, RuntimeError) as e:
            error_msg = str(e)
            if "address of object past end of allocation" in error_msg or "corrupt" in error_msg.lower():
                print(f"  ⚠️  HDF5 file appears corrupted: {error_msg}")
                print(f"  → Will overwrite with a new file")
            else:
                print(f"  ⚠️  Could not read existing file ({error_msg}), will overwrite")
        except Exception as e:
            print(f"  ⚠️  Unexpected error reading file ({type(e).__name__}: {e}), will overwrite")
    
    return already_processed, file_mode


def create_hdf5_dataset(
    image_files,
    label_files,
    output_hdf5,
    num_slices=3,
    rescale_dim=256,
    subject_filter=None,
    num_workers=1,
):
    """Create HDF5 dataset from image and label files."""
    print(f"Processing {len(image_files)} subjects")
    print(f"  Target size: {rescale_dim}×{rescale_dim}, Slice thickness: {num_slices}")
    print(f"  Output: {output_hdf5}")
    
    if num_workers > 1:
        print(f"Using {num_workers} parallel workers")
    
    mem = psutil.virtual_memory()
    print(f"Memory: {mem.available / (1024**3):.1f} GB available ({100-mem.percent:.1f}% free)")
    if mem.percent > 70:
        print(f"  ⚠️  Warning: System using {mem.percent:.1f}% of memory")
    
    output_hdf5.parent.mkdir(parents=True, exist_ok=True)
    
    already_processed, file_mode = _check_resume_capability(output_hdf5, num_slices, rescale_dim)
    
    if subject_filter is not None:
        # Filter files based on subject_filter
        filtered_pairs = []
        for img_file, label_file in zip(image_files, label_files):
            subject_name = Path(img_file).stem.replace('.nii', '').replace('.gz', '')
            if subject_name in subject_filter:
                filtered_pairs.append((img_file, label_file))
        image_files, label_files = zip(*filtered_pairs) if filtered_pairs else ([], [])
        print(f"Filtered {len(image_files)}/{len(already_processed) + len(image_files)} subjects based on data split")
    
    # Remove already processed subjects
    if already_processed:
        original_count = len(image_files)
        remaining_pairs = []
        for img_file, label_file in zip(image_files, label_files):
            subject_name = Path(img_file).stem.replace('.nii', '').replace('.gz', '')
            if subject_name not in already_processed:
                remaining_pairs.append((img_file, label_file))
        
        if remaining_pairs:
            image_files, label_files = zip(*remaining_pairs)
            image_files, label_files = list(image_files), list(label_files)
        else:
            image_files, label_files = [], []
        
        print(f"Filtered: {original_count} → {len(image_files)} subjects remaining")
        if len(image_files) == 0:
            print("✅ All subjects already processed!")
            return
    
    total_subjects = len(image_files)
    num_samples_written = 0
    
    with h5py.File(output_hdf5, file_mode) as hf:
        # Create datasets if they don't exist
        if 'images' not in hf:
            # Shape: [N, num_slices, H, W] for images, [N, H, W] for labels
            initial_shape_img = (0, num_slices, rescale_dim, rescale_dim)
            initial_shape_label = (0, rescale_dim, rescale_dim)
            
            images_ds = _create_resizable_dataset(hf, 'images', np.float32, initial_shape_img)
            labels_ds = _create_resizable_dataset(hf, 'labels', np.int64, initial_shape_label)
            subjects_ds = hf.create_dataset('subject', (0,), maxshape=(None,), dtype=h5py.string_dtype(encoding='utf-8'))
            
            # Store metadata
            hf.attrs['num_slices'] = num_slices
            hf.attrs['rescale_dim'] = rescale_dim
            hf.attrs['version'] = '1.0'
            print(f"✓ Created new datasets")
        else:
            images_ds = hf['images']
            labels_ds = hf['labels']
            subjects_ds = hf['subject']
            print(f"✓ Appending to existing datasets (current size: {images_ds.shape[0]} slices)")
        
        datasets = (images_ds, labels_ds, subjects_ds)
        
        # Process subjects
        subjects_processed = 0
        subjects_processed_set = set()
        
        try:
            if num_workers > 1:
                process_args = [
                    (idx, Path(img_file), Path(label_file), num_slices, rescale_dim, total_subjects)
                    for idx, (img_file, label_file) in enumerate(zip(image_files, label_files), 1)
                ]
                
                with Pool(processes=num_workers) as pool:
                    for result_data, msg in pool.imap_unordered(_process_single_subject_wrapper, process_args):
                        if _shutdown_requested:
                            print("\n⚠️  Shutdown requested. Stopping processing...")
                            pool.terminate()
                            pool.join()
                            break
                        print(msg)
                        if result_data is not None:
                            result, subject_name = result_data
                            num_samples_written += _append_to_datasets(datasets, result, subject_name)
                            subjects_processed_set.add(subject_name)
            else:
                for idx, (img_file, label_file) in enumerate(zip(image_files, label_files), 1):
                    if _shutdown_requested:
                        print("\n⚠️  Shutdown requested. Stopping processing...")
                        break
                    
                    subject_name = Path(img_file).stem.replace('.nii', '').replace('.gz', '')
                    result = process_subject(
                        Path(img_file), Path(label_file), num_slices, rescale_dim, verbose=False
                    )
                    
                    if result is None:
                        print(f"Processing ({idx}/{total_subjects}): {subject_name} → Skipped")
                        continue
                    
                    num_samples_written += _append_to_datasets(datasets, result, subject_name)
                    subjects_processed_set.add(subject_name)
                    print(f"Processing ({idx}/{total_subjects}): {subject_name} → {result['num_slices']} slices")
        except KeyboardInterrupt:
            print("\n⚠️  Keyboard interrupt received. Closing HDF5 file properly...")
            _shutdown_requested = True
        
        subjects_processed = len(subjects_processed_set)
        
        if _shutdown_requested:
            print(f"\n⚠️  Processing interrupted. Saved {num_samples_written} slices from {subjects_processed} subjects before shutdown.")
            print(f"  → HDF5 file has been properly closed and is safe to resume later.")
            return
    
    # Final summary
    with h5py.File(output_hdf5, 'r') as hf:
        unique_subjects = len(set(hf['subject'][:]))
        total_slices_in_file = hf['images'].shape[0]
        skipped_count = len(image_files) - subjects_processed
        
        print(f"\nSuccessfully processed: {subjects_processed} subjects → {num_samples_written} slices")
        if skipped_count > 0:
            print(f"Skipped: {skipped_count} subjects (no valid slices)")
        print(f"Total in file: {total_slices_in_file} slices from {unique_subjects} subjects")
        print(f"All images are exactly {rescale_dim}×{rescale_dim}")
        
        if total_slices_in_file == 0:
            print("⚠️  Warning: HDF5 file is empty!")
            return
        
        print(f"Final shapes: Images {hf['images'].shape}, Labels {hf['labels'].shape}")
    
    print(f"✅ Done! HDF5 file: {output_hdf5}")


def _process_single_subject_wrapper(args):
    """Wrapper function for parallel processing."""
    idx, image_file, label_file, num_slices, rescale_dim, total_subjects = args
    
    subject_name = image_file.stem.replace('.nii', '').replace('.gz', '')
    
    try:
        result = process_subject(
            image_file, label_file, num_slices, rescale_dim, verbose=False
        )
        
        if result is None:
            return None, f"Processing ({idx}/{total_subjects}): {subject_name} → Skipped"
        
        status_msg = f"Processing ({idx}/{total_subjects}): {subject_name} → {result['num_slices']} slices"
        return (result, subject_name), status_msg
        
    except Exception as e:
        return None, f"Error processing {subject_name}: {e}"


def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, _signal_handler)  # kill command
    
    parser = argparse.ArgumentParser(description="Generate HDF5 dataset for NHPskullstripNN")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--split_type", type=str, required=True, choices=["train", "val"], help="train or val")
    parser.add_argument("--num_workers", type=int, default=4, help="Number of parallel workers")
    
    args = parser.parse_args()
    
    # Load config
    config = TrainingConfig.from_yaml(args.config)
    
    # Get data paths
    image_files, label_files = config.get_data_paths()
    
    # Use HDF5 directory from config
    hdf5_dir = Path(config.hdf5_dir)
    hdf5_dir.mkdir(parents=True, exist_ok=True)
    output_hdf5 = hdf5_dir / f"{args.split_type}_dataset.h5"
    
    # Load split information if available
    if Path(config.TRAINING_DATA_DIR).is_file():
        split_json = Path(config.TRAINING_DATA_DIR).parent / "data_split.json"
    else:
        split_json = Path(config.TRAINING_DATA_DIR) / "data_split.json"
    
    subject_filter = None
    if split_json.exists():
        with open(split_json) as f:
            split = json.load(f)
            subject_filter = set(split[args.split_type])
    
    print(f"\nConfiguration:")
    print(f"  Config: {args.config}")
    print(f"  Split type: {args.split_type}")
    print(f"  Num slices: {config.num_input_slices}, Rescale dim: {config.rescale_dim}")
    print(f"  Workers: {args.num_workers}")
    print(f"  Output HDF5: {output_hdf5}\n")
    
    create_hdf5_dataset(
        image_files=image_files,
        label_files=label_files,
        output_hdf5=output_hdf5,
        num_slices=config.num_input_slices,
        rescale_dim=config.rescale_dim,
        subject_filter=subject_filter,
        num_workers=args.num_workers
    )


if __name__ == "__main__":
    main()

