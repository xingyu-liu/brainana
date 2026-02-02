#!/usr/bin/env python3

"""
Split data into training and validation sets for nhp_skullstrip_nn.

This script creates a data_split.json file that can be used by step2_create_hdf5.py
to filter subjects for train/val splits.
"""

import argparse
import os
import json
from pathlib import Path
import random
import sys

# Add src/ to path for nhp_skullstrip_nn imports (train/ -> nhp_skullstrip_nn -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_skullstrip_nn.config import TrainingConfig


def split_data(
    config,
    val_split=0.2,
    test_split=0.0,
    seed=42,
    min_train_subjects=5
):
    """
    Split data into train/val/test sets
    
    Parameters
    ----------
    config : TrainingConfig
        Configuration object with dataset paths
    val_split : float
        Fraction of data to use for validation
    test_split : float
        Fraction of data to use for testing
    seed : int
        Random seed for reproducibility
    min_train_subjects : int
        Minimum number of subjects to keep for training
    """
    # Get data file lists
    image_files, label_files = config.get_data_paths()
    
    # Extract subject names (remove .nii.gz extension and path)
    subjects = []
    for img_file in image_files:
        subject_name = Path(img_file).stem.replace('.nii', '').replace('.gz', '')
        subjects.append(subject_name)
    
    print(f"Total subjects: {len(subjects)}")
    
    # Calculate split sizes
    total_subjects = len(subjects)
    min_required = min_train_subjects + 1  # Need at least one for validation
    
    if total_subjects < min_required:
        print(f"Warning: Not enough subjects for splitting (need at least {min_required})")
        print("Using all subjects for training")
        train_subjects = subjects
        val_subjects = []
        test_subjects = []
    else:
        # Shuffle and split
        random.seed(seed)
        shuffled_subjects = subjects.copy()
        random.shuffle(shuffled_subjects)
        
        if test_split > 0:
            # Three-way split
            num_test = max(1, int(total_subjects * test_split))
            num_val = max(1, int(total_subjects * val_split))
            num_train = total_subjects - num_test - num_val
            
            # Ensure minimum training subjects
            if num_train < min_train_subjects:
                num_train = min_train_subjects
                remaining = total_subjects - num_train
                num_val = max(1, int(remaining * (val_split / (val_split + test_split))))
                num_test = remaining - num_val
            
            test_subjects = shuffled_subjects[:num_test]
            val_subjects = shuffled_subjects[num_test:num_test + num_val]
            train_subjects = shuffled_subjects[num_test + num_val:]
        else:
            # Two-way split
            num_val = max(1, int(total_subjects * val_split))
            num_train = total_subjects - num_val
            
            # Ensure minimum training subjects
            if num_train < min_train_subjects:
                num_train = min_train_subjects
                num_val = total_subjects - num_train
            
            test_subjects = []
            val_subjects = shuffled_subjects[:num_val]
            train_subjects = shuffled_subjects[num_val:]
    
    # Save split info
    split_info = {
        'train': sorted(train_subjects),
        'val': sorted(val_subjects),
        'test': sorted(test_subjects) if test_split > 0 else [],
        'total': total_subjects,
        'seed': seed,
        'val_split': val_split,
        'test_split': test_split
    }
    
    # Save to training data directory
    if Path(config.TRAINING_DATA_DIR).is_file():
        # If TRAINING_DATA_DIR is a JSON file, save split in the same directory
        split_file = Path(config.TRAINING_DATA_DIR).parent / "data_split.json"
    else:
        # If TRAINING_DATA_DIR is a directory, save split in that directory
        split_file = Path(config.TRAINING_DATA_DIR) / "data_split.json"
    
    split_file.parent.mkdir(parents=True, exist_ok=True)
    with open(split_file, 'w') as f:
        json.dump(split_info, f, indent=2)
    
    print(f"\nSplit information saved to: {split_file}")
    print(f"Training subjects: {len(train_subjects)}")
    print(f"Validation subjects: {len(val_subjects)}")
    if test_subjects:
        print(f"Test subjects: {len(test_subjects)}")
    
    return train_subjects, val_subjects, test_subjects


def main():
    parser = argparse.ArgumentParser(description="Split data into train/val/test sets")
    
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML config file"
    )
    parser.add_argument(
        "--val_split",
        type=float,
        default=None,
        help="Fraction for validation (default: use from config)"
    )
    parser.add_argument(
        "--test_split",
        type=float,
        default=None,
        help="Fraction for testing (default: use from config)"
    )
    args = parser.parse_args()
    
    # Load config
    config = TrainingConfig.from_yaml(args.config)
    
    # Get split ratios from config or args
    val_split = args.val_split if args.val_split is not None else getattr(config, 'validation_split', 0.2)
    test_split = args.test_split if args.test_split is not None else getattr(config, 'test_split', 0.0)
    seed = getattr(config, 'random_seed', 42)
    
    print(f"Configuration from YAML: {args.config}")
    print(f"  Training data dir: {config.TRAINING_DATA_DIR}")
    print(f"  Val split: {val_split}")
    print(f"  Test split: {test_split}")
    print(f"  Random seed: {seed}")
    print()
    
    split_data(
        config=config,
        val_split=val_split,
        test_split=test_split,
        seed=seed,
        min_train_subjects=5
    )


if __name__ == "__main__":
    main()

