"""
Scripts module for nhp_skullstrip_nn.

This module contains command-line scripts for training and inference.
"""

from .run_prediction import main as run_prediction

__all__ = [
    'run_prediction'
]
