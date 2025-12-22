#!/usr/bin/env python3
"""
Script to print the configuration stored in a checkpoint file.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path so we can import FastSurferCNN
_file_dir = Path(__file__).resolve().parent
if str(_file_dir.parent.parent) not in sys.path:
    sys.path.insert(0, str(_file_dir.parent.parent))

import torch
import yaml
from FastSurferCNN.utils.checkpoint import read_checkpoint_file


def main():
    parser = argparse.ArgumentParser(description="Print config from checkpoint file")
    parser.add_argument(
        "checkpoint",
        help="Path to checkpoint file (.pkl)",
        type=str,
    )
    parser.add_argument(
        "--format",
        choices=["yaml", "dict", "pretty"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    
    args = parser.parse_args()
    
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"ERROR: Checkpoint file not found: {checkpoint_path}")
        sys.exit(1)
    
    print(f"Loading checkpoint from: {checkpoint_path}")
    print("=" * 80)
    
    try:
        checkpoint = read_checkpoint_file(checkpoint_path, map_location="cpu")
        
        # Print checkpoint metadata
        print("\nCheckpoint Metadata:")
        print("-" * 80)
        for key in checkpoint.keys():
            if key != "config" and key != "model_state":
                value = checkpoint[key]
                if isinstance(value, (int, float, str, bool, type(None))):
                    print(f"  {key}: {value}")
                elif isinstance(value, dict):
                    print(f"  {key}: {len(value)} items")
                else:
                    print(f"  {key}: {type(value).__name__}")
        
        # Print config
        if "config" not in checkpoint:
            print("\n⚠️  WARNING: No config found in checkpoint!")
            sys.exit(0)
        
        config_str = checkpoint["config"]
        
        if args.format == "yaml":
            print("\n" + "=" * 80)
            print("Config (YAML format):")
            print("=" * 80)
            print(config_str)
        elif args.format == "dict":
            config_dict = yaml.safe_load(config_str)
            print("\n" + "=" * 80)
            print("Config (Python dict format):")
            print("=" * 80)
            import json
            print(json.dumps(config_dict, indent=2, default=str))
        else:  # pretty format
            config_dict = yaml.safe_load(config_str)
            print("\n" + "=" * 80)
            print("Config (Pretty format):")
            print("=" * 80)
            _print_config_dict(config_dict, indent=0)
        
    except Exception as e:
        print(f"ERROR: Failed to load checkpoint: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _print_config_dict(d, indent=0):
    """Recursively print config dictionary in a readable format."""
    prefix = "  " * indent
    for key, value in d.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            _print_config_dict(value, indent + 1)
        elif isinstance(value, list):
            print(f"{prefix}{key}:")
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    print(f"{prefix}  [{i}]:")
                    _print_config_dict(item, indent + 2)
                else:
                    print(f"{prefix}  - {item}")
        else:
            print(f"{prefix}{key}: {value}")


if __name__ == "__main__":
    main()

