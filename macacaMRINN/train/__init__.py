"""
Clean Training Module for macacaMRINN

Streamlined training components focused on simplicity and efficiency.
"""

from .trainer import Trainer
from .losses import DiceLoss, CombinedLoss, FocalLoss
from .metrics import compute_foreground_dice, compute_dice, MetricsTracker
from .callbacks import EarlyStopping, ModelCheckpoint, CallbackList
from .train_plot import TrainingPlotter, PlottingCallback, create_training_summary, save_test_set_info

__all__ = [
    # Core components
    'Trainer',
    
    # Loss functions
    'DiceLoss',
    'CombinedLoss', 
    'FocalLoss',
    
    # Metrics
    'compute_foreground_dice',
    'compute_dice',
    'MetricsTracker',
    
    # Callbacks
    'EarlyStopping',
    'ModelCheckpoint',
    'CallbackList',
    
    # Peripheral functions
    'TrainingPlotter',
    'PlottingCallback',
    'create_training_summary',
    'save_test_set_info'
]
