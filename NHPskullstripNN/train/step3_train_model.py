#!/usr/bin/env python3

"""
Main training script for NHPskullstripNN.

This script loads a YAML configuration file and runs training using the Trainer class.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from NHPskullstripNN.config import TrainingConfig
from NHPskullstripNN.train.trainer import Trainer


def main():
    parser = argparse.ArgumentParser(description="Train NHPskullstripNN model")
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

