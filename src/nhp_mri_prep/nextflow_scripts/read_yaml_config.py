#!/usr/bin/env python3
"""
Utility script for reading values from YAML configuration files.
Supports both single-value and batch reading modes.

Usage (single value):
    python3 read_yaml_config.py <config_file> <key_path> [default_value] [--type=TYPE]

Usage (batch mode):
    python3 read_yaml_config.py <config_file> <key1> <key2> ... [--defaults=val1,val2,...]

Output:
    Single mode: single value
    Batch mode: tab-separated values for each key in order
"""

import yaml
import sys
import os
from pathlib import Path

# Add src/ to path for nhp_mri_prep imports (nextflow_scripts/ -> nhp_mri_prep -> src)
_src_dir = Path(__file__).resolve().parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from nhp_mri_prep.config.config_io import get_nested_config_value, load_yaml_config


def main():
    if len(sys.argv) < 3:
        print("Usage: read_yaml_config.py <config_file> <key_path> [default_value] [--type=TYPE]", file=sys.stderr)
        print("   or: read_yaml_config.py <config_file> <key1> <key2> ... [--defaults=val1,val2,...]", file=sys.stderr)
        sys.exit(1)
    
    config_file = Path(sys.argv[1])
    keys = []
    defaults = []
    value_type = None
    
    # Parse arguments
    for arg in sys.argv[2:]:
        if arg.startswith('--defaults='):
            defaults = arg.split('=', 1)[1].split(',')
        elif arg.startswith('--type='):
            value_type = arg.split('=', 1)[1]
        elif arg.startswith('--'):
            continue
        else:
            keys.append(arg)
    
    # Determine mode: single value (1 key, no --defaults) or batch (multiple keys or --defaults)
    is_batch_mode = len(keys) > 1 or (len(sys.argv) > 3 and '--defaults=' in ' '.join(sys.argv))
    
    if is_batch_mode:
        # Batch mode: multiple keys
        # Ensure defaults match keys length
        while len(defaults) < len(keys):
            defaults.append('')
        
        if not config_file.exists():
            print('\t'.join(defaults), end='')
            sys.exit(0)
        
        try:
            config = load_yaml_config(config_file)
        except Exception as e:
            print('\t'.join(defaults), end='')
            sys.exit(0)
        
        # Read all values
        results = []
        for key, default in zip(keys, defaults):
            value = get_nested_config_value(config, key, default)
            # Convert to string representation
            if isinstance(value, bool):
                results.append('true' if value else 'false')
            elif value is None:
                results.append(default)
            else:
                str_value = str(value)
                # Auto-convert boolean-like strings if default is boolean-like
                if default.lower() in ('true', 'false') and str_value.lower() in ('true', 'false', '1', '0', 'yes', 'no', 'on', 'off'):
                    results.append('true' if str_value.lower() in ('true', '1', 'yes', 'on') else 'false')
                else:
                    results.append(str_value if str_value else default)
        
        print('\t'.join(results), end='')
    else:
        # Single value mode (backward compatible)
        key_path = keys[0]
        default_value = keys[1] if len(keys) > 1 else None
        if value_type is None:
            value_type = 'str'
        
        if not config_file.exists():
            if default_value is not None:
                print(default_value, end='')
            sys.exit(0)
        
        try:
            config = load_yaml_config(config_file)
        except Exception as e:
            if default_value is not None:
                print(default_value, end='')
            sys.exit(0)
        
        value = get_nested_config_value(config, key_path, default_value)
        
        # Convert to appropriate type
        if value_type == 'bool':
            if isinstance(value, bool):
                result = 'true' if value else 'false'
            elif isinstance(value, str):
                result = 'true' if value.lower() in ('true', '1', 'yes', 'on') else 'false'
            else:
                result = 'true' if value else 'false'
        elif value_type == 'str':
            result = str(value) if value is not None else (str(default_value) if default_value is not None else '')
        else:
            result = str(value) if value is not None else (str(default_value) if default_value is not None else '')
        
        print(result, end='')
    
    sys.exit(0)


if __name__ == '__main__':
    main()
