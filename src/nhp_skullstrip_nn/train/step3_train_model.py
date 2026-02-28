#!/usr/bin/env python3

"""
Main training script for nhp_skullstrip_nn.

This script loads a YAML configuration file and runs training using the Trainer class.
"""

import argparse
import sys
from pathlib import Path

# Add src/ to path for nhp_skullstrip_nn imports (train/ -> nhp_skullstrip_nn -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_skullstrip_nn.config import TrainingConfig
from nhp_skullstrip_nn.train.trainer import Trainer


def main():
    parser = argparse.ArgumentParser(description="Train nhp_skullstrip_nn model")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML config file"
    )
    
    args = parser.parse_args()
    
    # Load config from YAML
    config = TrainingConfig.from_yaml(args.config)
    
    # HDF5 files are automatically detected in train_utils.prepare_data_loaders()
    # Just check if they exist for user info
    train_hdf5 = Path(config.hdf5_dir) / "train_dataset.h5"
    val_hdf5 = Path(config.hdf5_dir) / "val_dataset.h5"
    
    if train_hdf5.exists() and val_hdf5.exists():
        print(f"✓ HDF5 datasets found at {config.hdf5_dir}")
        print(f"  Training will use HDF5 mode for faster data loading")
    else:
        print(f"ℹ️  HDF5 datasets not found, will use file-based mode")
        print(f"   Run step1_split_data.py and step2_create_hdf5.py for faster training")
    
    # Create trainer and run training
    trainer = Trainer(config)
    trainer.train()


if __name__ == "__main__":
    main()

