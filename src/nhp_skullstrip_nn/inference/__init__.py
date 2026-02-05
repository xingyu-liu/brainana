"""
Inference module for nhp_skullstrip_nn.

This module contains prediction and inference functionality.
"""

from .prediction import predict_volumes
from .evaluate_testset import evaluate_test_set_from_training, evaluate_test_set_from_paths

__all__ = [
    'predict_volumes',
    'evaluate_test_set_from_training',
    'evaluate_test_set_from_paths',
    'evaluate_single_volume',
    'create_detailed_evaluation_plot',
    'generate_evaluation_summary',
    'create_text_summary_report',
    'create_summary_plots'
]
