#!/usr/bin/env python3
"""
Prediction script for macacaMRINN.
"""

import sys
import argparse
import torch
import traceback
from pathlib import Path
import json

from ..inference.prediction import predict_volumes
from ..config import TrainingConfig
from ..utils.gpu import get_device
from ..utils.log import setup_logging
from ..model import ModelLoader


def main():
    parser = argparse.ArgumentParser(
        description='Run prediction with trained macacaMRINN model',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic prediction (config extracted from checkpoint)
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz
  
  # With config file (if checkpoint doesn't contain config)
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --config config.json
  
  # With specific device
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --device cuda:0
  
  # With morphological post-processing
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --morph-iterations 2
  
  # With custom rescale dimension and slice count
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --rescale-dim 512 --num-slices 5
  
  # With metrics computation (requires input label)
  run_prediction.py --model model.pth --input brain.nii.gz --input-label truth.nii.gz --output label.nii.gz --compute-metrics
  
  # Force softmax application
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --force-softmax
  
  # Save only probability map (no binary label)
  run_prediction.py --model model.pth --input brain.nii.gz --output label.nii.gz --no-save-label --save-prob-map
        """
    )
    
    parser.add_argument('--model', required=True, 
                       help='Path to trained model (.pth or .model file)')
    parser.add_argument('--input', required=True,
                       help='Path to input image')
    parser.add_argument('--input-label', default=None,
                       help='Path to input label')
    parser.add_argument('--output', required=True,
                       help='Path to save prediction output')
    parser.add_argument('--config', default=None,
                       help='Path to training configuration file (.json). Optional if checkpoint contains config.')
    parser.add_argument('--device', default='auto',
                       help='Device to use (auto, cpu, cuda:0, etc.)')
    parser.add_argument('--rescale-dim', type=int, default=256,
                       help='Dimension to rescale input to (default: 256)')
    parser.add_argument('--num-slices', type=int, default=3,
                       help='Number of input slices (default: 3)')
    parser.add_argument('--save-label', action='store_true', default=True,
                       help='Save label output (default: True)')
    parser.add_argument('--no-save-label', action='store_false', dest='save_label',
                       help='Disable saving label output')
    parser.add_argument('--save-prob-map', action='store_true', default=True,
                       help='Save probability map output (default: True)')
    parser.add_argument('--no-save-prob-map', action='store_false', dest='save_prob_map',
                       help='Disable saving probability map output')
    parser.add_argument('--compute-metrics', action='store_true', default=False,
                       help='Compute Dice and IoU metrics if input label is provided')
    parser.add_argument('--force-softmax', action='store_true', default=None,
                       help='Force softmax application. Use --force-softmax if model outputs logits, omit if model already outputs probabilities.')
    parser.add_argument('--morph-iterations', type=int, default=0,
                       help='Morphological post-processing iterations (default: 0)')
    parser.add_argument('--plot-QC', action='store_true', default=False,
                       help='Plot QC snapshots')
    parser.add_argument('--quiet', action='store_true',
                       help='Suppress verbose output')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging('macacaMRINN.prediction')
    
    # Validate model file
    if not Path(args.model).exists():
        logger.error(f"❌ Model file not found: {args.model}")
        sys.exit(1)
    
    # Validate input file
    if not Path(args.input).exists():
        logger.error(f"❌ Input file not found: {args.input}")
        sys.exit(1)
    
    # Try to load config from checkpoint first
    config = None
    config_source = "checkpoint"
    
    try:
        logger.info("🔍 Loading checkpoint to extract config...")
        checkpoint = torch.load(args.model, map_location='cpu', weights_only=False)
        
        if 'config' in checkpoint:
            checkpoint_config = checkpoint['config']
            # Filter to valid parameters
            from dataclasses import fields
            valid_params = {field.name for field in fields(TrainingConfig)}
            filtered_config = {k: v for k, v in checkpoint_config.items() if k in valid_params}
            config = TrainingConfig(**filtered_config)
            logger.info(f"✅ Config extracted from checkpoint")
        else:
            logger.warning("⚠️  No config found in checkpoint")
            config_source = None
    except Exception as e:
        logger.warning(f"⚠️  Could not load checkpoint: {e}")
        config_source = None
    
    # If no config from checkpoint, try to load from file, otherwise use default params
    if config is None:
        if args.config is  not None:
            # Load configuration from file
            try:
                with open(args.config, 'r') as f:
                    config_dict = json.load(f)
                logger.info(f"✅ Config loaded from file: {args.config}")
                config_source = "file"
            except Exception as e:
                logger.error(f"❌ Error loading config file: {e}")
                sys.exit(1)
    
    # Show device info
    if args.device == 'auto':
        device = get_device()
        logger.info(f"🔍 Auto-selected device: {device}")
    else:
        logger.info(f"🔍 Using device: {args.device}")
    
    logger.info(f"📁 Model: {args.model}")
    logger.info(f"📥 Input: {args.input}")
    if args.input_label:
        logger.info(f"📥 Input Label: {args.input_label}")
    logger.info(f"📤 Output: {args.output}")
    logger.info(f"⚙️  Config: {config_source} ({'checkpoint' if config_source == 'checkpoint' else args.config})")
    logger.info(f"🔧 Rescale dimension: {args.rescale_dim}")
    logger.info(f"🔧 Number of slices: {args.num_slices}")
    logger.info(f"🔧 Morph iterations: {args.morph_iterations}")
    logger.info(f"🔧 Save label: {args.save_label}")
    logger.info(f"🔧 Save prob map: {args.save_prob_map}")
    logger.info(f"🔧 Plot QC: {args.plot_QC}")
    if args.compute_metrics:
        logger.info("🔧 Metrics computation enabled (Dice + IoU)")
    if args.force_softmax is not None:
        logger.info(f"🔧 Force softmax: {args.force_softmax}")
    logger.info("-" * 50)
    logger.info(f'Running inference')
    
    try:
        # Load model
        model = ModelLoader.load_model_from_file(
            model_path=args.model,
            device_id=args.device,
            config=config,
            logger=None
        )

        # Run prediction with loaded config
        result = predict_volumes(
            model=model,
            rescale_dim=args.rescale_dim,
            num_slices=args.num_slices,
            num_classes=getattr(config, 'num_classes', 2) if config else None,  # Use num_classes from checkpoint config
            input_image=args.input,
            input_label=args.input_label,
            save_label=args.save_label,
            save_prob_map=args.save_prob_map,
            output_path=args.output,
            compute_metrics=args.compute_metrics,
            force_softmax=args.force_softmax,
            erosion_dilation_iterations=args.morph_iterations,
            plot_QC_snaps=args.plot_QC,
            verbose=not args.quiet
            )
        
        logger.info("-" * 50)
        logger.info("✓ Prediction completed successfully!")
        logger.info(f"   Output saved: {args.output}")

        if args.compute_metrics and result:
            logger.info("🔍 Metrics Results:")
            for image_name, metrics in result.items():
                # logger.info(f"   {image_name}:")
                for metric_name, value in metrics.items():
                    logger.info(f"     {metric_name}: {value:.4f}")
        
    except Exception as e:
        logger.error(f"✗ Prediction failed: {e}")
        if not args.quiet:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main() 