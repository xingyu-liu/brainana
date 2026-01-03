"""
Standalone step functions for Nextflow integration.

This module provides independent processing steps that can be called
from Nextflow processes, enabling maximum parallelization.
"""

from .types import StepInput, StepOutput, AnatomicalState, FunctionalState
from .dependencies import STEP_DEPENDENCIES, GPU_STEPS

__all__ = [
    'StepInput',
    'StepOutput',
    'AnatomicalState',
    'FunctionalState',
    'STEP_DEPENDENCIES',
    'GPU_STEPS',
]

