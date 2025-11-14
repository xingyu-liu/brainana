#!/usr/bin/env python3

"""
Config Utilities - Path Resolution for FastSurferCNN
=====================================================

This module provides utilities for resolving paths from YAML configuration files.
It implements a single-source-of-truth approach using BASE_DIR.

Key Features:
- Backward compatible with old absolute path configs
- Forward compatible with new BASE_DIR approach
- Automatic path derivation based on conventions
- Clear error messages

Usage:
------
from config_utils import get_paths_from_config

cfg = yaml.safe_load(open('config.yaml'))
paths = get_paths_from_config(cfg, 'config.yaml')

# Access paths
train_hdf5 = paths['train_hdf5']
log_dir = paths['log_dir']
"""

from pathlib import Path
import yaml


def get_paths_from_config(cfg, config_file=None):
    """
    Get all paths from configuration with smart resolution.
    
    This function supports two formats:
    
    NEW FORMAT (recommended):
        BASE_DIR: "/path/to/project"
        DATA:
          PLANE: "coronal"
        LOG_DIR_SUFFIX: "training_output/run_name"
        
    OLD FORMAT (backward compatible):
        DATA:
          PATH_HDF5_TRAIN: "/absolute/path/to/train.hdf5"
          PATH_HDF5_VAL: "/absolute/path/to/val.hdf5"
        LOG_DIR: "/absolute/path/to/output"
    
    Parameters
    ----------
    cfg : dict
        Configuration dictionary loaded from YAML
    config_file : str or Path, optional
        Path to the config file (used for relative path resolution)
        
    Returns
    -------
    dict
        Dictionary with resolved paths:
        - base_dir: Base directory for all paths
        - data_dir: Directory containing source data (T1w_images, T1w_atlas-{ATLAS})
        - train_hdf5: Path to training HDF5 file
        - val_hdf5: Path to validation HDF5 file
        - log_dir: Path to training output directory
        
    Examples
    --------
    >>> cfg = yaml.safe_load(open('config.yaml'))
    >>> paths = get_paths_from_config(cfg, 'config.yaml')
    >>> print(paths['train_hdf5'])
    /path/to/training_data/ARM2_coronal_train.hdf5
    """
    
    # NEW FORMAT: Use BASE_DIR (single source of truth)
    if 'BASE_DIR' in cfg:
        base_dir = Path(cfg['BASE_DIR'])
        plane = cfg['DATA']['PLANE']
        
        # Derive all paths from BASE_DIR and naming conventions
        data_dir = base_dir / "training_data"
        
        # Determine atlas name from config or environment
        atlas_name = "ARM2"  # Default
        if 'CLASS_OPTIONS' in cfg.get('DATA', {}):
            atlas_name = cfg['DATA']['CLASS_OPTIONS'][0]
        elif 'ATLAS_NAME' in cfg:
            atlas_name = cfg['ATLAS_NAME']
        
        # HDF5 files follow naming convention: {ATLAS}_{plane}_{split}.hdf5
        train_hdf5 = data_dir / f"{atlas_name}_{plane}_train.hdf5"
        val_hdf5 = data_dir / f"{atlas_name}_{plane}_val.hdf5"
        
        # Log directory can be customized with suffix
        log_dir_suffix = cfg.get('LOG_DIR_SUFFIX', f'training_output/{atlas_name}_{plane}')
        log_dir = base_dir / log_dir_suffix
        
        return {
            'base_dir': base_dir,
            'data_dir': data_dir,
            'train_hdf5': train_hdf5,
            'val_hdf5': val_hdf5,
            'log_dir': log_dir,
        }
    
    # OLD FORMAT: Use explicit paths (backward compatibility)
    elif 'PATH_HDF5_TRAIN' in cfg.get('DATA', {}):
        train_hdf5 = Path(cfg['DATA']['PATH_HDF5_TRAIN'])
        val_hdf5 = Path(cfg['DATA']['PATH_HDF5_VAL'])
        
        # Handle both absolute and relative paths
        if not train_hdf5.is_absolute() and config_file:
            config_dir = Path(config_file).parent
            train_hdf5 = config_dir / train_hdf5
            val_hdf5 = config_dir / val_hdf5
        
        # Derive data_dir from train HDF5 path
        data_dir = train_hdf5.parent
        base_dir = data_dir.parent  # Assume structure: base/training_data/file.hdf5
        
        # Get log directory
        log_dir = Path(cfg.get('LOG_DIR', base_dir / 'training_output'))
        if not log_dir.is_absolute() and config_file:
            log_dir = Path(config_file).parent / log_dir
        
        return {
            'base_dir': base_dir,
            'data_dir': data_dir,
            'train_hdf5': train_hdf5,
            'val_hdf5': val_hdf5,
            'log_dir': log_dir,
        }
    
    else:
        raise ValueError(
            "Invalid configuration format. Config must have either:\n"
            "  - BASE_DIR (new format), or\n"
            "  - DATA.PATH_HDF5_TRAIN and DATA.PATH_HDF5_VAL (old format)"
        )


def load_yaml_config(yaml_path):
    """
    Load configuration from YAML file.
    
    Parameters
    ----------
    yaml_path : str or Path
        Path to YAML configuration file
        
    Returns
    -------
    dict
        Configuration dictionary
        
    Examples
    --------
    >>> cfg = load_yaml_config('config/FastSurferVINN_ARM3.yaml')
    >>> print(cfg['DATA']['PLANE'])
    coronal
    """
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def print_paths_summary(paths):
    """
    Print a summary of resolved paths for debugging.
    
    Parameters
    ----------
    paths : dict
        Dictionary of paths from get_paths_from_config
        
    Examples
    --------
    >>> paths = get_paths_from_config(cfg, 'config.yaml')
    >>> print_paths_summary(paths)
    """
    print("\n" + "="*70)
    print("Resolved Paths from Configuration")
    print("="*70)
    print(f"Base directory:     {paths['base_dir']}")
    print(f"Data directory:     {paths['data_dir']}")
    print(f"Training HDF5:      {paths['train_hdf5']}")
    print(f"Validation HDF5:    {paths['val_hdf5']}")
    print(f"Output directory:   {paths['log_dir']}")
    print("="*70 + "\n")


def validate_paths(paths, check_existence=False):
    """
    Validate that paths are properly configured.
    
    Parameters
    ----------
    paths : dict
        Dictionary of paths from get_paths_from_config
    check_existence : bool, optional
        If True, check if data_dir actually exists (default: False)
        
    Returns
    -------
    bool
        True if paths are valid
        
    Raises
    ------
    ValueError
        If paths are invalid or don't exist (when check_existence=True)
    """
    # Check that all required keys exist
    required_keys = ['base_dir', 'data_dir', 'train_hdf5', 'val_hdf5', 'log_dir']
    for key in required_keys:
        if key not in paths:
            raise ValueError(f"Missing required path key: {key}")
    
    # Check path types
    for key, value in paths.items():
        if not isinstance(value, Path):
            raise ValueError(f"Path '{key}' must be a Path object, got {type(value)}")
    
    # Optionally check existence
    if check_existence:
        if not paths['data_dir'].exists():
            raise ValueError(
                f"Data directory does not exist: {paths['data_dir']}\n"
                f"Expected to find: T1w_images/ and T1w_atlas-ARM3/ subdirectories"
            )
    
    return True


if __name__ == "__main__":
    """
    Test the path resolution with sample configs.
    """
    import sys
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        print(f"Testing path resolution with: {config_path}")
        
        cfg = load_yaml_config(config_path)
        paths = get_paths_from_config(cfg, config_path)
        print_paths_summary(paths)
        
        try:
            validate_paths(paths, check_existence=True)
            print("✅ All paths validated successfully!")
        except ValueError as e:
            print(f"⚠️  Warning: {e}")
    else:
        print("Usage: python config_utils.py <config.yaml>")
        print("\nExample:")
        print("  python config_utils.py config/FastSurferVINN_ARM3_coronal.yaml")

