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
    checkpoint = read_checkpoint_file(args.model_path, map_location="cpu")
    
    # Extract config from checkpoint (this is the config used during training)
    if 'config' not in checkpoint:
        print("ERROR: No config found in checkpoint! Checkpoint must contain training config.")
        sys.exit(1)
    
    config_str = checkpoint['config']
    config_dict = yaml.safe_load(config_str)
    
    # Start with defaults
    cfg = get_cfg_defaults()
    
    # Merge checkpoint config (this preserves the training settings like ORIENTATION)
    cfg.merge_from_other_cfg(yacs.config.CfgNode(config_dict))
    
    # Override validation HDF5 path
    cfg.DATA.PATH_HDF5_VAL = args.val_hdf5
    
    # Create trainer (this will build the model and set device)
    trainer = Trainer(cfg=cfg)
    device = trainer.device
    
    # Load pretrained model (checkpoint already loaded above)
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
        else:
            drop_classifier = True
        
        # Load the checkpoint
        restore_model_state_from_checkpoint(
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
    except Exception as e:
        print(f"ERROR: Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Create validation data loader
    val_loader = loader.get_dataloader(cfg, mode="val")
    
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
    
    # Run validation
    # Ensure model is in eval mode and on correct device
    trainer.model.eval()
    trainer.model.to(device)  # Ensure model is on device
    
    # Reset meter to ensure clean state (trainer.eval() does this, but let's be explicit)
    val_meter.reset()
    
    trainer.eval(val_loader, val_meter, epoch=0)
    
    # Get final dice score and print it
    val_dice = val_meter.get_dice_without_background()
    print(val_dice)


if __name__ == "__main__":
    main()

