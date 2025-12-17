"""
Training callbacks for monitoring and control
"""

import os
import torch
from abc import ABC, abstractmethod
from typing import Dict, Any


class Callback(ABC):
    """Base class for training callbacks."""
    
    def on_train_begin(self, trainer):
        """Called at the start of training."""
        pass
    
    def on_train_end(self, trainer):
        """Called at the end of training."""
        pass
    
    def on_epoch_begin(self, epoch: int, trainer):
        """Called at the start of each epoch."""
        pass
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, float], trainer):
        """Called at the end of each epoch."""
        pass


class EarlyStopping(Callback):
    """Early stopping callback to prevent overfitting."""
    
    def __init__(self, patience: int = 10, monitor: str = 'val_loss', 
                 mode: str = 'min', min_delta: float = 0.0, 
                 restore_best_weights: bool = True):
        """
        Args:
            patience: Number of epochs to wait before stopping
            monitor: Metric to monitor
            mode: 'min' for metrics that should decrease, 'max' for increase
            min_delta: Minimum change to qualify as improvement
            restore_best_weights: Whether to restore best weights
        """
        self.patience = patience
        self.monitor = monitor
        self.mode = mode
        self.min_delta = min_delta
        self.restore_best_weights = restore_best_weights
        
        self.wait = 0
        self.stopped_epoch = 0
        self.best_weights = None
        
        if mode == 'min':
            self.monitor_op = lambda a, b: a < b - self.min_delta
            self.best = float('inf')
        elif mode == 'max':
            self.monitor_op = lambda a, b: a > b + self.min_delta
            self.best = float('-inf')
        else:
            raise ValueError(f"mode must be 'min' or 'max', got {mode}")
    
    def on_train_begin(self, trainer):
        """Reset early stopping state."""
        self.wait = 0
        self.stopped_epoch = 0
        self.best_weights = None
        
        if self.mode == 'min':
            self.best = float('inf')
        else:
            self.best = float('-inf')
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, float], trainer):
        """Check for early stopping condition."""
        current = logs.get(self.monitor)
        if current is None:
            trainer.logger.warning(f"Early stopping: metric '{self.monitor}' not found in logs")
            return
        
        if self.monitor_op(current, self.best):
            self.best = current
            self.wait = 0
            
            if self.restore_best_weights:
                self.best_weights = {k: v.cpu().clone() for k, v in trainer.model.state_dict().items()}
                
            trainer.logger.info(f"Early stopping: metric improved to {current:.4f}")
        else:
            self.wait += 1
            
            if self.wait >= self.patience:
                self.stopped_epoch = epoch
                trainer.stop_training = True
                trainer.logger.info(f"Early stopping: triggered after {self.patience} epochs")
                
                if self.restore_best_weights and self.best_weights is not None:
                    trainer.model.load_state_dict({k: v.to(trainer.device) for k, v in self.best_weights.items()})
                    trainer.logger.info("Early stopping: restored best model weights")


class ModelCheckpoint(Callback):
    """Model checkpoint callback to save model weights."""
    
    def __init__(self, filepath: str, monitor: str = 'val_loss', 
                 mode: str = 'min', save_best_only: bool = True):
        """
        Args:
            filepath: Path to save the model file
            monitor: Metric to monitor for best model
            mode: 'min' for metrics that should decrease, 'max' for increase
            save_best_only: If True, only save when the model improves
        """
        self.filepath = filepath
        self.monitor = monitor
        self.mode = mode
        self.save_best_only = save_best_only
        
        if mode == 'min':
            self.monitor_op = lambda a, b: a < b
            self.best = float('inf')
        elif mode == 'max':
            self.monitor_op = lambda a, b: a > b
            self.best = float('-inf')
        else:
            raise ValueError(f"mode must be 'min' or 'max', got {mode}")
    
    def on_train_begin(self, trainer):
        """Initialize checkpoint state."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        
        if self.mode == 'min':
            self.best = float('inf')
        else:
            self.best = float('-inf')
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, float], trainer):
        """Save model checkpoint if conditions are met."""
        current = logs.get(self.monitor)
        
        if current is None:
            trainer.logger.warning(f"Checkpoint metric '{self.monitor}' not found")
            return
        
        # Check if we should save
        should_save = not self.save_best_only or self.monitor_op(current, self.best)
        
        if should_save:
            if self.monitor_op(current, self.best):
                self.best = current
                trainer.logger.info(f"Model improved ({self.monitor}: {current:.2f}), saving to {self.filepath}")
            
            # Prepare checkpoint data
            checkpoint = {
                'epoch': epoch,
                'model_state_dict': trainer.model.state_dict(),
                'optimizer_state_dict': trainer.optimizer.state_dict(),
                'scheduler_state_dict': trainer.scheduler.state_dict() if trainer.scheduler else None,
                'best_metric': self.best,
                'config': trainer.config.__dict__
            }
            
            # Save checkpoint
            torch.save(checkpoint, self.filepath)
            trainer.logger.info(f"Model checkpoint saved: {self.filepath}")


class CallbackList:
    """Container for a list of callbacks."""
    
    def __init__(self, callbacks=None):
        """Initialize callback list."""
        self.callbacks = callbacks or []
    
    def append(self, callback):
        """Add a callback to the list."""
        self.callbacks.append(callback)
    
    def on_train_begin(self, trainer):
        """Call on_train_begin for all callbacks."""
        for callback in self.callbacks:
            callback.on_train_begin(trainer)
    
    def on_train_end(self, trainer):
        """Call on_train_end for all callbacks."""
        for callback in self.callbacks:
            callback.on_train_end(trainer)
    
    def on_epoch_begin(self, epoch: int, trainer):
        """Call on_epoch_begin for all callbacks."""
        for callback in self.callbacks:
            callback.on_epoch_begin(epoch, trainer)
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, float], trainer):
        """Call on_epoch_end for all callbacks."""
        for callback in self.callbacks:
            callback.on_epoch_end(epoch, logs, trainer)
