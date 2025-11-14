"""
Core Trainer Class for macacaMRINN - Simplified
"""

import os
import time
import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd

from torch.amp import autocast, GradScaler
from typing import Tuple
from tqdm import tqdm

from ..config import TrainingConfig
from ..model.unet import UNet2d
from ..utils import get_device
from ..model import ModelLoader
from .train_utils import setup_logging, prepare_data_loaders, count_parameters, format_time
from .losses import DiceLoss, CombinedLoss, FocalLoss
from .metrics import compute_foreground_dice, MetricsTracker
from .callbacks import CallbackList, EarlyStopping, ModelCheckpoint
from .train_plot import PlottingCallback


class Trainer:
    """Clean trainer for macacaMRINN."""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.stop_training = False
        
        # Setup directories and logging
        os.makedirs(config.output_dir, exist_ok=True)
        os.makedirs(os.path.join(config.output_dir, 'checkpoints'), exist_ok=True)
        
        self.logger = setup_logging(config.output_dir, getattr(config, 'log_level', 'INFO'))
        self.logger.info(f"Trainer: initializing for {config.modal}_{config.label}")
        
        # Set random seed
        if config.random_seed is not None:
            torch.manual_seed(config.random_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(config.random_seed)
        
        # Setup device
        self.device = get_device() if config.device == "auto" else torch.device(config.device)
        self.logger.info(f"System: using device {self.device}")
        
        # Initialize components
        self.model = None
        self.optimizer = None
        self.scheduler = None
        self.scaler = None
        
        # Setup loss and callbacks
        self.criterion = self._setup_loss_function()
        self.callbacks = self._setup_callbacks()
        
        # Training state
        self.current_epoch = 0
        self.best_val_loss = float('inf')
        self.training_history = []
        
        # Metrics
        self.train_metrics = MetricsTracker()
        self.val_metrics = MetricsTracker()
    
    def _setup_loss_function(self):
        """Setup loss function."""
        loss_type = getattr(self.config, 'loss_type', 'dice')
        
        if loss_type == 'dice':
            return DiceLoss()
        elif loss_type == 'combined':
            return CombinedLoss()
        elif loss_type == 'focal':
            return FocalLoss()
        elif loss_type == 'crossentropy':
            return nn.CrossEntropyLoss()
        else:
            return DiceLoss()
    
    def _setup_callbacks(self) -> CallbackList:
        """Setup callbacks."""
        callbacks = []
        
        # Early stopping
        if getattr(self.config, 'patience', 0) > 0:
            callbacks.append(EarlyStopping(
                patience=self.config.patience,
                monitor='val_loss',
                min_delta=getattr(self.config, 'early_stopping_min_delta', 0.0),
                restore_best_weights=getattr(self.config, 'early_stopping_restore_best_weights', True)
            ))
        
        # Model checkpoint
        checkpoint_path = os.path.join(
            self.config.output_dir, 'checkpoints', 'best_model.pth'
        )
        callbacks.append(ModelCheckpoint(
            filepath=checkpoint_path,
            monitor='val_loss'
        ))
        
        # Add plotting callback for live training visualization
        if getattr(self.config, 'enable_plotting', True):
            callbacks.append(PlottingCallback(
                output_dir=self.config.output_dir,
                plot_interval=getattr(self.config, 'plot_interval', 1)
            ))
        
        return CallbackList(callbacks)
    
    def train(self):
        """Main training loop."""
        start_time = time.time()
        
        # Setup training components
        self._setup_training_components()
        
        self.logger.info("Training: starting...")
        self.callbacks.on_train_begin(self)
        
        try:
            for epoch in range(self.config.num_epochs):
                if self.stop_training:
                    break
                
                self.current_epoch = epoch
                self.callbacks.on_epoch_begin(epoch, self)
                
                # Train and validate
                train_loss, train_dice = self._train_epoch()
                val_loss, val_dice = self._validate_epoch()
                
                # Scheduler step
                if hasattr(self.scheduler, 'step'):
                    if getattr(self.config, 'use_cosine_scheduler', False):
                        self.scheduler.step()
                    else:
                        self.scheduler.step(val_loss)
                
                # Log results with consistent format
                self.logger.info(
                    f"Epoch {epoch+1:3d}/{self.config.num_epochs} | "
                    f"Train: loss={train_loss:.4f}, dice={train_dice:.4f} | "
                    f"Val: loss={val_loss:.4f}, dice={val_dice:.4f}"
                )
                
                # Update history and best metric
                epoch_logs = {
                    'loss': train_loss, 'dice': train_dice,
                    'val_loss': val_loss, 'val_dice': val_dice
                }
                self.training_history.append(epoch_logs)
                
                if val_loss < self.best_val_loss:
                    self.best_val_loss = val_loss
                
                self.callbacks.on_epoch_end(epoch, epoch_logs, self)
        
        except KeyboardInterrupt:
            self.logger.info("Training: interrupted by user")
        finally:
            self.callbacks.on_train_end(self)
            total_time = time.time() - start_time
            self.logger.info(f"Training: completed in {format_time(total_time)}")
            
            # Generate training summary and additional outputs
            self._generate_training_outputs()
    
    def _generate_training_outputs(self):
        """Generate additional training outputs: summary, metrics, plots."""
        try:
            from .train_plot import create_training_summary
            
            # Create training summary - will save to root directory
            create_training_summary(
                self.config, 
                self.training_history, 
                self.config.output_dir
            )
            self.logger.info(f"Output: training summary generated")
            
            # Save training metrics CSV to root directory (no separate metrics folder)
            metrics_df = pd.DataFrame(self.training_history)
            metrics_csv = os.path.join(self.config.output_dir, 'training_metrics.csv')
            metrics_df.to_csv(metrics_csv, index=False)
            self.logger.info(f"Output: training metrics saved to root")
                
        except Exception as e:
            self.logger.warning(f"Output: failed to generate training outputs - {e}")
    
    def _setup_training_components(self):
        """Setup model, optimizer, scheduler, data loaders."""
        # Create model
        self.model = UNet2d(
            dim_in=self.config.num_input_slices,
            num_conv_block=getattr(self.config, 'num_conv_block', 5),
            kernel_root=getattr(self.config, 'kernel_root', 16),
            use_inst_norm=getattr(self.config, 'use_inst_norm', True),
            num_classes=getattr(self.config, 'num_classes', 2)
        ).to(self.device)
        
        # Check if we should load pretrained weights first
        pretrained_loaded = False
        if self.config.pretrained_model_path and os.path.exists(self.config.pretrained_model_path):
            try:
                self.logger.info(f"Model: loading pretrained weights from {self.config.pretrained_model_path}")
                # Use the existing ModelLoader functionality
                # Convert torch.device to device_id format
                if self.device.type == 'cuda':
                    device_id = self.device.index if self.device.index is not None else 0
                else:
                    device_id = -1  # CPU
                
                self.model = ModelLoader.load_model_from_file(
                    model_path=self.config.pretrained_model_path,
                    device_id=device_id,
                    config=self.config,
                    logger=self.logger
                )
                self.logger.info(f"Model: pretrained weights loaded successfully")

                # Check if loaded model has NaN weights - if so, we can't use it
                has_nan = any(torch.isnan(param).any() for param in self.model.parameters())
                if has_nan:
                    self.logger.error("Model: pretrained weights contain NaN - cannot use for finetuning")
                    self.logger.warning("Model: falling back to random initialization")
                    pretrained_loaded = False
                else:
                    # Check if the loaded model needs to be adapted for different number of classes
                    current_num_classes = getattr(self.model, 'num_classes', None)
                    if current_num_classes is None:
                        # Try to infer from output layer
                        try:
                            current_num_classes = self.model.out_layer.out_channels
                        except AttributeError:
                            current_num_classes = 2  # Default assumption
                    
                    target_num_classes = getattr(self.config, 'num_classes', 2)
                    
                    if current_num_classes != target_num_classes:
                        self.logger.info(f"Model: adapting from {current_num_classes} to {target_num_classes} classes")
                        
                        # Replace the output layer to match the target number of classes
                        kernel_root = getattr(self.config, 'kernel_root', 16)
                        self.model.out_layer = nn.Conv2d(kernel_root, target_num_classes, 3, 1, 1).to(self.device)
                        
                        # Update the model's num_classes attribute
                        self.model.num_classes = target_num_classes
                        
                        # Initialize the new output layer weights
                        nn.init.xavier_uniform_(self.model.out_layer.weight)
                        if self.model.out_layer.bias is not None:
                            nn.init.constant_(self.model.out_layer.bias, 0)
                        
                        self.logger.info(f"Model: successfully adapted to {target_num_classes} classes")
                    
                    self.logger.info("Model: pretrained model ready for finetuning")
                    pretrained_loaded = True

            except Exception as e:
                self.logger.warning(f"Model: failed to load pretrained weights - {e}")
                self.logger.warning("Model: falling back to random initialization")
                pretrained_loaded = False
        
        # Only initialize random weights if pretrained model wasn't loaded successfully
        if not pretrained_loaded:
            self.logger.info("Model: initializing with random weights")
            # Create model if not loaded from pretrained
            if not hasattr(self, 'model') or self.model is None:
                self.model = UNet2d(
                    dim_in=self.config.num_input_slices,
                    num_conv_block=getattr(self.config, 'num_conv_block', 5),
                    kernel_root=getattr(self.config, 'kernel_root', 16),
                    use_inst_norm=getattr(self.config, 'use_inst_norm', True),
                    num_classes=getattr(self.config, 'num_classes', 2)
                ).to(self.device)
            
            # Initialize model weights properly to prevent NaN
            self._initialize_model_weights()
        
        # Setup optimizer with conservative settings to prevent NaN
        learning_rate = self.config.learning_rate
        if learning_rate is not None and learning_rate > 5e-4:
            self.logger.warning(f"Training: learning rate {learning_rate:.2e} reduced to 5e-4 to prevent NaN")
            learning_rate = 5e-4
        elif learning_rate is None:
            # Default learning rate if not specified
            learning_rate = 1e-4
        
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=getattr(self.config, 'weight_decay', 0.01),
            eps=1e-8  # Add epsilon for numerical stability
        )
        
        # Setup training mode based on explicit configuration
        training_mode = getattr(self.config, 'training_mode').lower()
        
        if training_mode == 'scratch':
            self.logger.info("Training: from scratch")
        elif training_mode == 'continual_learning':
            if not (self.config.pretrained_model_path and os.path.exists(self.config.pretrained_model_path) and pretrained_loaded):
                raise ValueError("Continual learning requires a valid pretrained model")
            self.logger.info("Training: continual learning mode (preserving optimizer state)")
            self._setup_continual_learning()
        elif training_mode == 'fine_tuning':
            if not (self.config.pretrained_model_path and os.path.exists(self.config.pretrained_model_path) and pretrained_loaded):
                raise ValueError("Fine-tuning requires a valid pretrained model")
            self.logger.info("Training: fine-tuning mode (fresh optimizer state)")
        else:
            raise ValueError(f"Invalid training_mode '{training_mode}'. Use: scratch, continual_learning, or fine_tuning")
        
        # Setup scheduler
        if getattr(self.config, 'use_cosine_scheduler', False):
            self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer, T_max=self.config.num_epochs
            )
        else:
            # Use ReduceLROnPlateau with config parameters
            # Use the same patience as early stopping for consistency
            scheduler_patience = getattr(self.config, 'patience', 10)
            scheduler_factor = getattr(self.config, 'scheduler_factor', 0.5)
            self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer, mode='min', factor=scheduler_factor, patience=scheduler_patience
            )
        
        # Setup mixed precision - temporarily disabled to prevent NaN issues
        # if getattr(self.config, 'mixed_precision', False) and torch.cuda.is_available():
        #     self.scaler = GradScaler()
        self.scaler = None
        self.logger.info("Training: mixed precision disabled to prevent NaN issues")
        
        # Setup data loaders
        self.train_loader, self.val_loader, self.test_loader, test_files = prepare_data_loaders(
            self.config, self.logger
        )
        if test_files:
            self.test_files = test_files[0]  # Store test image paths
        else:
            self.test_files = []
        
        total_params, trainable_params = count_parameters(self.model)
        self.logger.info(f"Model: {total_params:,} total parameters, {trainable_params:,} trainable")
    
    def _train_epoch(self) -> Tuple[float, float]:
        """Train for one epoch."""
        self.model.train()
        self.train_metrics.reset()
        
        # Create progress bar with detailed metrics
        pbar = tqdm(self.train_loader, desc=f'Training Epoch {self.current_epoch + 1}')
        
        for batch in pbar:
            # Handle batch of BlockDataset objects
            if isinstance(batch, list):
                # Process each BlockDataset in the batch
                for block_dataset in batch:
                    slice_data, slice_list, _ = block_dataset.get_one_directory(axis=0)
                    
                    volume_loss, volume_dice, num_slices = 0.0, 0.0, 0
                    
                    # Accumulate predictions and targets for volume-level dice computation
                    volume_predictions = []
                    volume_targets = []
                    
                    for i, _ in enumerate(slice_list):
                        img_block, label_block = slice_data[i]
                        loss, pred_logits, target = self._process_slice(img_block, label_block, training=True)
                        volume_loss += loss
                        num_slices += 1
                        
                        # Accumulate predictions and targets for volume-level dice
                        if pred_logits is not None and target is not None:
                            volume_predictions.append(pred_logits)
                            volume_targets.append(target)
                    
                    if num_slices > 0:
                        avg_vol_loss = volume_loss / num_slices
                        
                        # Compute volume-level dice (like in prediction)
                        if volume_predictions and volume_targets:
                            # Stack all slice predictions and targets
                            stacked_predictions = torch.stack(volume_predictions, dim=0)  # [num_slices, 2, H, W]
                            stacked_targets = torch.stack(volume_targets, dim=0)  # [num_slices, H, W]
                            
                            # Compute volume-level dice using the same method as prediction
                            volume_dice = compute_foreground_dice(stacked_predictions, stacked_targets)
                        else:
                            volume_dice = 0.0
                        
                        self.train_metrics.update(loss=avg_vol_loss, dice=volume_dice)
                        
                        # Update progress bar with current volume metrics
                        avg_metrics = self.train_metrics.get_averages()
                        current_avg_loss = avg_metrics['loss']
                        current_avg_dice = avg_metrics['dice']
                        pbar.set_postfix({
                            'dice': f'{volume_dice:.4f}',
                        })
            else:
                # Single BlockDataset (shouldn't happen with current setup, but handle it)
                slice_data, slice_list, _ = batch.get_one_directory(axis=0)
                
                volume_loss, num_slices = 0.0, 0
                # Accumulate predictions and targets for volume-level dice computation
                volume_predictions = []
                volume_targets = []
                
                for i, _ in enumerate(slice_list):
                    img_block, label_block = slice_data[i]
                    loss, pred_logits, target = self._process_slice(img_block, label_block, training=True)
                    volume_loss += loss
                    num_slices += 1
                    
                    # Accumulate predictions and targets for volume-level dice
                    if pred_logits is not None and target is not None:
                        volume_predictions.append(pred_logits)
                        volume_targets.append(target)
                
                if num_slices > 0:
                    avg_vol_loss = volume_loss / num_slices
                    
                    # Compute volume-level dice (like in prediction)
                    if volume_predictions and volume_targets:
                        # Stack all slice predictions and targets
                        stacked_predictions = torch.stack(volume_predictions, dim=0)  # [num_slices, 2, H, W]
                        stacked_targets = torch.stack(volume_targets, dim=0)  # [num_slices, H, W]
                        
                        # Compute volume-level dice using the same method as prediction
                        volume_dice = compute_foreground_dice(stacked_predictions, stacked_targets)
                    else:
                        volume_dice = 0.0
                    
                    self.train_metrics.update(loss=avg_vol_loss, dice=volume_dice)
                    
                    # Update progress bar with current volume metrics
                    avg_metrics = self.train_metrics.get_averages()
                    current_avg_loss = avg_metrics['loss']
                    current_avg_dice = avg_metrics['dice']
                    pbar.set_postfix({
                        'dice': f'{volume_dice:.2f}',
                    })
        
        avg_metrics = self.train_metrics.get_averages()
        return avg_metrics['loss'], avg_metrics['dice']
    
    def _validate_epoch(self) -> Tuple[float, float]:
        """Validate for one epoch."""
        if self.val_loader is None:
            return 0.0, 0.0
        
        self.model.eval()
        self.val_metrics.reset()
        
        # Create progress bar with detailed metrics
        pbar = tqdm(self.val_loader, desc=f'Validation Epoch {self.current_epoch + 1}')
        
        with torch.no_grad():
            for batch in pbar:
                # Handle batch of BlockDataset objects
                if isinstance(batch, list):
                    # Process each BlockDataset in the batch
                    for block_dataset in batch:
                        slice_data, slice_list, _ = block_dataset.get_one_directory(axis=0)
                        
                        volume_loss, num_slices = 0.0, 0
                        
                        # Accumulate predictions and targets for volume-level dice computation
                        volume_predictions = []
                        volume_targets = []
                        
                        for i, _ in enumerate(slice_list):
                            img_block, label_block = slice_data[i]
                            loss, pred_logits, target = self._process_slice(img_block, label_block, training=False)
                            volume_loss += loss
                            num_slices += 1
                            
                            # Accumulate predictions and targets for volume-level dice
                            if pred_logits is not None and target is not None:
                                volume_predictions.append(pred_logits)
                                volume_targets.append(target)
                        
                        if num_slices > 0:
                            avg_vol_loss = volume_loss / num_slices
                            
                            # Compute volume-level dice (like in prediction)
                            if volume_predictions and volume_targets:
                                # Stack all slice predictions and targets
                                stacked_predictions = torch.stack(volume_predictions, dim=0)  # [num_slices, 2, H, W]
                                stacked_targets = torch.stack(volume_targets, dim=0)  # [num_slices, H, W]
                                
                                # Compute volume-level dice using the same method as prediction
                                volume_dice = compute_foreground_dice(stacked_predictions, stacked_targets)
                            else:
                                volume_dice = 0.0
                            
                            self.val_metrics.update(loss=avg_vol_loss, dice=volume_dice)
                            
                            # Update progress bar with current volume metrics
                            avg_metrics = self.val_metrics.get_averages()
                            current_avg_loss = avg_metrics['loss']
                            current_avg_dice = avg_metrics['dice']
                            pbar.set_postfix({
                                'vol_loss': f'{avg_vol_loss:.4f}',
                                'vol_dice': f'{volume_dice:.4f}',
                                'avg_loss': f'{current_avg_loss:.4f}',
                                'avg_dice': f'{current_avg_dice:.4f}'
                            })
                else:
                    # Single BlockDataset (shouldn't happen with current setup, but handle it)
                    slice_data, slice_list, _ = batch.get_one_directory(axis=0)
                    
                    volume_loss, num_slices = 0.0, 0
                    # Accumulate predictions and targets for volume-level dice computation
                    volume_predictions = []
                    volume_targets = []
                    
                    for i, _ in enumerate(slice_list):
                        img_block, label_block = slice_data[i]
                        loss, pred_logits, target = self._process_slice(img_block, label_block, training=False)
                        volume_loss += loss
                        num_slices += 1
                        
                        # Accumulate predictions and targets for volume-level dice
                        if pred_logits is not None and target is not None:
                            volume_predictions.append(pred_logits)
                            volume_targets.append(target)
                    
                    if num_slices > 0:
                        avg_vol_loss = volume_loss / num_slices
                        
                        # Compute volume-level dice (like in prediction)
                        if volume_predictions and volume_targets:
                            # Stack all slice predictions and targets
                            stacked_predictions = torch.stack(volume_predictions, dim=0)  # [num_slices, 2, H, W]
                            stacked_targets = torch.stack(volume_targets, dim=0)  # [num_slices, H, W]
                            
                            # Compute volume-level dice using the same method as prediction
                            volume_dice = compute_foreground_dice(stacked_predictions, stacked_targets)
                        else:
                            volume_dice = 0.0
                        
                        self.val_metrics.update(loss=avg_vol_loss, dice=volume_dice)
                        
                        # Update progress bar with current volume metrics
                        avg_metrics = self.val_metrics.get_averages()
                        current_avg_loss = avg_metrics['loss']
                        current_avg_dice = avg_metrics['dice']
                        pbar.set_postfix({
                            'dice': f'{volume_dice:.4f}',
                        })
        
        avg_metrics = self.val_metrics.get_averages()
        return avg_metrics['loss'], avg_metrics['dice']
    
    def _initialize_model_weights(self):
        """Initialize model weights properly to prevent NaN."""
        self.logger.info("Model: initializing weights...")
        
        for module in self.model.modules():
            if isinstance(module, nn.Conv2d):
                # Xavier/Glorot initialization for conv layers
                if hasattr(module, 'weight') and module.weight is not None:
                    nn.init.xavier_uniform_(module.weight)
                if hasattr(module, 'bias') and module.bias is not None:
                    nn.init.constant_(module.bias, 0)
            elif isinstance(module, nn.ConvTranspose2d):
                # Xavier initialization for transposed conv layers
                if hasattr(module, 'weight') and module.weight is not None:
                    nn.init.xavier_uniform_(module.weight)
                if hasattr(module, 'bias') and module.bias is not None:
                    nn.init.constant_(module.bias, 0)
            elif isinstance(module, nn.InstanceNorm2d):
                # Standard initialization for instance norm
                if hasattr(module, 'weight') and module.weight is not None:
                    nn.init.constant_(module.weight, 1)
                if hasattr(module, 'bias') and module.bias is not None:
                    nn.init.constant_(module.bias, 0)
            elif isinstance(module, nn.Linear):
                # Xavier initialization for linear layers
                if hasattr(module, 'weight') and module.weight is not None:
                    nn.init.xavier_uniform_(module.weight)
                if hasattr(module, 'bias') and module.bias is not None:
                    nn.init.constant_(module.bias, 0)
        
        self.logger.info("Model: weights initialized successfully")
    
    def _setup_continual_learning(self):
        """Setup optimizer and scheduler for continual learning."""
        try:
            checkpoint = torch.load(self.config.pretrained_model_path, map_location=self.device, weights_only=False)
            
            # Load optimizer state to preserve momentum
            if 'optimizer_state_dict' in checkpoint:
                self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
                self.logger.info("Training: loaded optimizer state (preserves momentum)")
                
                # For continual learning, preserve checkpoint LR or use config LR if specified
                if self.config.learning_rate is not None:
                    # User explicitly wants to override the checkpoint learning rate
                    for param_group in self.optimizer.param_groups:
                        old_lr = param_group['lr']
                        param_group['lr'] = self.config.learning_rate
                        self.logger.info(f"Training: LR overridden {old_lr:.2e} -> {param_group['lr']:.2e}")
                else:
                    # Preserve the learning rate from checkpoint
                    current_lr = self.optimizer.param_groups[0]['lr']
                    self.logger.info(f"Training: preserving checkpoint LR {current_lr:.2e}")
            else:
                self.logger.warning("Training: no optimizer state found - using fresh optimizer")
            
            # Load scheduler state if available
            if 'scheduler_state_dict' in checkpoint and hasattr(self, 'scheduler') and self.scheduler:
                try:
                    self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
                    self.logger.info("Training: loaded scheduler state")
                except Exception as e:
                    self.logger.warning(f"Training: failed to load scheduler state - {e}")
                    
        except Exception as e:
            self.logger.warning(f"Training: continual learning setup failed - {e}")
            self.logger.info("Training: falling back to fine-tuning setup")
    
    def _process_slice(self, img_block, label_block, training=True) -> Tuple[float, torch.Tensor, torch.Tensor]:
        """Process a single slice and return loss, predictions, and targets for volume-level dice computation."""
        img_block = img_block.unsqueeze(0).float().to(self.device)
        label_block = label_block.to(self.device)
        
        # Use middle slice as target
        middle_idx = self.config.num_input_slices // 2
        target = label_block[middle_idx, :, :].unsqueeze(0).long()
        
        # Comprehensive input validation
        if torch.isnan(img_block).any() or torch.isinf(img_block).any():
            self.logger.warning("Data: NaN/Inf detected in input image")
            return 0.0, None, None
        
        if torch.isnan(target.float()).any() or torch.isinf(target.float()).any():
            self.logger.warning("Data: NaN/Inf detected in target")
            return 0.0, None, None
        
        # Normalize input to prevent extreme values
        img_min, img_max = img_block.min(), img_block.max()
        if img_max > img_min:
            img_block = (img_block - img_min) / (img_max - img_min)
        
        # Check if target has valid values
        if target.max() == 0 and target.min() == 0:
            # Empty target, return small loss
            return 0.1, None, None
        
        # Validate target labels are within valid range for number of classes
        num_classes = getattr(self.config, 'num_classes', 2)
        if target.max() >= num_classes:
            self.logger.error(f"Data: target contains invalid class labels (max={target.max()}, expected < {num_classes})")
            self.logger.error(f"Data: target unique values: {torch.unique(target)}")
            return 0.0, None, None
        
        if target.min() < 0:
            self.logger.error(f"Data: target contains negative class labels (min={target.min()})")
            self.logger.error(f"Data: target unique values: {torch.unique(target)}")
            return 0.0, None, None
        
        if training:
            self.optimizer.zero_grad()
        
        # Forward pass
        if self.scaler is not None and training:
            with autocast(device_type='cuda'):
                output = self.model(img_block)
                
                # Check for NaN in output
                if torch.isnan(output).any() or torch.isinf(output).any():
                    self.logger.error("Model: NaN/Inf detected in output - indicates model corruption")
                    if training:
                        # Reset model weights if NaN detected during training
                        self.logger.warning("Model: resetting weights due to NaN")
                        self._initialize_model_weights()
                    return 0.0, None, None
                
                loss = self.criterion(output, target)
                
                # Check for NaN in loss
                if torch.isnan(loss) or torch.isinf(loss):
                    self.logger.warning("Training: NaN/Inf detected in loss")
                    return 0.0, None, None
            
            self.scaler.scale(loss).backward()
            
            # Gradient clipping to prevent explosion
            if hasattr(self.config, 'gradient_clip_norm') and self.config.gradient_clip_norm > 0:
                self.scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.gradient_clip_norm)
            
            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            output = self.model(img_block)
            
            # Check for NaN in output
            if torch.isnan(output).any() or torch.isinf(output).any():
                self.logger.error("Model: NaN/Inf detected in output - indicates model corruption")
                if training:
                    # Reset model weights if NaN detected during training
                    self.logger.warning("Model: resetting weights due to NaN")
                    self._initialize_model_weights()
                return 0.0, None, None
            
            loss = self.criterion(output, target)
            
            # Check for NaN in loss
            if torch.isnan(loss) or torch.isinf(loss):
                self.logger.warning("Training: NaN/Inf detected in loss")
                return 0.0, None, None
            
            if training:
                loss.backward()
                
                # Gradient clipping
                if hasattr(self.config, 'gradient_clip_norm') and self.config.gradient_clip_norm > 0:
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.gradient_clip_norm)
                
                self.optimizer.step()
        
        # Return loss, predictions, and targets for volume-level dice computation
        # Don't compute dice here - will be computed at volume level like in prediction
        return loss.item(), output.squeeze(0).detach(), target.squeeze(0).detach()
