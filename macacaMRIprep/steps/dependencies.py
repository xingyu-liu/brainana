"""
Dependency graph for processing steps.

This module defines the dependency relationships between processing steps,
enabling Nextflow to automatically manage execution order.
"""

# Step dependency graph
# Format: {step_name: [list of prerequisite steps]}
STEP_DEPENDENCIES = {
    # Multi-run T1w synthesis (runs before anatomical processing)
    "anat_synthesis": [],
    
    # Anatomical steps
    "anat_reorient": ["anat_synthesis"],  # Conditional dependency: only for files requiring synthesis
    "anat_conform": ["anat_reorient"],
    "anat_bias_correction": ["anat_conform"],
    "anat_skullstripping": ["anat_bias_correction"],
    "anat_registration": ["anat_skullstripping"],
    "anat_surface_reconstruction": ["anat_skullstripping"],
    
    # Functional steps
    "func_slice_timing": [],
    "func_reorient": ["func_slice_timing"],
    "func_motion_correction": ["func_reorien"],
    "func_despike": ["func_motion_correction"],
    "func_bias_correction": ["func_despike"],
    "func_conform": ["func_bias_correction", "anat_skullstripping"], # May also depend on anat_skullstripping for native space registration
    "func_skullstripping": ["func_conform"],
    "func_registration": ["func_skullstripping", "anat_registration"],  # May also depend on anat_registration for func2anat2template
    "func_apply_transforms": ["func_registration"],
}

# Steps that require GPU
GPU_STEPS = {
    "anat_conform",
    "anat_skullstripping",
    "func_conform",
    "func_skullstripping",
}

# Steps that are CPU-intensive (for resource allocation)
CPU_INTENSIVE_STEPS = {
    "anat_synthesis",
    "anat_conform",
    "anat_bias_correction",
    "anat_registration",
    "anat_surface_reconstruction",
    "func_conform",
    "func_bias_correction",
    "func_registration",
}

# Steps that are I/O intensive (for storage considerations)
IO_INTENSIVE_STEPS = {
    "func_apply_transforms",  # Large 4D files
    "anat_surface_reconstruction",  # Many surface files
}

def get_step_dependencies(step_name: str) -> list:
    """Get list of prerequisite steps for a given step.
    
    Args:
        step_name: Name of the processing step
        
    Returns:
        List of prerequisite step names
    """
    return STEP_DEPENDENCIES.get(step_name, [])


def requires_gpu(step_name: str) -> bool:
    """Check if a step requires GPU.
    
    Args:
        step_name: Name of the processing step
        
    Returns:
        True if step requires GPU, False otherwise
    """
    return step_name in GPU_STEPS


def is_cpu_intensive(step_name: str) -> bool:
    """Check if a step is CPU-intensive.
    
    Args:
        step_name: Name of the processing step
        
    Returns:
        True if step is CPU-intensive, False otherwise
    """
    return step_name in CPU_INTENSIVE_STEPS


def is_io_intensive(step_name: str) -> bool:
    """Check if a step is I/O intensive.
    
    Args:
        step_name: Name of the processing step
        
    Returns:
        True if step is I/O intensive, False otherwise
    """
    return step_name in IO_INTENSIVE_STEPS

