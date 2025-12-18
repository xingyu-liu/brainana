"""
Scripts module for macacaMRINN.

This module contains command-line scripts for training and inference.
"""

from .run_prediction import main as run_prediction
from .macaca_cli import main as macaca_cli

__all__ = [
    'run_prediction',
    'macaca_cli'
]
