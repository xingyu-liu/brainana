#!/usr/bin/env python3
"""
Simple CLI for macacaMRINN - wraps the standalone scripts.

This provides a unified interface but delegates to the individual scripts
to avoid code duplication.
"""

import sys
import argparse
import subprocess
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description='macacaMRINN - Simple neural network toolkit for macaque MRI processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  train      Train a new model
  predict    Run prediction with trained model

Examples:
  # Training
  macaca_cli.py train --data-dir /path/to/data --epochs 50

  # Prediction  
  macaca_cli.py predict --model model.pth --input brain.nii.gz --output mask.nii.gz
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Train command
    train_parser = subparsers.add_parser('train', help='Train a model')
    train_parser.add_argument('--data-dir', required=True, help='Data directory')
    train_parser.add_argument('--epochs', type=int, default=50, help='Number of epochs')
    train_parser.add_argument('--batch-size', type=int, default=8, help='Batch size')
    train_parser.add_argument('--lr', type=float, default=1e-4, help='Learning rate')
    train_parser.add_argument('--modal', default='T1w', help='MRI modality')
    train_parser.add_argument('--label', default='brainmask', help='Label type')
    train_parser.add_argument('--output-dir', default='training_output', help='Output directory')
    train_parser.add_argument('--device', default='auto', help='Device to use')
    train_parser.add_argument('--experiment-name', default='', help='Experiment name')
    
    # Predict command
    predict_parser = subparsers.add_parser('predict', help='Run prediction')
    predict_parser.add_argument('--model', required=True, help='Path to trained model')
    predict_parser.add_argument('--input', required=True, help='Input image path')
    predict_parser.add_argument('--output', required=True, help='Output path')
    predict_parser.add_argument('--config', help='Config file path (optional)')
    predict_parser.add_argument('--device', default='auto', help='Device to use')
    predict_parser.add_argument('--morph-iterations', type=int, default=0, help='Morphological post-processing iterations')
    predict_parser.add_argument('--threshold', type=float, default=0.5, help='Probability threshold')
    predict_parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    # Get script directory
    script_dir = Path(__file__).parent
    
    if args.command == 'train':
        # Build command for run_training.py
        cmd = [
            sys.executable, str(script_dir / 'run_training.py'),
            '--data-dir', args.data_dir,
            '--epochs', str(args.epochs),
            '--batch-size', str(args.batch_size),
            '--lr', str(args.lr),
            '--modal', args.modal,
            '--label', args.label,
            '--output-dir', args.output_dir,
            '--device', args.device,
            '--experiment-name', args.experiment_name
        ]
        
    elif args.command == 'predict':
        # Build command for run_prediction.py
        cmd = [
            sys.executable, str(script_dir / 'run_prediction.py'),
            '--model', args.model,
            '--input', args.input,
            '--output', args.output,
            '--device', args.device,
            '--morph-iterations', str(args.morph_iterations),
            '--threshold', str(args.threshold)
        ]
        
        if args.config:
            cmd.extend(['--config', args.config])
        if args.quiet:
            cmd.append('--quiet')
    
    # Execute the command
    try:
        result = subprocess.run(cmd, check=True)
        sys.exit(result.returncode)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    main()
