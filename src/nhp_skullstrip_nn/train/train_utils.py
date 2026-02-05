"""
Training utilities for nhp_skullstrip_nn.
"""

import os
import sys
import json
import logging
import torch
import numpy as np
import pandas as pd
import matplotlib
from pathlib import Path
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split
from datetime import datetime
from typing import Tuple, Optional

from ..data.datasets import FileListDataset
from ..data.hdf5_dataset import HDF5Dataset
from ..utils.log import get_logger
from ..data.transforms import create_transforms_from_config, create_training_transforms

# %%
def setup_logging(output_dir: str, log_level: str = None) -> logging.Logger:
    """Setup logging for training."""
    log_dir = os.path.join(output_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'training_{timestamp}.log')
    
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Configure logging
    if log_level is None:
        log_level = 'INFO'
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Suppress verbose matplotlib font debugging even when log_level is DEBUG
    matplotlib_logger = logging.getLogger('matplotlib.font_manager')
    matplotlib_logger.setLevel(logging.WARNING)
    
    # Also suppress PIL/Pillow debugging if present
    pil_logger = logging.getLogger('PIL')
    pil_logger.setLevel(logging.WARNING)
    
    logger = logging.getLogger('nhp_skullstrip_nn.training')
    logger.info(f"Logging: initialized with file {os.path.basename(log_file)}")
    
    return logger


def prepare_data_loaders(config, logger: Optional[logging.Logger] = None):
    """Prepare training, validation, and test data loaders.
    
    Supports both HDF5 mode (faster, preprocessed) and file-based mode (on-the-fly processing).
    HDF5 mode is used if hdf5_dir is set in config and HDF5 files exist.
    """
    if logger is None:
        logger = get_logger()
    
    # Always auto-detect HDF5 files (hdf5_dir is set in config.__post_init__)
    hdf5_dir = Path(config.hdf5_dir)
    train_hdf5 = hdf5_dir / "train_dataset.h5"
    val_hdf5 = hdf5_dir / "val_dataset.h5"
    
    # Check if HDF5 files exist
    if train_hdf5.exists() and val_hdf5.exists():
        logger.info("📦 Using HDF5 dataset mode (preprocessed data)")
        return _prepare_hdf5_data_loaders(config, train_hdf5, val_hdf5, logger)
    
    # File-based mode (original implementation)
    logger.info("📁 Using file-based dataset mode (on-the-fly processing)")
    
    # Get data file lists (now returns files directly instead of directories)
    image_files, label_files = config.get_data_paths()
    
    logger.info(f"Dataset: {len(image_files)} valid image-label pairs found")
    
    # Split data
    if getattr(config, 'test_split', 0) > 0:
        # Three-way split
        temp_imgs, test_imgs, temp_labels, test_labels = train_test_split(
            image_files, label_files,
            test_size=config.test_split,
            random_state=getattr(config, 'random_seed', 42)
        )
        
        val_size_adjusted = getattr(config, 'validation_split', 0.2) / (1 - config.test_split)
        train_imgs, val_imgs, train_labels, val_labels = train_test_split(
            temp_imgs, temp_labels,
            test_size=val_size_adjusted,
            random_state=getattr(config, 'random_seed', 42)
        )
        
        logger.info(f"Data split: Train={len(train_imgs)}, Val={len(val_imgs)}, Test={len(test_imgs)}")
        
        # Save test set information for later evaluation
        test_info = {
            'images': list(test_imgs),
            'labels': list(test_labels), 
            'count': len(test_imgs)
        }
        
        test_info_path = os.path.join(config.output_dir, 'testdataset_info.json')
        with open(test_info_path, 'w') as f:
            json.dump(test_info, f, indent=2)
        
        logger.info(f"Test dataset info saved: {test_info_path}")
        
    else:
        # Two-way split
        train_imgs, val_imgs, train_labels, val_labels = train_test_split(
            image_files, label_files, 
            test_size=getattr(config, 'validation_split', 0.2), 
            random_state=getattr(config, 'random_seed', 42)
        )
        test_imgs, test_labels = [], []
        logger.info(f"Data split: Train={len(train_imgs)}, Val={len(val_imgs)}")
    
    # Setup transforms for training
    train_transform = None
    if getattr(config, 'enable_augmentation', False):
        augmentation_config = getattr(config, 'augmentation_config', None)
        if augmentation_config:

            train_transform = create_transforms_from_config(augmentation_config)
            if logger:
                logger.info("✨ Data augmentation enabled with custom config")
        else:
            train_transform = create_training_transforms()
            if logger:
                logger.info("✨ Data augmentation enabled with default settings")
    elif logger:
        logger.info("📊 No data augmentation applied")

    # Create datasets
    train_dataset = FileListDataset(
        list(train_imgs), 
        list(train_labels), 
        config.num_input_slices, 
        config.rescale_dim,
        transform=train_transform
    )
    
    val_dataset = FileListDataset(
        list(val_imgs), 
        list(val_labels), 
        config.num_input_slices, 
        config.rescale_dim
    )
    
    # Data loader settings
    batch_size = getattr(config, 'batch_size', 4)
    num_workers = getattr(config, 'num_workers', 8) if getattr(config, 'num_workers', 8) else 0
    
    loader_kwargs = {
        'batch_size': batch_size,
        'num_workers': num_workers,
        'pin_memory': torch.cuda.is_available(),
        'collate_fn': lambda batch: batch  # Handle BlockDataset objects
    }
    
    train_loader = DataLoader(train_dataset, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_dataset, shuffle=False, **loader_kwargs)
    
    # Create test loader if needed
    test_loader = None
    if test_imgs:
        test_dataset = FileListDataset(
            list(test_imgs), 
            list(test_labels), 
            config.num_input_slices, 
            config.rescale_dim
        )
        test_loader = DataLoader(test_dataset, shuffle=False, **loader_kwargs)
    
    return train_loader, val_loader, test_loader, (test_imgs, test_labels) if test_imgs else None


def _prepare_hdf5_data_loaders(config, train_hdf5, val_hdf5, logger: Optional[logging.Logger] = None):
    """Prepare data loaders from HDF5 files."""
    if logger is None:
        logger = get_logger()
    
    # Setup transforms for training
    train_transform = None
    if getattr(config, 'enable_augmentation', False):
        augmentation_config = getattr(config, 'augmentation_config', None)
        if augmentation_config:
            train_transform = create_transforms_from_config(augmentation_config)
            if logger:
                logger.info("✨ Data augmentation enabled with custom config")
        else:
            train_transform = create_training_transforms()
            if logger:
                logger.info("✨ Data augmentation enabled with default settings")
    elif logger:
        logger.info("📊 No data augmentation applied")
    
    # Create HDF5 datasets
    train_dataset = HDF5Dataset(str(train_hdf5), transform=train_transform)
    val_dataset = HDF5Dataset(str(val_hdf5), transform=None)
    
    # Log dataset info
    train_metadata = train_dataset.get_metadata()
    val_metadata = val_dataset.get_metadata()
    logger.info(f"Train HDF5: {train_metadata['num_samples']} samples")
    logger.info(f"Val HDF5: {val_metadata['num_samples']} samples")
    
    # Data loader settings
    batch_size = getattr(config, 'batch_size', 4)
    num_workers = getattr(config, 'num_workers', 8) if getattr(config, 'num_workers', 8) else 0
    
    # Standard collate function for HDF5 (returns tuples directly)
    def collate_fn(batch):
        images = torch.stack([item[0] for item in batch])
        labels = torch.stack([item[1] for item in batch])
        return {'image': images, 'label': labels}
    
    loader_kwargs = {
        'batch_size': batch_size,
        'num_workers': num_workers,
        'pin_memory': torch.cuda.is_available(),
        'collate_fn': collate_fn
    }
    
    train_loader = DataLoader(train_dataset, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_dataset, shuffle=False, **loader_kwargs)
    
    return train_loader, val_loader, None, None


def adjust_batch_size_during_training(current_batch_size: int, memory_usage: dict, 
                                    config, logger: Optional[logging.Logger] = None) -> int:
    """Dynamically adjust batch size during training based on memory usage.
    
    Args:
        current_batch_size: Current batch size
        memory_usage: Current memory usage information
        config: Training configuration object
        logger: Optional logger for output
        
    Returns:
        Adjusted batch size
    """
    if not torch.cuda.is_available():
        return current_batch_size
    
    # Get memory thresholds
    gpu_memory_threshold = getattr(config, 'gpu_memory_threshold', 0.85)  # 85% of GPU memory
    batch_reduction_factor = getattr(config, 'batch_reduction_factor', 0.5)
    batch_increase_factor = getattr(config, 'batch_increase_factor', 1.2)
    
    # Check if we're using too much GPU memory
    if 'gpu_allocated' in memory_usage:
        gpu_allocated_gb = memory_usage['gpu_allocated']
        gpu_total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        memory_usage_ratio = gpu_allocated_gb / gpu_total_gb
        
        if memory_usage_ratio > gpu_memory_threshold:
            # Reduce batch size
            new_batch_size = max(1, int(current_batch_size * batch_reduction_factor))
            if logger and new_batch_size != current_batch_size:
                logger.warning(f"GPU memory usage high ({memory_usage_ratio:.1%}), "
                             f"reducing batch size from {current_batch_size} to {new_batch_size}")
            return new_batch_size
        
        # Check if we can increase batch size (memory usage is low)
        elif memory_usage_ratio < gpu_memory_threshold * 0.7:  # 70% of threshold
            # Increase batch size
            new_batch_size = min(
                getattr(config, 'max_batch_size', 32),
                int(current_batch_size * batch_increase_factor)
            )
            if logger and new_batch_size != current_batch_size:
                logger.info(f"GPU memory usage low ({memory_usage_ratio:.1%}), "
                           f"increasing batch size from {current_batch_size} to {new_batch_size}")
            return new_batch_size
    
    return current_batch_size


def count_parameters(model: torch.nn.Module) -> Tuple[int, int]:
    """Count total and trainable parameters in a model."""
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total_params, trainable_params


def format_time(seconds: float) -> str:
    """Format time duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def save_training_summary(config, metrics: dict, output_dir: str):
    """Save training summary to JSON file."""
    summary = {
        'config': config.to_dict() if hasattr(config, 'to_dict') else config.__dict__,
        'final_metrics': metrics,
        'timestamp': datetime.now().isoformat(),
        'pytorch_version': torch.__version__,
        'cuda_available': torch.cuda.is_available(),
    }
    
    if torch.cuda.is_available():
        summary['cuda_version'] = torch.version.cuda
        summary['gpu_count'] = torch.cuda.device_count()
    
    summary_file = os.path.join(output_dir, 'training_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    get_logger().info(f"Training summary saved: {summary_file}")
