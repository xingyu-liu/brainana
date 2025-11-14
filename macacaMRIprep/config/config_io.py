import json
from pathlib import Path
from typing import Dict, Any, Optional, Union, TYPE_CHECKING
from copy import deepcopy


"""Handles loading and saving configuration files in multiple formats."""
def load_json_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load configuration from JSON file.
    
    Args:
        config_path: Path to JSON configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If JSON is invalid
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_file}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_file}: {e}")
    
def merge_configs(base_config: Dict[str, Any], update_config: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two configuration dictionaries.
    
    Args:
        base_config: Base configuration dictionary
        update_config: Configuration updates to merge
        
    Returns:
        Merged configuration dictionary
    """
    
    result = deepcopy(base_config)
    
    def _recursive_merge(base: Dict[str, Any], update: Dict[str, Any]) -> None:
        """Recursively merge update into base dictionary."""
        for key, value in update.items():
            if (key in base and 
                isinstance(base[key], dict) and 
                isinstance(value, dict)):
                # Recursively merge nested dictionaries
                _recursive_merge(base[key], value)
            else:
                # Override with new value
                base[key] = deepcopy(value)
    
    _recursive_merge(result, update_config)
    return result 


def _deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_default_config() -> Dict[str, Any]:
    """Get default configuration.
    
    Returns:
        Default configuration dictionary
    """
    # Load from JSON defaults file
    defaults_path = Path(__file__).parent / "defaults.json"
    
    if defaults_path.exists():
        return load_json_config(defaults_path)
    

def load_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load configuration from file or return defaults.
    
    Args:
        config_path: Path to configuration file (JSON or Python)
        
    Returns:
        Configuration dictionary
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Start with default configuration
    config = get_default_config()
    
    if config_path is not None:
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        # Load user configuration based on file extension
        if config_file.suffix.lower() == '.json':
            user_config = load_json_config(config_file)
        elif config_file.suffix.lower() == '.py':
            # Legacy Python config support
            user_config = _load_python_config(config_file)
        else:
            raise ValueError(f"Unsupported config file format: {config_file.suffix}")
        
        # Merge with defaults
        config = merge_configs(config, user_config)
    
    return config


def _load_python_config(config_path: Path) -> Dict[str, Any]:
    """Load configuration from Python file (legacy support).
    
    Args:
        config_path: Path to Python configuration file
        
    Returns:
        Configuration dictionary
    """
    import importlib.util
    
    spec = importlib.util.spec_from_file_location("user_config", config_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load Python config from {config_path}")
    
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Look for common config variable names
    for attr_name in ['CONFIG', 'config', 'DEFAULT_CONFIG']:
        if hasattr(module, attr_name):
            return getattr(module, attr_name)
    
    raise ValueError(f"No configuration dictionary found in {config_path}")


def save_config(config: Dict[str, Any], output_path: Union[str, Path]) -> None:
    """Save configuration to JSON file.
    
    Args:
        config: Configuration dictionary
        output_path: Path to save configuration
    """
    output_file = Path(output_path)
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_file, 'w') as f:
            json.dump(config, f, indent=2, sort_keys=True)
    except Exception as e:
        raise ValueError(f"Failed to save config to {output_file}: {e}")