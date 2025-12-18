#!/usr/bin/env python3
"""
Configuration management for macacaMRINN training and inference.
"""

import os
import yaml
import json
import glob

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union, Tuple
from pathlib import Path


@dataclass
class TrainingConfig:
    """Simple training configuration with essential parameters only."""
    
    # ============================================================================
    # PATH CONFIGURATION
    # ============================================================================
    TRAINING_DATA_DIR: str                 # Training data directory (contains images/ and labels/ subdirectories, or JSON file)
    OUTPUT_DIR: str                        # Output directory (for logs, checkpoints, HDF5 files)
    
    # ============================================================================
    # REQUIRED PARAMETERS (no defaults - must be provided)
    # ============================================================================
    modal: str                             # Modality: T1w, T2w, EPI
    label: str                             # label type: brainmask, brainhemimask, segmentation, atlas-ARM6
    experiment_name: str = ""              # Experiment name for output directory (optional, used in output path if provided)
       
    # ============================================================================
    # MODEL CONFIGURATION
    # ============================================================================
    model_name: str = "UNet2d"             # Model architecture name
    num_input_slices: int = 3              # Number of input slices
    num_conv_block: int = 5                # Number of convolution blocks
    kernel_root: int = 16                  # Base number of filters
    use_inst_norm: bool = True                   # Use instance normalization (disabled for medical imaging consistency)
    num_classes: int = 2                   # Number of output classes (2 for binary, 5 for multi-class brain segmentation)
    pretrained_model_path: Optional[str] = None  # Pretrained model
    
    # ============================================================================
    # TRAINING CONFIGURATION
    # ============================================================================
    training_mode: str = "fine_tuning"     # Training mode: 'scratch', 'fine_tuning', 'continual_learning'
    
    num_epochs: int = 50                   # Number of epochs
    batch_size: int = 20                   # Batch size: number of volumes processed together (traditional CNN batching)
    enable_dynamic_batch_sizing: bool = False  # Enable automatic batch size adjustment based on available memory
    learning_rate: float = 1e-4            # Learning rate
    weight_decay: float = 0.001            # Weight decay for optimizer
    optimizer: str = "adam"                # Optimizer type: 'adam', 'sgd', 'adamw'
    
    # Loss function
    loss_type: str = 'crossentropy'        # Loss function type: 'dice', 'bce', 'combined', 'crossentropy'
    
    # Learning rate scheduling
    use_cosine_scheduler: bool = True      # Use cosine annealing scheduler
    scheduler_factor: float = 0.5          # ReduceLROnPlateau factor (only used when use_cosine_scheduler=False)
    min_lr: float = 1e-7                  # Minimum learning rate
    warmup_epochs: int = 5                # Warmup epochs for scheduler
    
    # Training control
    patience: int = 20                     # Early stopping patience
    early_stopping_min_delta: float = 0.0  # Minimum change for early stopping
    early_stopping_restore_best_weights: bool = True  # Restore best weights on early stopping
    dropout_rate: float = 0.2              # Dropout rate
    gradient_clip_norm: float = 0.5        # Gradient clipping norm
    checkpoint_frequency: int = 5          # Save checkpoint every N epochs (default: 5)
    
    # Advanced training features
    mixed_precision: bool = True           # Enable mixed precision training
    enable_augmentation: bool = True       # Enable data augmentation
    augmentation: bool = True               # Alias for enable_augmentation (for compatibility)
    enable_plotting: bool = True           # Enable live plotting during training
    plot_interval: int = 1                 # Plot update interval in epochs
    
    # Dynamic batch sizing
    gpu_memory_threshold: float = 0.85    # GPU memory threshold for batch adjustment
    batch_reduction_factor: float = 0.5   # Factor to reduce batch size when OOM
    batch_increase_factor: float = 1.2    # Factor to increase batch size when memory available
    max_batch_size: int = 32              # Maximum batch size for dynamic adjustment
    
    # ============================================================================
    # DATA CONFIGURATION
    # ============================================================================
    rescale_dim: int = 256                 # Input rescale dimension
    validation_split: float = 0.15         # Validation split ratio
    test_split: float = 0.15               # Test split ratio (0 = no test set)
    validation_frequency: int = 1          # Validation frequency in epochs
    validation_metrics: Optional[Dict[str, bool]] = None  # Validation metrics configuration
    
    
    # ============================================================================
    # SYSTEM CONFIGURATION
    # ============================================================================
    device: str = "auto"                   # Device selection
    random_seed: int = 42                  # Random seed for reproducibility
    num_workers: int = 8                   # Data loader workers
    pin_memory: bool = True                # Pin memory for faster data transfer
    log_level: str = "DEBUG"               # Logging level, 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
     
    # ============================================================================
    # AUGMENTATION CONFIGURATION
    # ============================================================================
    augmentation_config: Optional[Dict[str, Any]] = None  # Detailed augmentation settings
    
    # ============================================================================
    # TRAINING LOGGING CONFIGURATION
    # ============================================================================
    # Simplified logging configuration to match current train_log.py:
    enable_progress_bars: bool = True                    # Show progress bars during training
    track_training_metrics: bool = False                 # Track detailed training metrics (Dice, IoU, etc.)
    track_validation_metrics: bool = False               # Track validation metrics
        
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'TrainingConfig':
        """Create a TrainingConfig instance from a YAML file.
        
        Args:
            yaml_path: Path to the YAML configuration file
            
        Returns:
            TrainingConfig instance with values from the YAML file
        """
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"YAML config file not found: {yaml_path}")
        
        with open(yaml_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        
        # Convert numeric strings to proper types
        for key, value in config_dict.items():
            if isinstance(value, str):
                # Try to convert to float if it looks like a number
                if key in ['learning_rate', 'weight_decay', 'min_lr', 'scheduler_factor', 'dropout_rate', 'gradient_clip_norm', 'validation_split', 'test_split', 'early_stopping_min_delta', 'gpu_memory_threshold', 'batch_reduction_factor', 'batch_increase_factor']:
                    try:
                        config_dict[key] = float(value)
                    except ValueError:
                        pass  # Keep as string if conversion fails
                # Try to convert to int if it looks like an integer
                elif key in ['num_epochs', 'batch_size', 'num_input_slices', 'num_conv_block', 'kernel_root', 'num_classes', 'patience', 'rescale_dim', 'validation_frequency', 'warmup_epochs', 'num_workers', 'random_seed', 'plot_interval', 'max_batch_size', 'checkpoint_frequency']:
                    try:
                        config_dict[key] = int(value)
                    except ValueError:
                        pass  # Keep as string if conversion fails
                # Try to convert to bool if it looks like a boolean
                elif key in ['use_inst_norm', 'use_cosine_scheduler', 'mixed_precision', 'enable_augmentation', 'augmentation', 'pin_memory', 'enable_progress_bars', 'track_training_metrics', 'track_validation_metrics', 'enable_dynamic_batch_sizing', 'early_stopping_restore_best_weights', 'enable_plotting']:
                    if value.lower() in ['true', '1', 'yes', 'on']:
                        config_dict[key] = True
                    elif value.lower() in ['false', '0', 'no', 'off']:
                        config_dict[key] = False
        
        return cls(**config_dict)
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.TRAINING_DATA_DIR:
            raise ValueError("TRAINING_DATA_DIR must be specified")
        
        if not os.path.exists(self.TRAINING_DATA_DIR):
            raise FileNotFoundError(f"Training data directory not found: {self.TRAINING_DATA_DIR}")
        
        if not self.OUTPUT_DIR:
            raise ValueError("OUTPUT_DIR must be specified")
        
        # Set output_dir for compatibility with existing code
        self.output_dir = self.OUTPUT_DIR
        
        # HDF5 directory is in TRAINING_DATA_DIR (same location as source data, like FastSurferCNN)
        self.hdf5_dir = self.TRAINING_DATA_DIR
        
        self.create_output_directories()
    
    def create_output_directories(self):
        """Create necessary output directories."""
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, 'checkpoints'), exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, 'logs'), exist_ok=True)
    
    def get_data_paths(self) -> Tuple[List[str], List[str]]:
        """Get the paths to images and labels.
        
        Returns:
            Tuple of (image_files, label_files) lists
        """
        if self.TRAINING_DATA_DIR.endswith('.json'):
            # JSON file format - directly use paths provided in the JSON
            with open(self.TRAINING_DATA_DIR, 'r') as f:
                data = json.load(f)
            
            if 'images' not in data or 'labels' not in data:
                raise ValueError(f"JSON file must contain 'images' and 'labels' keys: {self.TRAINING_DATA_DIR}")
            
            image_files = data['images']
            label_files = data['labels']
            
            # Validate that image and label lists have the same length
            if len(image_files) != len(label_files):
                raise ValueError(f"Mismatch between number of images ({len(image_files)}) and labels ({len(label_files)}) in JSON file")
            
            # Validate that files exist
            missing_images = []
            for i, img_file in enumerate(image_files):
                if not os.path.exists(img_file):
                    missing_images.append(f"  [{i}]: {img_file}")
            
            missing_labels = []
            for i, label_file in enumerate(label_files):
                if not os.path.exists(label_file):
                    missing_labels.append(f"  [{i}]: {label_file}")
            
            if missing_images:
                raise FileNotFoundError(f"Image files not found:\n" + "\n".join(missing_images))
            
            if missing_labels:
                raise FileNotFoundError(f"Label files not found:\n" + "\n".join(missing_labels))
            
            return image_files, label_files
        
        else:
            # Directory format - assume TRAINING_DATA_DIR contains 'images' and 'labels' subdirectories
            images_dir = os.path.join(self.TRAINING_DATA_DIR, 'images')
            labels_dir = os.path.join(self.TRAINING_DATA_DIR, 'labels')
            
            if not os.path.exists(images_dir):
                raise FileNotFoundError(f"Images directory not found: {images_dir}")
            if not os.path.exists(labels_dir):
                raise FileNotFoundError(f"Labels directory not found: {labels_dir}")
            
            # Find image files and corresponding labels
            image_files = sorted(glob.glob(os.path.join(images_dir, '*.nii.gz')))
            
            valid_pairs = []
            for img_file in image_files:
                img_basename = os.path.basename(img_file)
                label_basename = img_basename.replace('.nii.gz', f'_{self.label}.nii.gz')
                label_file = os.path.join(labels_dir, label_basename)
                
                if os.path.exists(label_file):
                    valid_pairs.append((img_file, label_file))
            
            if not valid_pairs:
                raise ValueError(f"No valid image-label pairs found in {self.TRAINING_DATA_DIR}")
            
            image_files, label_files = zip(*valid_pairs)
            return list(image_files), list(label_files)


@dataclass 
class InferenceConfig:
    """Simple inference configuration."""
    
    model_path: str                        # Path to trained model
    input_path: str                        # Input file or directory
    output_path: str = ""                  # Output file or directory
    device: str = "auto"                   # Device selection
    batch_size: int = 4                    # Batch size
    
    def __post_init__(self):
        """Validate configuration."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"Input path not found: {self.input_path}")