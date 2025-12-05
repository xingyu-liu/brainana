"""
Configuration validation for macacaMRIprep.

This module provides functions to validate configuration parameters
and preprocessing settings.
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
    
    validate_slice_timing_config(func_config.get("slice_timing_correction", {}))
    validate_motion_correction_config(func_config.get("motion_correction", {}))
    validate_despike_config(func_config.get("despike", {}))
    validate_skullstripping_config(func_config.get("skullstripping", {}))
    validate_skullstripping_config(anat_config.get("skullstripping", {}))
    validate_surface_reconstruction_config(anat_config.get("surface_reconstruction", {}))
    validate_bias_correction_config(func_config.get("bias_correction", {}))
    validate_bias_correction_config(anat_config.get("bias_correction", {}))
    validate_registration_config(validated_config.get("registration", {}))
    validate_quality_control_config(validated_config.get("quality_control", {}))
    
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
    if not config.get("enabled", False):
        return
    
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
        
        # Validate boolean options
        for bool_param in ["use_mixed_model", "enable_crop_2round", "fix_V1_WM"]:
            if bool_param in fscnn_cfg:
                value = fscnn_cfg.get(bool_param)
                if not isinstance(value, bool):
                    raise ValueError(f"fastSurferCNN {bool_param} must be a boolean, got: {value}")
        
        # Validate plane weights (optional, can be None or float)
        for weight_name in ["plane_weight_coronal", "plane_weight_axial", "plane_weight_sagittal"]:
            weight = fscnn_cfg.get(weight_name)
            if weight is not None:
                if not isinstance(weight, (int, float)) or not (0 <= weight <= 1):
                    raise ValueError(f"fastSurferCNN {weight_name} must be a float between 0 and 1, or None, got: {weight}")
    
    elif method == "macacaMRINN":
        mrin_cfg = config.get("macacaMRINN", {})
        
        # Validate gpu_device (only runtime parameter needed)
        # Other parameters are loaded from model checkpoint automatically
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
    
    # Validate transform stages (if present)
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
            if not (grad_step.startswith('[') and grad_step.endswith(']')):
                raise ValueError(f"{stage_name} gradient_step string must be in format '[value]' or '[value1,value2]'")
        elif isinstance(grad_step, list):
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
    # Only validate if quality_control section exists (it's optional and may be removed)
    if not config:
        return
    
    if "snap_views" in config:
        views = config["snap_views"]
        if not isinstance(views, list) or not all(v in ["x", "y", "z"] for v in views):
            raise ValueError("snap_views must be a list containing 'x', 'y', and/or 'z'")
    
    if "snap_slices" in config:
        slices = config["snap_slices"]
        if not isinstance(slices, int) or slices <= 0:
            raise ValueError(f"snap_slices must be a positive integer, got {slices}")


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
