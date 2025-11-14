#!/usr/bin/env python3

"""
Split monkey MRI data into training and validation sets

This script uses the config_utils module to resolve paths from YAML config.
All paths are derived from BASE_DIR in the YAML file (single source of truth).
Supports any atlas via command line or environment variable.
"""

import argparse
import os
import shutil
from pathlib import Path
import random
import json
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from FastSurferCNN.utils.config_utils import load_yaml_config, get_paths_from_config, print_paths_summary


def split_data(
    data_dir,
    atlas_name="ARM3",
    val_split=0.2,
    seed=42,
    min_train_subjects=5
):
    """
    Split monkey data into train/val sets
    
    Parameters
    ----------
    data_dir : Path
        Directory containing T1w_images and T1w_atlas-{ATLAS_NAME}
    atlas_name : str
        Name of the atlas (e.g., ARM2, ARM3)
    val_split : float
        Fraction of data to use for validation
    seed : int
        Random seed for reproducibility
    min_train_subjects : int
        Minimum number of subjects to keep for training
    """
    data_dir = Path(data_dir)
    image_dir = data_dir / "T1w_images"
    label_dir = data_dir / f"T1w_atlas-{atlas_name}"
    
    # Get all subjects
    image_files = sorted(image_dir.glob("*.nii.gz"))
    # Handle .nii.gz files properly (two extensions)
    subjects = [f.name.split(".nii.gz")[0].replace("_T1w", "") for f in image_files]
    
    # Remove any subjects without labels
    valid_subjects = []
    for subj in subjects:
        label_file = label_dir / f"{subj}_T1w_atlas-{atlas_name}.nii.gz"
        if label_file.exists():
            valid_subjects.append(subj)
    
    print(f"Total subjects: {len(subjects)}")
    print(f"Valid subjects (with labels): {len(valid_subjects)}")
    
    if len(valid_subjects) < min_train_subjects + 1:
        print(f"Warning: Not enough subjects for splitting (need at least {min_train_subjects + 1})")
        print("Using all subjects for training")
        train_subjects = valid_subjects
        val_subjects = []
    else:
        # Shuffle and split
        random.seed(seed)
        random.shuffle(valid_subjects)
        
        num_val = max(1, int(len(valid_subjects) * val_split))
        num_train = len(valid_subjects) - num_val
        
        # Ensure minimum training subjects
        if num_train < min_train_subjects:
            num_train = min_train_subjects
            num_val = len(valid_subjects) - num_train
        
        val_subjects = valid_subjects[:num_val]
        train_subjects = valid_subjects[num_val:]
    
    # print(f"\nTraining subjects: {len(train_subjects)}")
    # print(f"Validation subjects: {len(val_subjects)}")
    
    # Save split info
    split_info = {
        'train': train_subjects,
        'val': val_subjects,
        'total': len(valid_subjects),
        'seed': seed,
        'val_split': val_split
    }
    
    split_file = data_dir / "data_split.json"
    with open(split_file, 'w') as f:
        json.dump(split_info, f, indent=2)
    
    print(f"\nSplit information saved to: {split_file}")
    # print("\nTraining subjects:")
    # for subj in train_subjects:
    #     print(f"  {subj}")
    
    # if val_subjects:
    #     print("\nValidation subjects:")
    #     for subj in val_subjects:
    #         print(f"  {subj}")
    
    return train_subjects, val_subjects


def main():
    parser = argparse.ArgumentParser(description="Split monkey data into train/val sets")
    
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML config file (SINGLE SOURCE OF TRUTH)"
    )
    parser.add_argument(
        "--val_split",
        type=float,
        default=0.2,
        help="Fraction for validation (default: 0.2 = 20%%, can override YAML)"
    )
    parser.add_argument(
        "--atlas", type=str, default=None,
        help="Atlas name (e.g., ARM2, ARM3). If not provided, uses ATLAS_NAME env var or defaults to ARM2"
    )
    
    args = parser.parse_args()
    
    # Load config from YAML using unified config utilities
    cfg = load_yaml_config(args.config)
    paths = get_paths_from_config(cfg, args.config)
    
    # Determine atlas name from config (single source of truth)
    atlas_name = args.atlas or os.environ.get('ATLAS_NAME')
    if not atlas_name:
        # Extract from config using same logic as config_utils
        if 'CLASS_OPTIONS' in cfg.get('DATA', {}):
            atlas_name = cfg['DATA']['CLASS_OPTIONS'][0]
        elif 'ATLAS_NAME' in cfg:
            atlas_name = cfg['ATLAS_NAME']
        else:
            atlas_name = 'ARM2'  # Fallback default
    
    print(f"Using atlas: {atlas_name}")
    
    # Get data directory and seed from resolved paths
    data_dir = paths['data_dir']
    seed = cfg.get('RNG_SEED', 42)
    
    print(f"Configuration from YAML: {args.config}")
    print(f"  Base directory:  {paths['base_dir']}")
    print(f"  Data directory:  {data_dir}")
    print(f"  Atlas:           {atlas_name}")
    print(f"  Val split:       {args.val_split}")
    print(f"  Random seed:     {seed}")
    print()
    
    split_data(
        data_dir=data_dir,
        atlas_name=atlas_name,
        val_split=args.val_split,
        seed=seed,
        min_train_subjects=5
    )


if __name__ == "__main__":
    main()

