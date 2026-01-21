"""
Standalone step functions for Nextflow integration.

This module provides independent processing steps that can be called
from Nextflow processes, enabling maximum parallelization.
"""

from .types import StepInput, StepOutput, AnatomicalState, FunctionalState

__all__ = [
    'StepInput',
    'StepOutput',
    'AnatomicalState',
    'FunctionalState',
]

