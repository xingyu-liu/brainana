"""
Configuration validation for macacaMRIprep.

This module provides functions to validate configuration parameters,
preprocessing settings, file paths, and logging configuration.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Union, Optional
from .config_io import get_default_config, _deep_merge


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Validated and normalized configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Start with default config
    validated_config = get_default_config().copy()
    
    # Deep merge with provided config
    validated_config = _deep_merge(validated_config, config)
    
    # Validate individual sections with new nested structure
    func_config = validated_config.get("func", {})
    anat_config = validated_config.get("anat", {})
    
    # validate_slice_timing_config(func_config.get("slice_timing", {}))
    validate_motion_correction_config(func_config.get("motion_correction", {}))
    validate_despike_config(func_config.get("despike", {}))
    validate_skullstripping_config(func_config.get("skullstripping", {}))
    validate_skullstripping_config(anat_config.get("skullstripping", {}))
    validate_surface_reconstruction_config(anat_config.get("surface_reconstruction", {}))
    validate_bias_correction_config(func_config.get("bias_correction", {}))
    validate_bias_correction_config(anat_config.get("bias_correction", {}))
    validate_registration_config(validated_config.get("registration", {}))
    validate_quality_control_config(validated_config.get("quality_control", {}))
    validate_pipelines_config(validated_config.get("pipelines", {}))
    validate_templates_config(validated_config.get("templates", {}))
    validate_output_config(validated_config.get("output", {}))
    
    return validated_config


def validate_slice_timing_config(config: Dict[str, Any]) -> None:
    """Validate slice timing configuration.
    
    Args:
        config: Slice timing configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Only validate if slice timing is enabled
    if not config.get('enabled', False):
        return
    
    if "repetition_time" in config:
        tr = config["repetition_time"]
        # Skip validation if repetition_time is None (metadata missing)
        if tr is None:
            return
        if not isinstance(tr, (int, float)) or tr <= 0:
            raise ValueError(f"repetition_time must be a positive number, got {tr}")
    
    if "tzero" in config:
        tzero = config["tzero"]
        # Skip validation if tzero is None (metadata missing)
        if tzero is None:
            return
        if not isinstance(tzero, (int, float)):
            raise ValueError(f"tzero must be a number, got {tzero}")
        # Only check tzero < tr if both are present and valid
        if "repetition_time" in config and config["repetition_time"] is not None:
            if tzero > config["repetition_time"]:
                raise ValueError(f"tzero must be less than repetition time, got {tzero} > {config['repetition_time']}")

def validate_motion_correction_config(config: Dict[str, Any]) -> None:
    """Validate motion correction configuration.
    
    Args:
        config: Motion correction configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "dof" in config:
        dof = config["dof"]
        if not isinstance(dof, int) or dof not in [6, 9, 12]:
            raise ValueError(f"dof must be 6, 9, or 12, got {dof}")
    
    if "cost" in config:
        cost = config["cost"]
        valid_costs = ["mutualinfo", "woods", "corratio", "normcorr", "normmi", "leastsq"]
        if cost not in valid_costs:
            raise ValueError(f"cost must be one of {valid_costs}, got {cost}")
    
    if "ref_vol" in config:
        ref_vol = config["ref_vol"]
        if not (isinstance(ref_vol, int) or ref_vol in ["Tmean", "mid"]):
            raise ValueError(f"ref_vol must be an integer or 'Tmean'/'mid', got {ref_vol}")

def validate_despike_config(config: Dict[str, Any]) -> None:
    """Validate despike configuration.
    
    Args:
        config: Despike configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "c1" in config:
        c1 = config["c1"]
        if not isinstance(c1, (int, float)) or c1 <= 0:
            raise ValueError(f"c1 must be a positive number, got {c1}")
    
    if "c2" in config:
        c2 = config["c2"]
        if not isinstance(c2, (int, float)) or c2 <= 0:
            raise ValueError(f"c2 must be a positive number, got {c2}")
    
    if "c1" in config and "c2" in config:
        if config["c1"] >= config["c2"]:
            raise ValueError("c1 must be less than c2")

def validate_skullstripping_config(config: Dict[str, Any]) -> None:
    """Validate skullstripping configuration.
    
    Args:
        config: Skullstripping configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if config.get("enabled", False):
        method = config.get("method", "fastSurferCNN")
        
        if method not in ["bet", "fastSurferCNN", "macacaMRINN"]:
            raise ValueError(f"Invalid skullstripping method: {method}. Must be 'bet', 'fastSurferCNN', or 'macacaMRINN'")
        
        if method == "bet":
            bet_cfg = config.get("bet", {})
            fractional_intensity = bet_cfg.get("fractional_intensity", 0.3)
            if not isinstance(fractional_intensity, (int, float)) or not (0 < fractional_intensity < 1):
                raise ValueError(f"bet fractional_intensity must be between 0 and 1, got: {fractional_intensity}")
        
        elif method == "fastSurferCNN":
            fscnn_cfg = config.get("fastSurferCNN", {})
            
            # Validate gpu_device
            gpu_device = fscnn_cfg.get("gpu_device", "auto")
            if not (isinstance(gpu_device, int) and gpu_device >= -1) and gpu_device != "auto":
                raise ValueError(f"fastSurferCNN gpu_device must be integer >= -1 (where -1 means CPU) or 'auto' for automatic selection, got: {gpu_device}")
            
            # Validate batch_size
            batch_size = fscnn_cfg.get("batch_size", 1)
            if not isinstance(batch_size, int) or batch_size < 1:
                raise ValueError(f"fastSurferCNN batch_size must be a positive integer, got: {batch_size}")
            
            # Validate threads
            threads = fscnn_cfg.get("threads", 1)
            if not isinstance(threads, int) or threads < 1:
                raise ValueError(f"fastSurferCNN threads must be a positive integer, got: {threads}")
            
            # Validate use_mixed_model
            use_mixed_model = fscnn_cfg.get("use_mixed_model", False)
            if not isinstance(use_mixed_model, bool):
                raise ValueError(f"fastSurferCNN use_mixed_model must be a boolean, got: {use_mixed_model}")
            
            # Validate enable_crop_2round
            enable_crop_2round = fscnn_cfg.get("enable_crop_2round", False)
            if not isinstance(enable_crop_2round, bool):
                raise ValueError(f"fastSurferCNN enable_crop_2round must be a boolean, got: {enable_crop_2round}")
            
            # Validate plane weights (optional, can be None or float)
            for weight_name in ["plane_weight_coronal", "plane_weight_axial", "plane_weight_sagittal"]:
                weight = fscnn_cfg.get(weight_name)
                if weight is not None:
                    if not isinstance(weight, (int, float)) or not (0 <= weight <= 1):
                        raise ValueError(f"fastSurferCNN {weight_name} must be a float between 0 and 1, or None, got: {weight}")
        
        elif method == "macacaMRINN":
            mrin_cfg = config.get("macacaMRINN", {})
            
            # Validate gpu_device (only runtime parameter needed)
            # Other parameters (rescale_dim, num_input_slices, morph_iterations) 
            # are loaded from model checkpoint automatically
            gpu_device = mrin_cfg.get("gpu_device", "auto")
            if not (isinstance(gpu_device, int) and gpu_device >= -1) and gpu_device != "auto":
                raise ValueError(f"macacaMRINN gpu_device must be integer >= -1 (where -1 means CPU) or 'auto' for automatic selection, got: {gpu_device}")

def validate_bias_correction_config(config: Dict[str, Any]) -> None:
    """Validate bias correction configuration.
    
    Args:
        config: Bias correction configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "dimension" in config:
        dim = config["dimension"]
        if not isinstance(dim, int) or dim not in [2, 3, 4]:
            raise ValueError(f"dimension must be 2, 3, or 4, got {dim}")
    
    if "shrink_factor" in config:
        shrink = config["shrink_factor"]
        if not isinstance(shrink, (int, float)) or shrink <= 0:
            raise ValueError(f"shrink_factor must be a positive number, got {shrink}")

def validate_registration_config(config: Dict[str, Any]) -> None:
    """Validate registration configuration.
    
    Args:
        config: Registration configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    valid_interpolations = [
        "Linear", "NearestNeighbor", "MultiLabel", "Gaussian", "BSpline",
        "CosineWindowedSinc", "WelchWindowedSinc", "HammingWindowedSinc",
        "LanczosWindowedSinc", "GenericLabel"
    ]
    
    if "interpolation" in config:
        interp = config["interpolation"]
        if interp not in valid_interpolations:
            raise ValueError(f"interpolation must be one of {valid_interpolations}, got {interp}")
    
    # Validate transform stages
    for stage in ["translation", "rigid", "affine", "syn"]:
        if stage in config:
            validate_transform_stage_config(config[stage], stage)

def validate_transform_stage_config(config: Dict[str, Any], stage_name: str) -> None:
    """Validate individual transform stage configuration.
    
    Args:
        config: Transform stage configuration
        stage_name: Name of the transform stage
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "gradient_step" in config:
        grad_step = config["gradient_step"]
        # Allow both string format (e.g., "[0.1]") and list format
        if isinstance(grad_step, str):
            # Validate it looks like a list string
            if not (grad_step.startswith('[') and grad_step.endswith(']')):
                raise ValueError(f"{stage_name} gradient_step string must be in format '[value]' or '[value1,value2]'")
        elif isinstance(grad_step, list):
            # Original validation for list format
            if not all(isinstance(x, (str, int, float)) for x in grad_step):
                raise ValueError(f"{stage_name} gradient_step list must contain strings or numbers")
        else:
            raise ValueError(f"{stage_name} gradient_step must be a string (e.g., '[0.1]') or list")
    
    if "metric" in config:
        metrics = config["metric"]
        if not isinstance(metrics, list) or not all(isinstance(x, str) for x in metrics):
            raise ValueError(f"{stage_name} metric must be a list of strings")

def validate_quality_control_config(config: Dict[str, Any]) -> None:
    """Validate quality control configuration.
    
    Args:
        config: Quality control configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "snap_views" in config:
        views = config["snap_views"]
        if not isinstance(views, list) or not all(v in ["x", "y", "z"] for v in views):
            raise ValueError("snap_views must be a list containing 'x', 'y', and/or 'z'")
    
    if "snap_slices" in config:
        slices = config["snap_slices"]
        if not isinstance(slices, int) or slices <= 0:
            raise ValueError(f"snap_slices must be a positive integer, got {slices}")
    
    if "report_format" in config:
        fmt = config["report_format"]
        valid_formats = ["html", "pdf", "json"]
        if fmt not in valid_formats:
            raise ValueError(f"report_format must be one of {valid_formats}, got {fmt}")


def validate_pipelines_config(config: Dict[str, Any]) -> None:
    """Validate pipelines configuration.
    
    Args:
        config: Pipelines configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    valid_pipelines = ["func2template", "anat2template", "func2anat"]
    
    for pipeline_name, pipeline_config in config.items():
        if pipeline_name not in valid_pipelines:
            raise ValueError(f"Unknown pipeline: {pipeline_name}. Valid pipelines: {valid_pipelines}")
        
        if not isinstance(pipeline_config, dict):
            raise ValueError(f"Pipeline config for {pipeline_name} must be a dictionary")
        
        if "enabled" in pipeline_config:
            if not isinstance(pipeline_config["enabled"], bool):
                raise ValueError(f"Pipeline {pipeline_name} 'enabled' must be boolean")


def validate_templates_config(config: Dict[str, Any]) -> None:
    """Validate templates configuration.
    
    Args:
        config: Templates configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "default_space" in config:
        space = config["default_space"]
        if not isinstance(space, str):
            raise ValueError("default_space must be a string")
    
    if "resolution" in config:
        res = config["resolution"]
        if not isinstance(res, str):
            raise ValueError("resolution must be a string (e.g., '2mm')")
    
    if "custom_template" in config and config["custom_template"] is not None:
        template_path = Path(config["custom_template"])
        if not template_path.exists():
            raise ValueError(f"Custom template file not found: {template_path}")
    
    if "custom_mask" in config and config["custom_mask"] is not None:
        mask_path = Path(config["custom_mask"])
        if not mask_path.exists():
            raise ValueError(f"Custom mask file not found: {mask_path}")


def validate_surface_reconstruction_config(config: Dict[str, Any]) -> None:
    """Validate surface reconstruction configuration.
    
    Args:
        config: Surface reconstruction configuration dictionary
        
    Raises:
        ValueError: If any surface reconstruction parameters are invalid
    """
    if not isinstance(config, dict):
        raise ValueError("surface_reconstruction config must be a dictionary")
    
    # Validate enabled flag
    if "enabled" in config:
        if not isinstance(config["enabled"], bool):
            raise ValueError("anat.surface_reconstruction.enabled must be boolean")
    
    # Validate threads (optional, can be null for auto-detection)
    if "threads" in config and config["threads"] is not None:
        threads = config["threads"]
        if not isinstance(threads, int):
            raise ValueError("anat.surface_reconstruction.threads must be an integer or null")
        if threads < 1:
            raise ValueError("anat.surface_reconstruction.threads must be >= 1")


def validate_output_config(config: Dict[str, Any]) -> None:
    """Validate output configuration.
    
    Args:
        config: Output configuration
        
    Raises:
        ValueError: If configuration is invalid
    """
    if "derivatives_dir" in config:
        if not isinstance(config["derivatives_dir"], str):
            raise ValueError("derivatives_dir must be a string")
    
    for bool_param in ["compression", "save_intermediate", "cleanup_working_dir"]:
        if bool_param in config:
            if not isinstance(config[bool_param], bool):
                raise ValueError(f"{bool_param} must be boolean")

def validate_preprocessing_config(config: Dict[str, Any]) -> None:
    """Validate preprocessing configuration.
    
    Args:
        config: Preprocessing configuration dictionary
        
    Raises:
        ValueError: If any preprocessing parameters are invalid
    """
    # Validate overall structure
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary")
    
    # Check for required sections based on enabled features
    required_sections = []
    
    # Always require slice timing if not disabled
    if config.get("slice_timing", {}).get("enabled", True):
        required_sections.append("slice_timing")
    
    # Always require motion correction if not disabled
    if config.get("motion_correction", {}).get("enabled", True):
        required_sections.append("motion_correction")
    
    # Check registration if enabled
    if config.get("registration", {}).get("enabled", True):
        required_sections.append("registration")
    
    # Validate log level
    if "log_level" in config:
        log_level = config["log_level"]
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {log_level}")
    
    # Validate verbose setting in general section
    if "general" in config and "verbose" in config["general"]:
        verbose = config["general"]["verbose"]
        if not isinstance(verbose, (int, bool)):
            raise ValueError(f"verbose must be boolean or integer, got {type(verbose)}")
    
    # Also check root level for backward compatibility
    if "verbose" in config:
        verbose = config["verbose"] 
        if not isinstance(verbose, (int, bool)):
            raise ValueError(f"verbose must be boolean or integer, got {type(verbose)}")

def validate_paths(input_file: Union[str, Path], output_dir: Union[str, Path], 
                  template_file: Optional[Union[str, Path]] = None) -> None:
    """Validate input and output paths.
    
    Args:
        input_file: Path to input file
        output_dir: Path to output directory
        template_file: Optional path to template file
        
    Raises:
        FileNotFoundError: If input files don't exist
        ValueError: If paths are invalid
    """
    # Validate input file
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    
    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    
    # Check if it's a valid neuroimaging file
    # Check if file has a valid NIFTI extension
    if not str(input_path).endswith(('.nii', '.nii.gz')):
        raise ValueError(f"Input file must be a NIFTI file: {input_path}")
    
    # Validate output directory
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValueError(f"Cannot create output directory: {e}")
    
    # Validate template file if provided
    if template_file is not None:
        template_path = Path(template_file)
        if not template_path.exists():
            raise FileNotFoundError(f"Template file does not exist: {template_path}")
        
        if not template_path.is_file():
            raise ValueError(f"Template path is not a file: {template_path}")
        
        if not str(template_path).endswith(('.nii', '.nii.gz')):
            raise ValueError(f"Template file must be a NIFTI file: {template_path}")

def validate_logging_config(config: Dict[str, Any]) -> None:
    """Validate logging configuration.
    
    Args:
        config: Logging configuration dictionary
        
    Raises:
        ValueError: If logging configuration is invalid
    """
    if "log_level" in config:
        log_level = config["log_level"]
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            raise ValueError(f"Invalid log level: {log_level}. Must be one of {valid_levels}")
        
        # Verify it's a valid logging level
        try:
            getattr(logging, log_level)
        except AttributeError:
            raise ValueError(f"Invalid logging level: {log_level}")
    
    # Validate log format if specified
    if "log_format" in config:
        log_format = config["log_format"]
        if not isinstance(log_format, str):
            raise ValueError("log_format must be a string")
        
        # Test the format string
        try:
            log_format % {
                "name": "test",
                "levelname": "INFO", 
                "asctime": "2024-01-01 12:00:00",
                "message": "test message"
            }
        except (TypeError, KeyError) as e:
            raise ValueError(f"Invalid log format string: {e}")
    
    # Validate log file path if specified
    if "log_file" in config:
        log_file = config["log_file"]
        if log_file is not None:
            log_path = Path(log_file)
            try:
                # Test if we can create the parent directory
                log_path.parent.mkdir(parents=True, exist_ok=True)
                # Test if we can write to the file
                with open(log_path, 'a') as f:
                    pass
            except Exception as e:
                raise ValueError(f"Cannot write to log file {log_path}: {e}")
