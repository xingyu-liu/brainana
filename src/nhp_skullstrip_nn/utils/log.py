#!/usr/bin/env python3
"""
Logging utilities for nhp_skullstrip_nn.
Provides consistent logging patterns and GPU information logging.
"""

import os
import sys
import logging
import inspect
import torch

from datetime import datetime
from typing import Optional, Union, Dict, Any
from pathlib import Path


class MacacaLogger:
    """Centralized logger for nhp_skullstrip_nn with consistent formatting and configuration."""
    
    def __init__(self, name: str, output_dir: Optional[str] = None, log_level: str = 'INFO'):
        """Initialize the logger.
        
        Args:
            name: Logger name (usually __name__)
            output_dir: Directory to save log files (optional)
            log_level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        """
        self.name = name
        self.output_dir = output_dir
        self.log_level = log_level.upper()
        
        # Create logger instance
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, self.log_level))
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup logging handlers."""
        # Console handler with colored output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.log_level))
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler if output_dir is specified
        if self.output_dir:
            self._setup_file_handler(formatter)
    
    def _setup_file_handler(self, formatter):
        """Setup file logging handler."""
        try:
            log_dir = Path(self.output_dir) / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = log_dir / f'nhp_skullstrip_nn_{timestamp}.log'
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, self.log_level))
            file_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.info(f"Log file created: {log_file}")
            
        except Exception as e:
            self.logger.warning(f"Failed to setup file logging: {e}")
    
    def get_logger(self) -> logging.Logger:
        """Get the configured logger instance."""
        return self.logger


def setup_logging(
    name: str = 'nhp_skullstrip_nn',
    output_dir: Optional[str] = None,
    log_level: str = 'INFO'
) -> logging.Logger:
    """Setup logging for a module or component.
    
    Args:
        name: Logger name (usually __name__)
        output_dir: Directory to save log files
        log_level: Logging level
        
    Returns:
        Configured logger instance
    """
    macaca_logger = MacacaLogger(name, output_dir, log_level)
    return macaca_logger.get_logger()


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance for a module.
    
    Args:
        name: Logger name (if None, uses calling module's name)
        
    Returns:
        Logger instance
    """
    if name is None:
        # Get the calling module's name
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'nhp_skullstrip_nn')
    
    return logging.getLogger(name)


# Convenience functions for common logging patterns
def log_training_start(logger: logging.Logger, config: dict):
    """Log training start information."""
    logger.info("🚀 Starting nhp_skullstrip_nn Training")
    logger.info("=" * 40)
    logger.info(f"Configuration: {config}")


def log_training_complete(logger: logging.Logger, output_dir: str):
    """Log training completion."""
    logger.info(f"✅ Training completed! Model saved in: {output_dir}")


def log_training_failed(logger: logging.Logger, error: Exception):
    """Log training failure."""
    logger.error(f"❌ Training failed: {error}")


def log_model_info(logger: logging.Logger, model: object, device: str, dataset_size: int):
    """Log model and training setup information."""
    if hasattr(model, 'parameters'):
        param_count = sum(p.numel() for p in model.parameters())
        logger.info(f"🔧 Model: {param_count:,} parameters")
    logger.info(f"🔧 Dataset: {dataset_size} samples")
    logger.info(f"🔧 Device: {device}")


def log_epoch_progress(logger: logging.Logger, epoch: int, total_epochs: int, loss: float, metrics: Optional[dict] = None):
    """Log epoch progress information."""
    log_msg = f"Epoch {epoch+1:3d}/{total_epochs}: Loss = {loss:.4f}"
    if metrics:
        metric_str = ", ".join([f"{k}: {v:.4f}" for k, v in metrics.items()])
        log_msg += f" | {metric_str}"
    logger.info(log_msg)


def log_checkpoint_saved(logger: logging.Logger, checkpoint_path: str):
    """Log checkpoint save operation."""
    logger.info(f"  → Checkpoint saved: {checkpoint_path}")


def log_model_saved(logger: logging.Logger, model_path: str):
    """Log model save operation."""
    logger.info(f"  → Model saved: {model_path}")


def log_gpu_info(logger: logging.Logger):
    """Log GPU information and status."""
    try:
        if not torch.cuda.is_available():
            logger.info("CUDA not available, using CPU")
            return
        
        logger.info(f"Found {torch.cuda.device_count()} GPU(s)")
        
        for i in range(torch.cuda.device_count()):
            gpu_name = torch.cuda.get_device_name(i)
            memory_allocated = torch.cuda.memory_allocated(i) / (1024**3)
            memory_reserved = torch.cuda.memory_reserved(i) / (1024**3)
            memory_total = torch.cuda.get_device_properties(i).total_memory / (1024**3)
            
            logger.info(f"  GPU {i}: {gpu_name} - {memory_allocated:.1f}GB / {memory_total:.1f}GB allocated")
            
    except ImportError:
        logger.info("PyTorch not available, cannot log GPU information")
    except Exception as e:
        logger.warning(f"Failed to log GPU information: {e}")


def log_data_info(logger: logging.Logger, image_files: list, label_files: list, missing_count: int = 0):
    """Log dataset information."""
    if missing_count > 0:
        logger.warning(f"{missing_count} images missing corresponding labels")
    
    logger.info(f"Found {len(image_files)} valid image-label pairs")
    logger.info(f"Labels: {len(label_files)} files")


def log_prediction_info(logger: logging.Logger, model_path: str, input_path: str, output_path: str, device: str):
    """Log prediction setup information."""
    logger.info("🧠 Running nhp_skullstrip_nn Prediction")
    logger.info("=" * 40)
    logger.info(f"📁 Model: {model_path}")
    logger.info(f"📥 Input: {input_path}")
    logger.info(f"📤 Output: {output_path}")
    logger.info(f"🔧 Device: {device}")


def log_prediction_complete(logger: logging.Logger, output_path: str):
    """Log prediction completion."""
    logger.info("✓ Prediction completed successfully!")
    logger.info(f"✗ Output saved: {output_path}")


def log_prediction_failed(logger: logging.Logger, error: Exception):
    """Log prediction failure."""
    logger.error(f" Prediction failed: {error}")


# Legacy compatibility - these functions maintain the old interface
def setup_training_logging(output_dir: str, log_level: str = 'INFO') -> logging.Logger:
    """Legacy function for backward compatibility."""
    return setup_logging('nhp_skullstrip_nn.training', output_dir, log_level)