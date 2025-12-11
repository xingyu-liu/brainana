#!/usr/bin/env python3
"""
Update checkpoint files to change IMG_SIZE from 'auto' to 'cube'.

This script updates all checkpoint files in the pretrained_model directory
to replace 'auto' with 'cube' in DATA.PREPROCESSING.IMG_SIZE.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

import torch
import yaml
from FastSurferCNN.utils.checkpoint import read_checkpoint_file

def update_checkpoint_img_size(checkpoint_path: Path) -> bool:
    """
    Update IMG_SIZE from 'auto' to 'cube' in a checkpoint file.
    
    Parameters
    ----------
    checkpoint_path : Path
        Path to checkpoint file
        
    Returns
    -------
    bool
        True if update was made, False if no update needed
    """
    print(f"Processing: {checkpoint_path.name}")
    
    # Load checkpoint
    checkpoint = read_checkpoint_file(checkpoint_path, map_location="cpu")
    
    if 'config' not in checkpoint:
        print(f"  WARNING: No config found in {checkpoint_path.name}")
        return False
    
    # Parse config YAML string
    config_str = checkpoint['config']
    config_dict = yaml.safe_load(config_str)
    
    # update orientation to RAS
    updated = False
    if 'DATA' in config_dict and 'PREPROCESSING' in config_dict['DATA']:
        preproc = config_dict['DATA']['PREPROCESSING']
        if 'ORIENTATION' in preproc:
            preproc['ORIENTATION'] = 'RAS'
            updated = True
            print(f"  Updated ORIENTATION → 'RAS'")

        else:
            print(f"  WARNING: ORIENTATION not found in PREPROCESSING")
    else:
        print(f"  WARNING: DATA.PREPROCESSING not found in config")
    
    if updated:
        # Convert back to YAML string
        updated_config_str = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
        checkpoint['config'] = updated_config_str
        
        # Save checkpoint
        # Create backup first
        backup_path = checkpoint_path.with_suffix('.pkl.backup')
        if not backup_path.exists():
            print(f"  Creating backup: {backup_path.name}")
            torch.save(read_checkpoint_file(checkpoint_path, map_location="cpu"), backup_path)
        
        # Save updated checkpoint
        print(f"  Saving updated checkpoint...")
        torch.save(checkpoint, checkpoint_path)
        print(f"  ✓ Successfully updated {checkpoint_path.name}")
    
    return updated


def main():
    """Update all checkpoint files."""
    # Get pretrained_model directory
    script_dir = Path(__file__).resolve().parent
    pretrained_dir = script_dir.parent / "pretrained_model"
    
    if not pretrained_dir.exists():
        print(f"Error: pretrained_model directory not found at {pretrained_dir}")
        sys.exit(1)
    
    # List of checkpoint files to update
    checkpoint_files = [
        "EPI_seg-brainmask_axial.pkl",
        "EPI_seg-brainmask_coronal.pkl",
        "EPI_seg-brainmask_mixed.pkl",
        "EPI_seg-brainmask_sagittal.pkl",
        "T1w_seg-ARM2_axial.pkl",
        "T1w_seg-ARM2_coronal.pkl",
        "T1w_seg-ARM2_sagittal.pkl",
    ]
    
    print("=" * 80)
    print("Updating checkpoint files: IMG_SIZE 'auto' → 'cube'")
    print("=" * 80)
    print()
    
    updated_count = 0
    for ckpt_name in checkpoint_files:
        ckpt_path = pretrained_dir / ckpt_name
        if not ckpt_path.exists():
            print(f"WARNING: {ckpt_name} not found, skipping...")
            continue
        
        if update_checkpoint_img_size(ckpt_path):
            updated_count += 1
        print()
    
    print("=" * 80)
    print(f"Summary: Updated {updated_count} checkpoint file(s)")
    print("=" * 80)


if __name__ == "__main__":
    main()

