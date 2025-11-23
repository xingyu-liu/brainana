#!/usr/bin/env python3

"""
Generate HDF5 training dataset for MRI segmentation with conform() preprocessing.
Uses proportional resizing to maintain aspect ratio, then pads to exact dimensions.
"""

import argparse
import h5py
import nibabel as nib
import numpy as np
import os
import sys
from pathlib import Path
from multiprocessing import Pool
from scipy import ndimage
import json
import gc
import psutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from FastSurferCNN.utils.config_utils import load_yaml_config, get_paths_from_config
from FastSurferCNN.atlas.atlas_manager import get_atlas_manager
from FastSurferCNN.data_loader.data_utils import (
    create_weight_mask,
    filter_blank_slices_thick,
    get_thick_slices,
    transform_axial,
    transform_sagittal,
)
from FastSurferCNN.data_loader.conform import conform


def resize_volume_proportional(volume, target_size=256, order=1):
    from FastSurferCNN.data_loader.data_utils import resize_to_target_size
    
    # Use unified resize function for consistency
    padded, scale_factor = resize_to_target_size(volume, target_size, order=order)
    return padded, scale_factor


def load_and_conform_image(image_path, preprocess_params):
    """Load and preprocess image using conform(). Returns (data, zoom) or (None, None) if invalid."""
    img = nib.load(image_path, mmap=True)
    zoom = img.header.get_zooms()[:3]
    
    if np.any(np.abs(zoom) < 1e-6):
        print(f"  ⚠️  SKIPPING: Invalid zoom values in {image_path.name}")
        return None, None
    
    conformed_img = conform(
        img,
        order=preprocess_params['ORDER_IMAGE'],
        orientation=preprocess_params['ORIENTATION'].lower(),
        img_size=preprocess_params['IMG_SIZE'],
        vox_size=preprocess_params['VOX_SIZE'],
        dtype=np.dtype(preprocess_params['DTYPE_IMAGE']),
        rescale=preprocess_params['RESCALE'],
    )
    
    # conform() already rescales to [0, RESCALE] range - keep that range in HDF5
    # Dataset loader will normalize to [0, 1] by dividing by RESCALE
    data = np.asarray(conformed_img.dataobj).astype(np.float32)
    
    del img, conformed_img
    return data, zoom


def load_and_map_labels(label_path, plane="coronal", atlas_manager=None, preprocess_params=None, num_classes=None):
    """Load and preprocess labels using conform(). Returns dense label array."""
    img = nib.load(label_path, mmap=True)
    
    conformed_img = conform(
        img,
        order=preprocess_params['ORDER_LABEL'],
        orientation=preprocess_params['ORIENTATION'].lower(),
        img_size=preprocess_params['IMG_SIZE'],
        vox_size=preprocess_params['VOX_SIZE'],
        dtype=np.dtype(preprocess_params['DTYPE_LABEL']),
        rescale=None,
    )
    
    sparse_labels = np.asarray(conformed_img.dataobj).astype(np.int32)
    del img, conformed_img
    
    if num_classes == 2:
        unique_labels = np.unique(sparse_labels)
        if not np.all(np.isin(unique_labels, [0, 1])):
            raise ValueError(
                f"Binary mode (NUM_CLASSES=2) requires labels to be 0 (background) and 1 (brain).\n"
                f"Found labels: {unique_labels}\n"
                f"File: {label_path}"
            )
        return sparse_labels
    
    if atlas_manager is None:
        raise ValueError("atlas_manager required for multi-class segmentation (NUM_CLASSES > 2)")
    
    if plane == "sagittal":
        return atlas_manager.map_labels_to_sagittal_dense(sparse_labels)
    else:
        return atlas_manager.map_labels_to_dense(sparse_labels)


def _get_plane_transform(plane):
    """Get transform function and zoom extraction for given plane."""
    if plane == "sagittal":
        return transform_sagittal, lambda z: np.asarray(z)[::-1][:2]
    elif plane == "axial":
        return transform_axial, lambda z: np.asarray(z)[[2, 0]]
    else:  # coronal
        return lambda x: x, lambda z: np.asarray(z)[:2]


def _append_to_datasets(datasets, result, subject_name):
    """Append processed subject data to HDF5 datasets."""
    images_ds, labels_ds, weights_ds, zooms_ds, subjects_ds = datasets
    num_slices = result['num_slices']
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
    
    return num_slices


def process_subject(image_path, label_path, plane, slice_thickness=3, target_size=256, 
                   atlas_manager=None, preprocess_params=None, num_classes=None, verbose=False):
    """Process a single subject's MRI and segmentation."""
    # Validate affine match
    raw_image = nib.load(image_path)
    raw_label = nib.load(label_path)
    if not np.allclose(raw_image.affine, raw_label.affine, atol=1e-3):
        print(f"  ⚠️  WARNING: Image and label affines don't match for {image_path.name}!")
    del raw_image, raw_label
    
    # Load and conform image
    image_data, zoom = load_and_conform_image(image_path, preprocess_params)
    if image_data is None or zoom is None:
        return None
    
    # Validate zoom values
    if not np.all((np.array(zoom) > 0.001) & (np.array(zoom) < 10)):
        return None
    
    # Load and map labels
    if not label_path.exists():
        print(f"  ⚠️  ERROR: Label file does not exist: {label_path}")
        return None
    
    try:
        label_data = load_and_map_labels(label_path, plane, atlas_manager, preprocess_params, num_classes)
    except Exception as e:
        print(f"  ⚠️  ERROR loading labels for {label_path.name}: {e}")
        return None
    
    # Check for all-zero labels (critical error)
    if np.sum(label_data > 0) == 0:
        print(f"  ⚠️  CRITICAL: All labels are zero after conforming! File: {label_path.name}")
        return None
    
    # Get cortex labels for weight mask
    if num_classes == 2:
        cortex_labels = None
    else:
        atlas_config = atlas_manager.get_atlas_config(plane)
        cortex_labels = atlas_config.cortex_labels
    
    # Create weight mask
    weights = create_weight_mask(
        label_data,
        max_weight=5,
        max_edge_weight=5,
        max_hires_weight=5,
        gradient=False,
        cortex_labels=cortex_labels,
        verbose=False
    )
    
    # Transform to requested plane
    transform_func, zoom_extract = _get_plane_transform(plane)
    image_data = transform_func(image_data)
    label_data = transform_func(label_data)
    weights = transform_func(weights)
    zoom_2d = zoom_extract(zoom)
    
    # Resize proportionally
    image_data_resized, scale_factor = resize_volume_proportional(image_data, target_size, order=1)
    label_data_resized, _ = resize_volume_proportional(label_data, target_size, order=0)
    weights_resized, _ = resize_volume_proportional(weights, target_size, order=1)
    
    del image_data, label_data, weights
    
    # Validate scaled zoom values
    zoom_2d_scaled = zoom_2d / scale_factor
    if np.any(np.abs(zoom_2d_scaled) < 1e-6):
        print(f"  ⚠️  SKIPPING: Invalid scaled zoom values for {image_path.name}")
        del image_data_resized, label_data_resized, weights_resized
        gc.collect()
        return None
    
    # Create thick slices
    image_thick = get_thick_slices(image_data_resized, slice_thickness)
    del image_data_resized
    
    # Filter blank slices
    blank_threshold = 10
    label_sum_per_slice = np.sum(label_data_resized, axis=(0, 1))
    max_pixels = int(np.max(label_sum_per_slice))
    slices_above_threshold = int(np.sum(label_sum_per_slice > blank_threshold))
    
    image_slices, label_slices, weights_final = filter_blank_slices_thick(
        image_thick, label_data_resized, weights_resized, threshold=blank_threshold
    )
    del image_thick, label_data_resized, weights_resized
    
    if image_slices.shape[2] == 0:
        if max_pixels == 0:
            print(f"  ⚠️  SKIPPING: All labels are zero for {image_path.name}")
        elif max_pixels < blank_threshold:
            print(f"  ⚠️  SKIPPING: Max pixels/slice ({max_pixels}) < threshold ({blank_threshold}) for {image_path.name}")
        gc.collect()
        return None
    
    # Transpose to (slices, height, width, channels) for images
    image_slices = np.transpose(image_slices, (2, 0, 1, 3))
    label_slices = np.transpose(label_slices, (2, 0, 1))
    weights_final = np.transpose(weights_final, (2, 0, 1))
    
    assert image_slices.shape[1] == target_size and image_slices.shape[2] == target_size
    assert label_slices.shape[1] == target_size and label_slices.shape[2] == target_size
    
    result = {
        'images': image_slices,
        'labels': label_slices,
        'weights': weights_final,
        'zooms': np.tile(zoom_2d_scaled, (image_slices.shape[0], 1)),
        'num_slices': image_slices.shape[0],
        'scale_factor': scale_factor
    }
    
    gc.collect()
    return result


def get_memory_usage():
    """Get current memory usage information."""
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        virtual_mem = psutil.virtual_memory()
        return {
            'process_rss_gb': mem_info.rss / (1024**3),
            'system_available_gb': virtual_mem.available / (1024**3),
            'system_percent': virtual_mem.percent,
        }
    except Exception:
        return None


def check_memory_and_warn(threshold_percent=85):
    """Check system memory usage and warn if high."""
    mem = get_memory_usage()
    if mem and mem['system_percent'] > threshold_percent:
        print(f"\n⚠️  WARNING: High memory usage ({mem['system_percent']:.1f}%, {mem['system_available_gb']:.1f} GB available)")
        print(f"   Process: {mem['process_rss_gb']:.2f} GB. Consider reducing num_workers.\n")
        return False
    return True


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


def _find_image_label_pairs(image_dir, label_dir):
    """Find matching image-label pairs."""
    all_image_files = sorted(image_dir.glob("*.nii.gz"))
    matched_pairs = []
    
    for image_file in all_image_files:
        base_name = image_file.name.replace('.nii.gz', '')
        label_pattern = f"{base_name}_*.nii.gz"
        label_matches = sorted(label_dir.glob(label_pattern))
        
        if len(label_matches) == 1:
            matched_pairs.append((image_file, label_matches[0]))
        # elif len(label_matches) == 0:
        #     print(f"Warning: No label file found for {image_file.name}")
        # else:
        #     print(f"Warning: Multiple label files found for {image_file.name}, skipping")
    
    return [pair[0] for pair in matched_pairs], [pair[1] for pair in matched_pairs]


def _check_resume_capability(output_hdf5, target_size, preprocess_params):
    """Check if HDF5 file exists and can be resumed."""
    already_processed = set()
    file_mode = 'w'
    
    if output_hdf5.exists():
        try:
            with h5py.File(output_hdf5, 'r') as hf_check:
                if str(target_size) in hf_check and 'subject' in hf_check[str(target_size)]:
                    subjects_in_hdf5 = hf_check[str(target_size)]['subject'][:]
                    already_processed = set(
                        str(s.decode('utf-8') if isinstance(s, bytes) else s).strip()
                        for s in subjects_in_hdf5
                    )
                    print(f"✓ Found {len(already_processed)} subjects already processed")
                    
                    if 'preprocessing_metadata' in hf_check:
                        meta = hf_check['preprocessing_metadata']
                        for key, expected_value in preprocess_params.items():
                            if key in meta.attrs and meta.attrs[key] != expected_value:
                                print(f"  ⚠️  Warning: Preprocessing parameter '{key}' differs!")
                    
                    file_mode = 'a'
        except Exception as e:
            print(f"  ⚠️  Could not read existing file ({e}), will overwrite")
    
    return already_processed, file_mode


def create_hdf5_dataset(
    data_dir,
    output_hdf5,
    plane="coronal",
    target_size=256,
    slice_thickness=3,
    atlas_manager=None,
    preprocess_params=None,
    num_classes=None,
    subject_filter=None,
    num_workers=1,
):
    """Create HDF5 dataset using conform() preprocessing.
    
    When plane="mixed", processes each subject for all three planes (axial, coronal, sagittal)
    and stores all slices in a single HDF5 file for plane-agnostic training.
    """
    image_dir = Path(data_dir) / "images"
    label_dir = Path(data_dir) / "labels"
    
    all_image_files, all_label_files = _find_image_label_pairs(image_dir, label_dir)
    
    if subject_filter is not None:
        image_files = [
            img for img in all_image_files
            if img.name.replace('.nii.gz', '').strip() in subject_filter
        ]
        print(f"Filtered {len(image_files)}/{len(all_image_files)} subjects based on data split")
    else:
        image_files = all_image_files
        print(f"Found {len(image_files)} subjects")
    
    # Handle mixed plane mode
    if plane == "mixed":
        planes_to_process = ["axial", "coronal", "sagittal"]
        print(f"Processing MIXED planes (axial, coronal, sagittal)")
        print(f"  Each subject will be processed for all 3 planes")
        print(f"  Target size: {target_size}×{target_size}, output: {output_hdf5}")
    else:
        planes_to_process = [plane]
        print(f"Processing plane: {plane}, target size: {target_size}×{target_size}, output: {output_hdf5}")
    
    if num_workers > 1:
        print(f"Using {num_workers} parallel workers")
    
    mem = get_memory_usage()
    if mem:
        print(f"Memory: {mem['system_available_gb']:.1f} GB available ({100-mem['system_percent']:.1f}% free)")
        if mem['system_percent'] > 70:
            print(f"  ⚠️  Warning: System using {mem['system_percent']:.1f}% of memory")
    
    output_hdf5.parent.mkdir(parents=True, exist_ok=True)
    
    already_processed, file_mode = _check_resume_capability(output_hdf5, target_size, preprocess_params)
    
    # For mixed mode, track which (subject, plane) combinations are already processed
    if plane == "mixed" and already_processed:
        # Load existing subject-plane pairs from HDF5
        with h5py.File(output_hdf5, 'r') as hf_check:
            if str(target_size) in hf_check and 'subject' in hf_check[str(target_size)]:
                # For mixed mode, we can't easily track which planes are done per subject
                # So we'll just check if subject exists (conservative approach)
                existing_subjects = set(
                    str(s.decode('utf-8') if isinstance(s, bytes) else s).strip()
                    for s in hf_check[str(target_size)]['subject'][:]
                )
                original_count = len(image_files)
                image_files = [
                    img for img in image_files 
                    if img.name.replace('.nii.gz', '').strip() not in existing_subjects
                ]
                print(f"Filtered: {original_count} → {len(image_files)} subjects remaining (mixed mode)")
                if len(image_files) == 0:
                    print("✅ All subjects already processed!")
                    return
    elif already_processed:
        original_count = len(image_files)
        image_files = [
            img for img in image_files 
            if img.name.replace('.nii.gz', '').strip() not in already_processed
        ]
        print(f"Filtered: {original_count} → {len(image_files)} subjects remaining")
        if len(image_files) == 0:
            print("✅ All subjects already processed!")
            return
    
    total_subjects = len(image_files)
    num_samples_written = 0
    
    with h5py.File(output_hdf5, file_mode) as hf:
        if 'preprocessing_metadata' not in hf:
            preprocess_metadata = hf.create_group('preprocessing_metadata')
            for key, value in preprocess_params.items():
                preprocess_metadata.attrs[key] = value
            preprocess_metadata.attrs['created_with_conform'] = True
            preprocess_metadata.attrs['version'] = '1.0'
            preprocess_metadata.attrs['plane_mode'] = plane  # Store plane mode
            print("✓ Saved preprocessing metadata")
        
        if str(target_size) not in hf:
            grp = hf.create_group(str(target_size))
            initial_img_shape = (0, target_size, target_size, slice_thickness * 2 + 1)
            initial_label_weight_shape = (0, target_size, target_size)
            initial_zoom_shape = (0, 2)
            
            images_ds = _create_resizable_dataset(grp, 'orig_dataset', np.float32, initial_img_shape)
            labels_ds = _create_resizable_dataset(grp, 'aseg_dataset', np.int32, initial_label_weight_shape)
            weights_ds = _create_resizable_dataset(grp, 'weight_dataset', np.float32, initial_label_weight_shape)
            zooms_ds = _create_resizable_dataset(grp, 'zoom_dataset', np.float32, initial_zoom_shape)
            subjects_ds = grp.create_dataset('subject', (0,), maxshape=(None,), dtype=h5py.string_dtype(encoding='utf-8'))
            print(f"✓ Created new datasets for size {target_size}")
        else:
            grp = hf[str(target_size)]
            images_ds = grp['orig_dataset']
            labels_ds = grp['aseg_dataset']
            weights_ds = grp['weight_dataset']
            zooms_ds = grp['zoom_dataset']
            subjects_ds = grp['subject']
            print(f"✓ Appending to existing datasets (current size: {images_ds.shape[0]} slices)")
        
        datasets = (images_ds, labels_ds, weights_ds, zooms_ds, subjects_ds)
        
        # Build process args: for mixed mode, process each subject for all planes
        process_args = []
        for idx, image_file in enumerate(image_files, 1):
            for p in planes_to_process:
                process_args.append((
                    idx, image_file, label_dir, p, slice_thickness, target_size, 
                    atlas_manager, preprocess_params, num_classes, total_subjects
                ))
        
        subjects_processed = 0
        subjects_processed_set = set()  # Track unique subjects processed
        
        if num_workers > 1:
            with Pool(processes=num_workers) as pool:
                for result_data, msg in pool.imap_unordered(_process_single_subject_wrapper, process_args):
                    print(msg)
                    if result_data is not None:
                        result, subject_name = result_data
                        num_samples_written += _append_to_datasets(datasets, result, subject_name)
                        subjects_processed_set.add(subject_name)
                        if len(subjects_processed_set) % 10 == 0:
                            check_memory_and_warn()
        else:
            for args in process_args:
                result_data, msg = _process_single_subject_wrapper(args)
                print(msg)
                if result_data is not None:
                    result, subject_name = result_data
                    num_samples_written += _append_to_datasets(datasets, result, subject_name)
                    subjects_processed_set.add(subject_name)
                    if len(subjects_processed_set) % 10 == 0:
                        check_memory_and_warn()
        
        subjects_processed = len(subjects_processed_set)
    
    # Final summary
    with h5py.File(output_hdf5, 'r') as hf:
        grp = hf[str(target_size)]
        unique_subjects = len(set(grp['subject'][:]))
        total_slices_in_file = grp['orig_dataset'].shape[0]
        skipped_count = len(image_files) - subjects_processed
        
        if plane == "mixed":
            expected_slices_per_subject = 3  # Each subject processed for 3 planes
            print(f"\nMixed-plane mode summary:")
            print(f"  Processed {subjects_processed} subjects × {len(planes_to_process)} planes = {subjects_processed * len(planes_to_process)} subject-plane combinations")
        else:
            expected_slices_per_subject = 1
        
        if file_mode == 'a' and num_samples_written > 0:
            print(f"Newly added: {num_samples_written} slices from {subjects_processed} subjects")
        elif file_mode == 'a' and num_samples_written == 0 and len(image_files) > 0:
            print("⚠️  Warning: No new data added! All subjects failed processing.")
        else:
            print(f"Successfully processed: {subjects_processed} subjects → {num_samples_written} slices")
        
        if skipped_count > 0:
            print(f"Skipped: {skipped_count} subjects (invalid zoom values or no valid slices)")
        
        print(f"Total in file: {total_slices_in_file} slices from {unique_subjects} subjects")
        if plane == "mixed":
            print(f"  (Mixed-plane mode: slices from axial, coronal, and sagittal planes)")
        print(f"All images are exactly {target_size}×{target_size}")
        
        if total_slices_in_file == 0:
            print("⚠️  Warning: HDF5 file is empty!")
            return
        
        print(f"Final shapes: Images {grp['orig_dataset'].shape}, Labels {grp['aseg_dataset'].shape}")
        
        # Validate zoom values
        zooms_array = grp['zoom_dataset'][:]
        invalid_mask = np.any(np.abs(zooms_array) < 1e-6, axis=1)
        num_invalid = np.sum(invalid_mask)
        
        if num_invalid > 0:
            print(f"\n⚠️  WARNING: Found {num_invalid} slices with invalid zoom values ({100*num_invalid/len(zooms_array):.2f}%)")
            subjects_array = grp['subject'][:]
            invalid_subjects = np.unique(subjects_array[invalid_mask])
            print(f"   Affected subjects ({len(invalid_subjects)}): {list(invalid_subjects[:10])}")
            if len(invalid_subjects) > 10:
                print(f"   ... and {len(invalid_subjects) - 10} more")
        else:
            print(f"\n✓ All zoom values valid (range: [{np.min(zooms_array):.4f}, {np.max(zooms_array):.4f}])")
    
    print(f"✅ Done! HDF5 file: {output_hdf5}")


def _process_single_subject_wrapper(args):
    """Wrapper function for parallel processing."""
    idx, image_file, label_dir, plane, slice_thickness, target_size, atlas_manager, preprocess_params, num_classes, total_subjects = args
    
    base_name = image_file.name.replace('.nii.gz', '')
    label_pattern = f"{base_name}_*.nii.gz"
    label_matches = sorted(label_dir.glob(label_pattern))
    subject_name = image_file.name.replace('.nii.gz', '').strip()
    
    if len(label_matches) == 0:
        return None, f"Warning: No label file found for {subject_name}, skipping"
    elif len(label_matches) > 1:
        return None, f"Warning: Multiple label files found for {subject_name}, skipping"
    
    label_file = label_matches[0]
    
    try:
        result = process_subject(
            image_file, label_file, plane, slice_thickness, target_size,
            atlas_manager, preprocess_params, num_classes, verbose=False
        )
        
        if result is None:
            return None, f"Processing ({idx}/{total_subjects}): {subject_name} → Skipped"
        
        status_msg = f"Processing ({idx}/{total_subjects}): {subject_name} → {result['num_slices']} slices"
        return (result, subject_name), status_msg
        
    except Exception as e:
        return None, f"Error processing {subject_name}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Generate HDF5 dataset with proportional resizing")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--split_type", type=str, required=True, choices=["train", "val"], help="train or val")
    parser.add_argument("--atlas", type=str, default=None, help="Atlas name (e.g., ARM2, ARM3)")
    
    args = parser.parse_args()
    
    cfg = load_yaml_config(args.config)
    paths = get_paths_from_config(cfg)
    num_classes = cfg['MODEL']['NUM_CLASSES']
    is_binary = (num_classes == 2)
    
    if is_binary:
        print(f"Binary segmentation mode (NUM_CLASSES={num_classes})")
        atlas_manager = None
    else:
        if cfg['DATA']['CLASS_OPTIONS'] is None or not cfg['DATA']['CLASS_OPTIONS']:
            raise ValueError(
                f"Multi-class mode (NUM_CLASSES={num_classes}) requires CLASS_OPTIONS in config."
            )
        
        if args.atlas:
            atlas_name = args.atlas
        elif cfg['DATA']['CLASS_OPTIONS'] and cfg['DATA']['CLASS_OPTIONS'][0]:
            atlas_name = cfg['DATA']['CLASS_OPTIONS'][0]
        else:
            raise ValueError("Multi-class mode requires atlas name in CLASS_OPTIONS or --atlas argument.")
        
        print(f"Multi-class segmentation mode (NUM_CLASSES={num_classes}), atlas: {atlas_name}")
        atlas_manager = get_atlas_manager(atlas_name)
    
    data_dir = paths['data_dir']
    plane = cfg['DATA']['PLANE']
    target_size = cfg['DATA']['SIZES'][0]
    thickness = (cfg['MODEL']['NUM_CHANNELS'] - 1) // 2
    num_workers = cfg['TRAIN'].get('NUM_WORKERS', 4)
    preprocess_params = cfg['DATA']['PREPROCESSING']
    
    print(f"\nPreprocessing parameters:")
    print(f"  Orientation: {preprocess_params['ORIENTATION']}")
    print(f"  Image size: {preprocess_params['IMG_SIZE']}, Voxel size: {preprocess_params['VOX_SIZE']}")
    print(f"  Dtype (image/label): {preprocess_params['DTYPE_IMAGE']}/{preprocess_params['DTYPE_LABEL']}")
    
    output_hdf5 = paths['train_hdf5'] if args.split_type == 'train' else paths['val_hdf5']
    
    split_json = data_dir / "data_split.json"
    subject_filter = None
    if split_json.exists():
        with open(split_json) as f:
            split = json.load(f)
            subject_filter = set(split[args.split_type])
    
    print(f"\nConfiguration:")
    print(f"  Data dir: {data_dir}, Plane: {plane}, Target size: {target_size}×{target_size}")
    print(f"  Thickness: {thickness}, Workers: {num_workers}, Split: {args.split_type}")
    print(f"  Output HDF5: {output_hdf5}\n")
    
    create_hdf5_dataset(
        data_dir=data_dir,
        output_hdf5=output_hdf5,
        plane=plane,
        target_size=target_size,
        slice_thickness=thickness,
        atlas_manager=atlas_manager,
        preprocess_params=preprocess_params,
        num_classes=num_classes,
        subject_filter=subject_filter,
        num_workers=num_workers
    )


if __name__ == "__main__":
    main()
