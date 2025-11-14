#!/usr/bin/env python3
"""
Training script for macacaMRINN.
"""

import sys
import argparse
import torch
import traceback
from pathlib import Path

from ..train.trainer import Trainer
from ..config import TrainingConfig
from ..utils.gpu import get_device


def main():
    parser = argparse.ArgumentParser(
        description='Train a macacaMRINN model using YAML configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train using YAML config file
  run_training.py --config config_T1w_brainmask_finetune.yaml
  
  # Override specific parameters from config
  run_training.py --config config_T1w_brainmask_finetune.yaml --epochs 100 --batch-size 32
  
  # Use custom output directory
  run_training.py --config config_T1w_brainmask_finetune.yaml --output-dir /custom/output
        """
    )
    
    parser.add_argument('--config', required=True, help='Path to YAML configuration file')
    parser.add_argument('--epochs', type=int, help='Override number of epochs from config')
    parser.add_argument('--batch-size', type=int, help='Override batch size from config')
    parser.add_argument('--lr', type=float, help='Override learning rate from config')
    parser.add_argument('--output-dir', help='Override output directory from config')
    parser.add_argument('--device', help='Override device from config')
    parser.add_argument('--experiment-name', help='Override experiment name from config')
    
    args = parser.parse_args()
    
    # Check if config file exists
    if not Path(args.config).exists():
        print(f"System: configuration file not found - {args.config}")
        sys.exit(1)
    
    try:
        # Load configuration from YAML
        print(f"📁 Loading configuration from: {args.config}")
        config = TrainingConfig.from_yaml(args.config)
        print("✓ Configuration loaded successfully")
        
        # Override config values if command-line arguments are provided
        if args.epochs is not None:
            config.num_epochs = args.epochs
            print(f"🔄 Overriding epochs: {args.epochs}")
        
        if args.batch_size is not None:
            config.batch_size = args.batch_size
            print(f"🔄 Overriding batch size: {args.batch_size}")
        
        if args.lr is not None:
            config.learning_rate = args.lr
            print(f"🔄 Overriding learning rate: {args.lr}")
        
        if args.output_dir is not None:
            config.output_base_dir = args.output_dir
            print(f"🔄 Overriding output directory: {args.output_dir}")
        
        if args.device is not None:
            config.device = args.device
            print(f"🔄 Overriding device: {args.device}")
        
        if args.experiment_name is not None:
            config.experiment_name = args.experiment_name
            print(f"🔄 Overriding experiment name: {args.experiment_name}")
        
        print("🚀 Starting macacaMRINN Training")
        print("=" * 40)
        print(f"📋 Configuration: {config.modal}_{config.label}_{config.experiment_name}")
        print(f"📁 Data directory: {config.dataset}")
        print(f"📊 Training parameters: {config.num_epochs} epochs, batch size {config.batch_size}")
        print(f"🎯 Loss function: {config.loss_type}")
        print(f"⚡ Mixed precision: {config.mixed_precision}")
        print(f"📈 Scheduler: {'Cosine' if config.use_cosine_scheduler else 'ReduceLROnPlateau'}")
        print(f"📁 Output directory: {config.output_dir}")
        
        # Setup device
        if config.device == "auto":
            device = get_device()
        else:
            device = torch.device(config.device)
        
        print(f"🖥️  Using device: {device}")
        if device.type == "cuda":
            print(f"GPU memory: {torch.cuda.get_device_properties(device).total_memory / 1e9:.1f} GB")
        
        # Use the enhanced Trainer class
        try:
            trainer = Trainer(config)
            trainer.train()
            print(f"✅ Training completed! Model saved in: {config.output_dir}")
        
        except Exception as e:
            print(f"❌ Training failed: {e}")
            traceback.print_exc()
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()