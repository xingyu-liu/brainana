import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from copy import deepcopy
from .config_io import save_config, merge_configs, load_config, get_default_config
from .config_validation import validate_config

class Config:
    """Configuration class with validation and easy access methods."""
    
    def __init__(self, config_data: Optional[Union[str, Path, Dict[str, Any]]] = None):
        """Initialize configuration.
        
        Args:
            config_data: Configuration source (file path or dictionary)
        """
        """
        TODO : global logger
        """
        if isinstance(config_data, (str, Path)):
            self._data = load_config(config_data)
        elif isinstance(config_data, dict):
            # Start with defaults and merge user config
            defaults = get_default_config()
            self._data = merge_configs(defaults, config_data)
        elif config_data is None:
            self._data = get_default_config()
        else:
            raise ValueError(f"Invalid config_data type: {type(config_data)}")
        
        # Validate configuration
        self._data = validate_config(self._data)
        
        # Normalize verbose to integer (0, 1, or 2) for consistency
        if "general" in self._data and "verbose" in self._data["general"]:
            from ..utils.logger import normalize_verbose
            self._data["general"]["verbose"] = normalize_verbose(self._data["general"]["verbose"])
        
        self._logger = logging.getLogger(__name__)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Args:
            key: Configuration key (supports dot notation like 'reg.trans.enabled')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._data
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split('.')
        data = self._data
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        
        # Set the value
        data[keys[-1]] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values.
        
        Args:
            updates: Dictionary of updates
        """
        self._data = merge_configs(self._data, updates)
        self._data = validate_config(self._data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary.
        
        Returns:
            Configuration dictionary
        """
        return deepcopy(self._data)
    
    def save(self, output_path: Union[str, Path]) -> None:
        """Save configuration to file.
        
        Args:
            output_path: Path to save configuration
        """
        save_config(self._data, output_path)
        self._logger.info(f"Config: configuration saved - {output_path}")
    
    def validate(self) -> None:
        """Validate current configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        self._data = validate_config(self._data)
    
    def get_log_level(self) -> str:
        """Get the logging level, derived from verbose if log_level not explicitly set.
        
        If log_level is explicitly set in config, use it (for backward compatibility).
        Otherwise, derive log_level from verbose:
        - verbose=0 -> "ERROR" (quiet)
        - verbose=1 -> "INFO" (normal)
        - verbose=2 -> "DEBUG" (verbose)
        
        Returns:
            Logging level string
        """
        # Check if log_level is explicitly set (backward compatibility)
        if 'general' in self._data and 'log_level' in self._data['general']:
            return self._data['general']['log_level']
        
        # Derive from verbose
        from ..utils.logger import normalize_verbose, verbose_to_log_level
        verbose = normalize_verbose(self.get('general.verbose', 1))
        return verbose_to_log_level(verbose)
    
    def __repr__(self) -> str:
        return f"Config({len(self._data)} sections)"
    
    def __str__(self) -> str:
        return json.dumps(self._data, indent=2)

# Global configuration instance
_global_config: Optional['Config'] = None


def get_config() -> Config:
    """Get global configuration instance.
    
    Returns:
        Global configuration instance
    """
    global _global_config
    
    if _global_config is None:
        _global_config = Config()
    
    return _global_config