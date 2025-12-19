import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, TYPE_CHECKING
from copy import deepcopy


"""Handles loading and saving configuration files in multiple formats."""
def load_yaml_config(config_path: Union[str, Path]) -> Dict[str, Any]:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to YAML configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If YAML is invalid
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        if config is None:
            return {}
        return config
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file {config_file}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load config file {config_file}: {e}")

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
    # Load from YAML defaults file (preferred), fallback to JSON for backward compatibility
    defaults_path_yaml = Path(__file__).parent / "defaults.yaml"
    defaults_path_json = Path(__file__).parent / "defaults.json"
    
    if defaults_path_yaml.exists():
        return load_yaml_config(defaults_path_yaml)
    elif defaults_path_json.exists():
        return load_json_config(defaults_path_json)
    else:
        raise FileNotFoundError(f"Default configuration file not found. Expected defaults.yaml or defaults.json in {Path(__file__).parent}")
    

def load_config(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load configuration from file or return defaults.
    
    Args:
        config_path: Path to configuration file (YAML, JSON, or Python)
        
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
        suffix = config_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            user_config = load_yaml_config(config_file)
        elif suffix == '.json':
            user_config = load_json_config(config_file)
        elif suffix == '.py':
            # Legacy Python config support
            user_config = _load_python_config(config_file)
        else:
            raise ValueError(f"Unsupported config file format: {suffix}. Supported: .yaml, .yml, .json, .py")
        
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
    """Save configuration to file (YAML or JSON based on extension).
    
    Args:
        config: Configuration dictionary
        output_path: Path to save configuration (determines format by extension)
    """
    output_file = Path(output_path)
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Determine format from extension
    suffix = output_file.suffix.lower()
    
    try:
        if suffix in ['.yaml', '.yml']:
            # Save as YAML
            with open(output_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2, allow_unicode=True)
        elif suffix == '.json':
            # Save as JSON
            with open(output_file, 'w') as f:
                json.dump(config, f, indent=2, sort_keys=True)
        else:
            # Default to YAML if no extension or unknown extension
            if suffix:
                raise ValueError(f"Unsupported output format: {suffix}. Use .yaml, .yml, or .json")
            # No extension, default to YAML
            output_file = output_file.with_suffix('.yaml')
            with open(output_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, indent=2, allow_unicode=True)
    except Exception as e:
        raise ValueError(f"Failed to save config to {output_file}: {e}")


def get_output_space(config: Union[Dict[str, Any], Any]) -> str:
    """
    Get output_space from config with fallback logic.
    
    Works with both Config objects (with .get() method) and plain dictionaries.
    
    Args:
        config: Configuration object (Config instance or dictionary)
        
    Returns:
        Output space string, or empty string if not found
    """
    # Try dot notation first (works for Config objects and dicts with dot notation support)
    output_space = config.get("template.output_space", "")
    if not output_space:
        # Fallback: try accessing via nested dict (for dict configs)
        template_dict = config.get("template", {})
        if isinstance(template_dict, dict):
            output_space = template_dict.get("output_space", "")
    return output_space or ""