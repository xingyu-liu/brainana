#!/usr/bin/env python3
"""
Validation script to run validation on a dataset using a pretrained model.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

import yaml
import yacs.config
from FastSurferCNN.training.trainer import Trainer
from FastSurferCNN.data_loader import loader
from FastSurferCNN.utils.checkpoint import read_checkpoint_file, restore_model_state_from_checkpoint
from FastSurferCNN.utils.meters import Meter
from FastSurferCNN.config.defaults import get_cfg_defaults


def main():
    parser = argparse.ArgumentParser(description="Run validation on a dataset using a pretrained model. Config is extracted from checkpoint.")
    parser.add_argument(
        "--val-hdf5",
        dest="val_hdf5",
        help="Path to validation HDF5 file",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--model",
        dest="model_path",
        help="Path to pretrained model (.pkl file)",
        required=True,
        type=str,
    )
    
    args = parser.parse_args()
    
    # Check if files exist
    if not Path(args.val_hdf5).exists():
        print(f"ERROR: Validation HDF5 file not found: {args.val_hdf5}")
        sys.exit(1)
    
    if not Path(args.model_path).exists():
        print(f"ERROR: Model file not found: {args.model_path}")
        sys.exit(1)
    
    # Load checkpoint first to extract config
    print(f"Loading checkpoint to extract config from: {args.model_path}")
    checkpoint = read_checkpoint_file(args.model_path, map_location="cpu")
    
    # Extract config from checkpoint (this is the config used during training)
    if 'config' not in checkpoint:
        print("ERROR: No config found in checkpoint! Checkpoint must contain training config.")
        sys.exit(1)
    
    print("✓ Config found in checkpoint, using checkpoint config")
    config_str = checkpoint['config']
    config_dict = yaml.safe_load(config_str)
    
    # Start with defaults
    cfg = get_cfg_defaults()
    
    # Merge checkpoint config (this preserves the training settings like ORIENTATION)
    cfg.merge_from_other_cfg(yacs.config.CfgNode(config_dict))
    
    print(f"  Orientation from checkpoint: {cfg.DATA.PREPROCESSING.ORIENTATION}")
    
    # DEBUG: Print key config values to diagnose Dice mismatch
    print("\n" + "-"*40)
    print("DEBUG: Config values after merging checkpoint:")
    print(f"  cfg.MODEL.NUM_CLASSES = {cfg.MODEL.NUM_CLASSES}")
    print(f"  cfg.MODEL.NUM_FILTERS = {cfg.MODEL.NUM_FILTERS}")
    print(f"  cfg.DATA.PLANE = {cfg.DATA.PLANE}")
    print(f"  cfg.DATA.SIZES = {cfg.DATA.SIZES}")
    print(f"  cfg.DATA.PADDED_SIZE = {cfg.DATA.PADDED_SIZE}")
    print(f"  cfg.DATA.CLASS_OPTIONS = {cfg.DATA.CLASS_OPTIONS}")
    print("-"*40 + "\n")
    
    # Override validation HDF5 path
    cfg.DATA.PATH_HDF5_VAL = args.val_hdf5
    print(f"Validation HDF5: {cfg.DATA.PATH_HDF5_VAL}")
    
    # Create trainer (this will build the model and set device)
    print("Initializing trainer...")
    trainer = Trainer(cfg=cfg)
    device = trainer.device
    print(f"Using device: {device}")
    
    # DEBUG: Print trainer state
    print("\n" + "-"*40)
    print("DEBUG: Trainer state after initialization:")
    print(f"  trainer.num_classes = {trainer.num_classes}")
    print(f"  len(trainer.class_names) = {len(trainer.class_names)}")
    print(f"  trainer.class_names[:5] = {trainer.class_names[:5]}")  # First 5 class names
    print("-"*40 + "\n")
    
    # Load pretrained model (checkpoint already loaded above)
    print(f"Loading pretrained model weights from: {args.model_path}")
    try:
        # Find classifier weight to determine number of classes in checkpoint
        classifier_key = None
        for key in checkpoint["model_state"].keys():
            if "classifier" in key and "weight" in key and "conv" in key:
                classifier_key = key
                break
        
        if classifier_key:
            pretrained_num_classes = checkpoint["model_state"][classifier_key].shape[0]
            drop_classifier = (cfg.MODEL.NUM_CLASSES != pretrained_num_classes)
            if drop_classifier:
                print(f"Warning: Model has {pretrained_num_classes} classes, config has {cfg.MODEL.NUM_CLASSES} classes. Dropping classifier.")
        else:
            drop_classifier = True
        
        # Load the checkpoint
        checkpoint_epoch, best_metric = restore_model_state_from_checkpoint(
            args.model_path,
            trainer.model,
            optimizer=None,
            scheduler=None,
            fine_tune=False,
            drop_classifier=drop_classifier,
        )
        # Move model to the correct device (checkpoint was loaded to CPU)
        # IMPORTANT: Model must be on device BEFORE creating meter, so DiceScore tensors are on correct device
        trainer.model.to(device)
        print(f"Model loaded successfully (epoch: {checkpoint_epoch}, best metric: {best_metric})")
    except Exception as e:
        print(f"ERROR: Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Create validation data loader
    print("Creating validation data loader...")
    val_loader = loader.get_dataloader(cfg, mode="val")
    print(f"Validation batches: {len(val_loader)}")
    
    # Create validation meter AFTER model is on device
    # This ensures DiceScore initializes tensors on the correct device
    val_meter = Meter(
        cfg=cfg,
        mode="val",
        global_step=0,
        total_iter=len(val_loader),
        total_epoch=1,
        class_names=trainer.class_names,
        device=device,  # Device is already set correctly
        writer=None,  # No tensorboard writer for validation only
    )
    
    # DEBUG: Print meter and DiceScore state
    print("\n" + "-"*40)
    print("DEBUG: Meter and DiceScore state:")
    print(f"  val_meter.dice_score.n_classes = {val_meter.dice_score.n_classes}")
    print(f"  val_meter.dice_score._device = {val_meter.dice_score._device}")
    print(f"  val_meter.dice_score.union.shape = {val_meter.dice_score.union.shape}")
    print(f"  val_meter.dice_score.union.device = {val_meter.dice_score.union.device}")
    print("-"*40 + "\n")
    
    # Run validation
    print("\n" + "="*80)
    print("Running validation...")
    print("="*80 + "\n")
    
    # Ensure model is in eval mode and on correct device
    trainer.model.eval()
    trainer.model.to(device)  # Ensure model is on device
    
    # Reset meter to ensure clean state (trainer.eval() does this, but let's be explicit)
    val_meter.reset()
    
    trainer.eval(val_loader, val_meter, epoch=0)
    
    # DEBUG: Print DiceScore state after validation
    print("\n" + "-"*40)
    print("DEBUG: DiceScore state after validation:")
    print(f"  union.device = {val_meter.dice_score.union.device}")
    print(f"  intersection.device = {val_meter.dice_score.intersection.device}")
    print(f"  union diagonal sum = {val_meter.dice_score.union.diagonal().sum().item():.2f}")
    print(f"  intersection diagonal sum = {val_meter.dice_score.intersection.diagonal().sum().item():.2f}")
    # Check if any class has significant predictions
    diag_union = val_meter.dice_score.union.diagonal()
    nonzero_classes = (diag_union > 0).sum().item()
    print(f"  Classes with non-zero union: {nonzero_classes}/{val_meter.dice_score.n_classes}")
    print("-"*40 + "\n")
    
    # Get final dice score
    val_dice = val_meter.get_dice_without_background()
    
    print("\n" + "="*80)
    print(f"Validation Dice Score (excluding background): {val_dice:.6f}")
    print("="*80 + "\n")
    
    # Also print per-class dice if available
    dice_score, dice_matrix = val_meter.dice_score.compute(per_class=True)
    if len(dice_score) > 1:
        print("Per-class Dice Scores (excluding background):")
        for i in range(1, len(dice_score)):  # Skip background (class 0)
            class_name = trainer.class_names[i] if i < len(trainer.class_names) else f"Class {i}"
            dice_val = dice_score[i].item() if hasattr(dice_score[i], 'item') else dice_score[i]
            print(f"  {class_name}: {dice_val:.6f}")
        print()


if __name__ == "__main__":
    main()

