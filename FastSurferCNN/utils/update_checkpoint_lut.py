#!/usr/bin/env python3
"""
Update Checkpoint Atlas Metadata with Latest LUT

This script updates the atlas_metadata in model checkpoints to reflect changes
in the LUT/roiinfo files. This is necessary when the label mapping has been
modified after training.

Usage:
    # Update a single checkpoint
    python update_checkpoint_lut.py --checkpoint /path/to/model.pkl --atlas ARM2
    
    # Update all checkpoints in a directory
    python update_checkpoint_lut.py --checkpoint-dir /path/to/models --atlas ARM2
    
    # Dry run (show what would be updated without making changes)
    python update_checkpoint_lut.py --checkpoint-dir /path/to/models --atlas ARM2 --dry-run

Author: FastSurfer Team
Date: 2024
"""

import argparse
import sys
from pathlib import Path
import torch
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from atlas.atlas_manager import AtlasManager


def update_checkpoint_metadata(
    checkpoint_path: Path,
    atlas_name: str,
    dry_run: bool = False,
    verbose: bool = True
) -> bool:
    """
    Update the atlas metadata in a single checkpoint file.
    
    Parameters
    ----------
    checkpoint_path : Path
        Path to the checkpoint file to update.
    atlas_name : str
        Name of the atlas (e.g., 'ARM2', 'ARM3').
    dry_run : bool
        If True, show what would be updated without making changes.
    verbose : bool
        If True, print detailed information.
    
    Returns
    -------
    bool
        True if successful, False otherwise.
    """
    if not checkpoint_path.exists():
        if verbose:
            print(f"❌ Checkpoint not found: {checkpoint_path}")
        return False
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"Processing: {checkpoint_path.name}")
        print(f"{'='*70}")
    
    try:
        # Load checkpoint
        if verbose:
            print("Loading checkpoint...")
        from FastSurferCNN.utils.checkpoint import read_checkpoint_file
        checkpoint = read_checkpoint_file(checkpoint_path, map_location='cpu')
        
        # Check if atlas_metadata exists
        if 'atlas_metadata' not in checkpoint:
            if verbose:
                print("⚠️  No atlas_metadata found in checkpoint")
                print("    This checkpoint may be too old to update automatically")
            return False
        
        # Get current metadata
        old_metadata = checkpoint['atlas_metadata']
        old_mapping = old_metadata.get('dense_to_sparse_mapping', [])
        old_num_classes = old_metadata.get('num_classes', len(old_mapping))
        
        if verbose:
            print(f"\nCurrent metadata:")
            print(f"  Atlas: {old_metadata.get('atlas_name', 'Unknown')}")
            print(f"  Plane: {old_metadata.get('plane', 'Unknown')}")
            print(f"  Num classes: {old_num_classes}")
            print(f"  Mapping length: {len(old_mapping)}")
        
        # Get new mapping from AtlasManager
        if verbose:
            print(f"\nLoading new mapping from atlas '{atlas_name}'...")
        atlas_manager = AtlasManager(atlas_name)
        new_dense_to_sparse = atlas_manager.get_dense_to_sparse_mapping()
        new_mapping = new_dense_to_sparse.tolist()
        
        if verbose:
            print(f"\nNew metadata:")
            print(f"  Atlas: {atlas_name.upper()}")
            print(f"  Num classes: {len(new_mapping)}")
            print(f"  Mapping length: {len(new_mapping)}")
        
        # Check if update is needed
        if old_mapping == new_mapping:
            if verbose:
                print("\n✓ Checkpoint already has the latest mapping, no update needed")
            return True
        
        # Show differences
        if verbose:
            print(f"\n📝 Changes detected:")
            if len(old_mapping) != len(new_mapping):
                print(f"  - Number of classes: {len(old_mapping)} → {len(new_mapping)}")
            
            # Show first few label differences
            diff_count = 0
            for i, (old, new) in enumerate(zip(old_mapping, new_mapping)):
                if old != new and diff_count < 5:
                    print(f"  - Index {i}: {old} → {new}")
                    diff_count += 1
            
            if diff_count >= 5:
                print(f"  ... and more differences")
        
        # Update metadata
        if not dry_run:
            checkpoint['atlas_metadata']['atlas_name'] = atlas_name.upper()
            checkpoint['atlas_metadata']['dense_to_sparse_mapping'] = new_mapping
            checkpoint['atlas_metadata']['num_classes'] = len(new_mapping)
            
            # Create backup
            backup_path = checkpoint_path.with_suffix('.pkl.backup')
            if not backup_path.exists():
                if verbose:
                    print(f"\n💾 Creating backup: {backup_path.name}")
                torch.save(
                    read_checkpoint_file(checkpoint_path, map_location='cpu'),
                    backup_path
                )
            
            # Save updated checkpoint
            if verbose:
                print(f"💾 Saving updated checkpoint...")
            torch.save(checkpoint, checkpoint_path)
            
            # Verify
            if verbose:
                print("🔍 Verifying update...")
            verify = read_checkpoint_file(checkpoint_path, map_location='cpu')
            verify_mapping = verify['atlas_metadata']['dense_to_sparse_mapping']
            
            if verify_mapping != new_mapping:
                if verbose:
                    print("❌ Verification failed! Restoring backup...")
                torch.save(
                    read_checkpoint_file(backup_path, map_location='cpu'),
                    checkpoint_path
                )
                return False
            
            if verbose:
                print("✅ Update successful and verified!")
        else:
            if verbose:
                print("\n🔍 DRY RUN - No changes made")
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"❌ Error updating checkpoint: {e}")
            import traceback
            traceback.print_exc()
        return False


def update_directory(
    checkpoint_dir: Path,
    atlas_name: str,
    pattern: str = "*.pkl",
    dry_run: bool = False,
    verbose: bool = True
) -> tuple[int, int]:
    """
    Update all checkpoint files in a directory.
    
    Parameters
    ----------
    checkpoint_dir : Path
        Directory containing checkpoint files.
    atlas_name : str
        Name of the atlas (e.g., 'ARM2', 'ARM3').
    pattern : str
        Glob pattern for checkpoint files (default: '*.pkl').
    dry_run : bool
        If True, show what would be updated without making changes.
    verbose : bool
        If True, print detailed information.
    
    Returns
    -------
    tuple[int, int]
        (number of successful updates, total number of files processed)
    """
    if not checkpoint_dir.exists():
        print(f"❌ Directory not found: {checkpoint_dir}")
        return 0, 0
    
    checkpoint_files = list(checkpoint_dir.glob(pattern))
    
    # Exclude backup files
    checkpoint_files = [f for f in checkpoint_files if not f.name.endswith('.backup')]
    
    if not checkpoint_files:
        print(f"⚠️  No checkpoint files found in {checkpoint_dir}")
        return 0, 0
    
    print(f"\n{'='*70}")
    print(f"Updating Checkpoints in Directory")
    print(f"{'='*70}")
    print(f"Directory: {checkpoint_dir}")
    print(f"Atlas: {atlas_name}")
    print(f"Found {len(checkpoint_files)} checkpoint file(s)")
    if dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    print()
    
    success_count = 0
    for ckpt_file in checkpoint_files:
        result = update_checkpoint_metadata(
            ckpt_file,
            atlas_name,
            dry_run=dry_run,
            verbose=verbose
        )
        if result:
            success_count += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"Summary")
    print(f"{'='*70}")
    print(f"Total files processed: {len(checkpoint_files)}")
    print(f"Successful updates: {success_count}")
    print(f"Failed/Skipped: {len(checkpoint_files) - success_count}")
    
    if not dry_run and success_count > 0:
        print(f"\n💡 Tip: Backup files (.pkl.backup) have been created")
        print(f"    You can restore them if needed by renaming back to .pkl")
    
    return success_count, len(checkpoint_files)


def main():
    parser = argparse.ArgumentParser(
        description="Update checkpoint atlas metadata with latest LUT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update a single checkpoint
  python update_checkpoint_lut.py --checkpoint model.pkl --atlas ARM2
  
  # Update all checkpoints in a directory
  python update_checkpoint_lut.py --checkpoint-dir ./models --atlas ARM2
  
  # Dry run (preview changes without modifying files)
  python update_checkpoint_lut.py --checkpoint-dir ./models --atlas ARM2 --dry-run
  
  # Update specific plane checkpoints
  python update_checkpoint_lut.py --checkpoint axial.pkl --atlas ARM2
  python update_checkpoint_lut.py --checkpoint coronal.pkl --atlas ARM2
  python update_checkpoint_lut.py --checkpoint sagittal.pkl --atlas ARM2
        """
    )
    
    # Input arguments
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--checkpoint',
        type=Path,
        help='Path to a single checkpoint file to update'
    )
    input_group.add_argument(
        '--checkpoint-dir',
        type=Path,
        help='Path to directory containing checkpoint files'
    )
    
    # Atlas argument
    parser.add_argument(
        '--atlas',
        type=str,
        required=True,
        help='Atlas name (e.g., ARM2, ARM3, DKT)'
    )
    
    # Optional arguments
    parser.add_argument(
        '--pattern',
        type=str,
        default='*.pkl',
        help='Glob pattern for checkpoint files when using --checkpoint-dir (default: *.pkl)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Reduce output verbosity'
    )
    
    args = parser.parse_args()
    
    verbose = not args.quiet
    
    # Process single checkpoint or directory
    if args.checkpoint:
        success = update_checkpoint_metadata(
            args.checkpoint,
            args.atlas,
            dry_run=args.dry_run,
            verbose=verbose
        )
        sys.exit(0 if success else 1)
    else:
        success_count, total_count = update_directory(
            args.checkpoint_dir,
            args.atlas,
            pattern=args.pattern,
            dry_run=args.dry_run,
            verbose=verbose
        )
        sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()

