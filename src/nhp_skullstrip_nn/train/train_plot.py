"""
Training plotting and visualization utilities for nhp_skullstrip_nn.
Simple and clear implementation of peripheral training functions.
"""

import os
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server environments
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import torch
import seaborn as sns
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime

# Set style for better-looking plots
plt.style.use('default')
sns.set_palette("husl")


class TrainingPlotter:
    """Live plotting utility for training metrics."""
    
    def __init__(self, output_dir: str, plot_interval: int = 1):
        """Initialize the training plotter.
        
        Args:
            output_dir: Directory to save plots
            plot_interval: Plot every N epochs (default: 1)
        """
        self.output_dir = output_dir
        self.plot_interval = plot_interval
        self.plots_dir = os.path.join(output_dir, 'plots')
        os.makedirs(self.plots_dir, exist_ok=True)
        
        # Initialize plot data
        self.metrics_data = []
        
        # Set up the plotting style
        plt.rcParams['figure.figsize'] = (12, 8)
        plt.rcParams['font.size'] = 10
        self.colors = {'train': 'mediumseagreen', 'val': 'mediumpurple', 'single': 'mediumpurple'}
        
    def add_metrics(self, epoch: int, metrics: Dict[str, float]):
        """Add metrics for a new epoch.
        
        Args:
            epoch: Current epoch number
            metrics: Dictionary of metrics for this epoch
        """
        # Add epoch number to metrics
        epoch_metrics = {'epoch': epoch, **metrics}
        self.metrics_data.append(epoch_metrics)
        
        # Plot if we've reached the interval
        if epoch % self.plot_interval == 0:
            self._create_plots()
    
    def _create_plots(self):
        """Create all training plots."""
        if not self.metrics_data:
            return
            
        df = pd.DataFrame(self.metrics_data)
        
        # Create individual plots
        self._plot_loss(df)
        self._plot_dice(df)
        self._plot_learning_rate(df)
        self._plot_epoch_time(df)
        
        # Create combined plots
        self._plot_training_summary(df)
        
        # Save metrics CSV to root output directory (not in plots subfolder)
        csv_path = os.path.join(self.output_dir, 'training_metrics.csv')
        df.to_csv(csv_path, index=False)
    
    def _plot_loss(self, df: pd.DataFrame, ax=None, save_individual=True):
        """Plot training and validation loss."""
        if ax is None:
            plt.figure(figsize=(10, 6))
            ax = plt.gca()
        
        if 'train_loss' in df.columns:
            ax.plot(df['epoch'], df['train_loss'], self.colors['train'], linewidth=2, label='Training Loss', alpha=0.8)
        if 'val_loss' in df.columns:
            ax.plot(df['epoch'], df['val_loss'], self.colors['val'], linewidth=2, label='Validation Loss', alpha=0.8)
        
        ax.set_xlabel('Epoch')
        ax.set_ylabel('Loss')
        ax.set_title('Training and Validation Loss')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if save_individual:
            plt.tight_layout()
            plot_path = os.path.join(self.plots_dir, 'training_loss.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
    
    def _plot_dice(self, df: pd.DataFrame, ax=None, save_individual=True):
        """Plot training and validation Dice scores."""
        if ax is None:
            plt.figure(figsize=(10, 6))
            ax = plt.gca()
        
        if 'train_dice' in df.columns:
            ax.plot(df['epoch'], df['train_dice'], self.colors['train'], linewidth=2, label='Training Dice', alpha=0.8)
        if 'val_dice' in df.columns:
            ax.plot(df['epoch'], df['val_dice'], self.colors['val'], linewidth=2, label='Validation Dice', alpha=0.8)
        
        ax.set_xlabel('Epoch')
        ax.set_ylabel('Dice Score')
        ax.set_title('Training and Validation Dice Scores')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, 1)
        
        if save_individual:
            plt.tight_layout()
            plot_path = os.path.join(self.plots_dir, 'training_dice.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
    
    def _plot_learning_rate(self, df: pd.DataFrame, ax=None, save_individual=True):
        """Plot learning rate over time."""
        if ax is None:
            plt.figure(figsize=(10, 6))
            ax = plt.gca()
        
        if 'lr' in df.columns:
            lr_values = df['lr'].dropna()
            if len(lr_values) > 0 and (lr_values > 0).all():
                # Only use log scale if all values are positive
                ax.set_yscale('log')
            
            ax.plot(df['epoch'], df['lr'], self.colors['single'], linewidth=2, alpha=0.8)
            ax.set_xlabel('Epoch')
            ax.set_ylabel('Learning Rate')
            ax.set_title('Learning Rate Schedule')
            ax.grid(True, alpha=0.3)
        
        if save_individual:
            plt.tight_layout()
            plot_path = os.path.join(self.plots_dir, 'learning_rate.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
    
    def _plot_epoch_time(self, df: pd.DataFrame, ax=None, save_individual=True):
        """Plot epoch time over training."""
        if ax is None:
            plt.figure(figsize=(10, 6))
            ax = plt.gca()
        
        if 'epoch_time' in df.columns:
            ax.plot(df['epoch'], df['epoch_time'], self.colors['single'], linewidth=2, alpha=0.8)
            ax.set_xlabel('Epoch')
            ax.set_ylabel('Time (seconds)')
            ax.set_title('Epoch Training Time')
            ax.grid(True, alpha=0.3)
        
        if save_individual:
            plt.tight_layout()
            plot_path = os.path.join(self.plots_dir, 'epoch_time.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
    
    def _plot_training_summary(self, df: pd.DataFrame):
        """Create training summary plot."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Training Summary', fontsize=16, fontweight='bold')
        
        # Reuse individual plotting functions for subplots
        self._plot_loss(df, axes[0, 0], save_individual=False)
        self._plot_dice(df, axes[0, 1], save_individual=False)
        self._plot_learning_rate(df, axes[1, 0], save_individual=False)
        
        # Subplot 4: Training progress with moving average
        ax4 = axes[1, 1]
        if 'train_dice' in df.columns:
            epochs = df['epoch']
            train_dice = df['train_dice']
            
            # Calculate moving average for smoother trend
            window = min(5, len(train_dice))
            if window > 1:
                moving_avg = df['train_dice'].rolling(window=window, center=True).mean()
                ax4.plot(epochs, moving_avg, self.colors['single'], linewidth=3, label=f'Moving Average (w={window})')
            
            ax4.plot(epochs, train_dice, self.colors['single'], linewidth=2, alpha=0.8, label='Training Dice')
            ax4.set_xlabel('Epoch')
            ax4.set_ylabel('Dice Score')
            ax4.set_title('Training Progress')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
            ax4.set_ylim(0, 1)
        
        plt.tight_layout()
        plot_path = os.path.join(self.plots_dir, 'training_summary.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()
    
    def finalize_plots(self):
        """Create final plots and save all data."""
        if self.metrics_data:
            self._create_plots()
            # All training plots saved to plots directory


class PlottingCallback:
    """Callback for live plotting during training."""
    
    def __init__(self, output_dir: str, plot_interval: int = 1):
        """Initialize plotting callback.
        
        Args:
            output_dir: Directory to save plots
            plot_interval: Plot every N epochs (default: 1)
        """
        self.plotter = TrainingPlotter(output_dir, plot_interval)
    
    def on_train_begin(self, trainer):
        """Called at the beginning of training."""
        pass
    
    def on_train_end(self, trainer):
        """Called at the end of training."""
        self.plotter.finalize_plots()
    
    def on_epoch_begin(self, epoch: int, trainer):
        """Called at the beginning of each epoch."""
        pass
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, float], trainer):
        """Called at the end of each epoch."""
        # Extract metrics from logs
        metrics = {
            'train_loss': logs.get('loss', 0.0),
            'train_dice': logs.get('dice', 0.0),
            'val_loss': logs.get('val_loss', 0.0),
            'val_dice': logs.get('val_dice', 0.0),
            'lr': logs.get('lr', 0.0),
            'epoch_time': logs.get('epoch_time', 0.0)
        }
        
        # Add GPU memory info if available
        if hasattr(trainer, 'device') and trainer.device.type == 'cuda':
            try:
                gpu_memory = torch.cuda.memory_allocated(trainer.device) / (1024**3)  # Convert to GB
                metrics['gpu_allocated'] = gpu_memory
            except:
                pass
        
        # Add metrics to plotter
        self.plotter.add_metrics(epoch + 1, metrics)


def create_training_summary(config, training_history, output_dir):
    """Create a comprehensive training summary report.
    
    Args:
        config: Training configuration
        training_history: List of training metrics per epoch
        output_dir: Output directory for saving summary
    """
    # Save directly to output_dir root, no nested summary directory
    
    # Create summary text file in root directory
    summary_file = os.path.join(output_dir, 'training_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("TRAINING SUMMARY REPORT\n")
        f.write("=" * 60 + "\n\n")
        
        f.write(f"Training completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Model: {config.model_name}\n")
        f.write(f"Modal: {config.modal}\n")
        f.write(f"Label: {config.label}\n")
        f.write(f"Total epochs: {len(training_history)}\n\n")
        
        if training_history:
            # Best metrics
            best_epoch = np.argmin([h.get('val_loss', float('inf')) for h in training_history])
            best_val_loss = training_history[best_epoch].get('val_loss', 0)
            best_val_dice = training_history[best_epoch].get('val_dice', 0)
            
            f.write(f"Best validation loss: {best_val_loss:.6f} (epoch {best_epoch + 1})\n")
            f.write(f"Best validation Dice: {best_val_dice:.6f} (epoch {best_epoch + 1})\n\n")
            
            # Final metrics
            final_epoch = training_history[-1]
            f.write(f"Final training loss: {final_epoch.get('loss', 0):.6f}\n")
            f.write(f"Final validation loss: {final_epoch.get('val_loss', 0):.6f}\n")
            f.write(f"Final training Dice: {final_epoch.get('dice', 0):.6f}\n")
            f.write(f"Final validation Dice: {final_epoch.get('val_dice', 0):.6f}\n\n")
        
        # Configuration summary
        f.write("CONFIGURATION SUMMARY:\n")
        f.write("-" * 30 + "\n")
        f.write(f"Batch size: {config.batch_size}\n")
        f.write(f"Learning rate: {config.learning_rate}\n")
        f.write(f"Optimizer: {config.optimizer}\n")
        f.write(f"Loss function: {getattr(config, 'loss_type', 'dice')}\n")
        f.write(f"Data augmentation: {getattr(config, 'augmentation', False)}\n")
        f.write(f"Random seed: {config.random_seed}\n")
    
    # Don't create duplicate plots here - plots are already handled by PlottingCallback
    # Just return the output directory
    return output_dir


def save_test_set_info(test_files, output_dir):
    """Save information about the test set for later evaluation.
    
    Args:
        test_files: List of test file paths
        output_dir: Output directory
    """
    test_info_dir = os.path.join(output_dir, 'test_set_info')
    os.makedirs(test_info_dir, exist_ok=True)
    
    # Save test file list
    test_list_file = os.path.join(test_info_dir, 'test_files.txt')
    with open(test_list_file, 'w') as f:
        for file_path in test_files:
            f.write(f"{file_path}\n")
    
    # Save test set summary
    summary_file = os.path.join(test_info_dir, 'test_set_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("TEST SET INFORMATION\n")
        f.write("=" * 30 + "\n")
        f.write(f"Total test files: {len(test_files)}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if test_files:
            f.write("Test files:\n")
            for i, file_path in enumerate(test_files, 1):
                f.write(f"{i:3d}. {os.path.basename(file_path)}\n")
    
            # Test set info saved to test info directory
    return test_info_dir
