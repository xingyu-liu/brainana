# Copyright 2019 Image Analysis Lab, German Center for Neurodegenerative Diseases (DZNE), Bonn
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

# IMPORTS
import csv
import pprint
import time

import numpy as np
import torch
import torch.optim.lr_scheduler as scheduler
import yacs.config
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

from FastSurferCNN.atlas.atlas_manager import get_atlas_manager
from FastSurferCNN.data_loader import loader
from FastSurferCNN.models.losses import get_loss_func
from FastSurferCNN.models.networks import build_model
from FastSurferCNN.models.optimizer import get_optimizer
from FastSurferCNN.utils import checkpoint as cp
from FastSurferCNN.utils import logging
from FastSurferCNN.utils.lr_scheduler import get_lr_scheduler
from FastSurferCNN.utils.meters import Meter
from FastSurferCNN.utils.metrics import iou_score, precision_recall
from FastSurferCNN.utils.misc import plot_predictions, update_num_steps
from FastSurferCNN.utils.gpu_utils import get_device

logger = logging.getLogger(__name__)


class Trainer:
    """
    Trainer for the networks.

    Methods
    -------
    __init__
        Construct object.
    train
        Trains the network.
    eval
        Validates calculations.
    run
        Performs training loop.
    """

    def __init__(self, cfg: yacs.config.CfgNode):
        """
        Construct Trainer object.

        Parameters
        ----------
        cfg : yacs.config.CfgNode
            Node of configs to be used.
        """
        # Set random seed from configs.
        np.random.seed(cfg.RNG_SEED)
        torch.manual_seed(cfg.RNG_SEED)
        self.cfg = cfg

        # Create the checkpoint dir (flat structure, no EXPR_NUM subdirectory).
        self.checkpoint_dir = os.path.join(cfg.LOG_DIR, "checkpoints")
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        
        # Setup logging (flat structure)
        os.makedirs(os.path.join(cfg.LOG_DIR, "logs"), exist_ok=True)
        logging.setup_logging(os.path.join(cfg.LOG_DIR, "logs", "training.log"))
        
        # Setup CSV metrics logging
        self.metrics_csv_path = os.path.join(cfg.LOG_DIR, "training_metrics.csv")
        self.metrics_file = None
        self.csv_writer = None
        logger.info("Training with config:")
        logger.info(pprint.pformat(cfg))
        
        # Automatic GPU selection (finds least busy GPU)
        self.device = get_device()
        logger.info(f"Using device: {self.device}")
        self.model = build_model(cfg)
        self.loss_func = get_loss_func(cfg)

        # Set up logger format
        self.num_classes = cfg.MODEL.NUM_CLASSES
        
        # Binary brain mask mode - no atlas needed
        if self.num_classes == 2:
            logger.info("Binary segmentation mode (NUM_CLASSES=2) - brain mask task")
            self.class_names = ["background", "brain"]
            atlas_manager = None  # No atlas needed
        else:
            # Multi-class mode - set up class names using AtlasManager
            # Determine atlas name: if CLASS_OPTIONS[0] is an atlas name (ARM2, ARM3), use it
            # Otherwise default to ARM2 for backward compatibility
            potential_atlas = cfg.DATA.CLASS_OPTIONS[0] if cfg.DATA.CLASS_OPTIONS else 'ARM2'
            atlas_name = potential_atlas if potential_atlas.upper() in ['ARM2', 'ARM3', 'FREESURFER'] else 'ARM2'
            
            # Get class names from AtlasManager
            atlas_manager = get_atlas_manager(atlas_name)
            class_dict = atlas_manager.get_class_dict()
            
            # Extract class names based on plane and options
            plane_key = "sagittal" if cfg.DATA.PLANE == "sagittal" else "not_sagittal"
            self.class_names = []
            for opt in cfg.DATA.CLASS_OPTIONS:
                if opt.upper() in ['ARM2', 'ARM3', 'FREESURFER']:
                    # If option is an atlas name, use the combined view
                    self.class_names.extend(class_dict[plane_key].get(opt, []))
                else:
                    # Otherwise it's a class type (aseg, aparc)
                    self.class_names.extend(class_dict[plane_key].get(opt, []))
        
        # Create format string with same number of placeholders as class names
        self.a = "{}\t" * (len(self.class_names) - 1) + "{}"
        self.plot_dir = os.path.join(cfg.LOG_DIR, "plots")
        os.makedirs(self.plot_dir, exist_ok=True)

        self.subepoch = False if self.cfg.TRAIN.BATCH_SIZE == 16 else True
    
    def _init_csv_logging(self):
        """Initialize CSV file for logging training metrics."""
        self.metrics_file = open(self.metrics_csv_path, 'w', newline='')
        self.csv_writer = csv.writer(self.metrics_file)
        self.csv_writer.writerow(['loss', 'dice', 'val_loss', 'val_dice'])
        self.metrics_file.flush()
        logger.info(f"CSV metrics will be logged to: {self.metrics_csv_path}")
    
    def _log_metrics_to_csv(self, train_loss, train_dice, val_loss, val_dice):
        """Log metrics to CSV file."""
        if self.csv_writer is not None:
            self.csv_writer.writerow([train_loss, train_dice, val_loss, val_dice])
            self.metrics_file.flush()
    
    def _close_csv_logging(self):
        """Close CSV file."""
        if self.metrics_file is not None:
            self.metrics_file.close()

    def train(
        self,
        train_loader: loader.DataLoader,
        optimizer: torch.optim.Optimizer,
        scheduler: None | scheduler.StepLR | scheduler.CosineAnnealingWarmRestarts,
        train_meter: Meter,
        epoch,
    ) -> None:
        """
        Train the network to the given training data.

        Parameters
        ----------
        train_loader : loader.DataLoader
            Data loader for the training.
        optimizer : torch.optim.Optimizer
            Optimizer for the training.
        scheduler : None, scheduler.StepLR, scheduler.CosineAnnealingWarmRestarts
            LR scheduler for the training.
        train_meter : Meter
            Meter to keep track of the training stats.
        epoch : int
            Current epoch.

        """
        self.model.train()
        logger.info("Training started ")
        epoch_start = time.time()
        loss_batch = np.zeros(1)

        # Start background dice tracking
        train_meter.start_background_tracking()
        
        # Create progress bar with custom description
        pbar = tqdm(enumerate(train_loader), total=len(train_loader), 
                   desc=f"Epoch {epoch}/{self.cfg.TRAIN.NUM_EPOCHS}")
        
        for curr_iter, batch in pbar:
            images, labels, weights, scale_factors = (
                batch["image"].to(self.device),
                batch["label"].to(self.device),
                batch["weight"].float().to(self.device),
                batch["scale_factor"],
            )

            if not self.subepoch or (curr_iter) % (16 / self.cfg.TRAIN.BATCH_SIZE) == 0:
                optimizer.zero_grad()  # every second epoch to get batchsize of 16 if using 8

            pred = self.model(images, scale_factors)
            loss_total, loss_dice, loss_ce = self.loss_func(pred, labels, weights)

            train_meter.update_stats(pred, labels, loss_total)
            train_meter.log_iter(curr_iter, epoch)
            if scheduler is not None:
                # Use get_last_lr() instead of deprecated get_lr()
                # get_last_lr() returns a list of learning rates (one per parameter group)
                current_lr = scheduler.get_last_lr()
                train_meter.write_summary(
                    loss_total, current_lr, loss_ce, loss_dice
                )
            else:
                train_meter.write_summary(
                    loss_total, [self.cfg.OPTIMIZER.BASE_LR], loss_ce, loss_dice
                )

            loss_total.backward()
            if (
                not self.subepoch
                or (curr_iter + 1) % (16 / self.cfg.TRAIN.BATCH_SIZE) == 0
            ):
                optimizer.step()  # every second epoch to get batchsize of 16 if using 8
                if scheduler is not None:
                    scheduler.step(epoch + curr_iter / len(train_loader))

            loss_batch += loss_total.item()
            
            # Update progress bar with current metrics (non-blocking background computation)
            if curr_iter % 5 == 0:  # Update more frequently since it's non-blocking
                current_dice = train_meter.get_latest_dice()
                pbar.set_postfix({'Dice': f'{current_dice:.4f}'})

            # Plot sample predictions
            if curr_iter == len(train_loader) - 2:
                plt_title = "Training Results Epoch " + str(epoch)

                file_save_name = os.path.join(
                    self.plot_dir, "Epoch_" + str(epoch) + "_Training_Predictions.pdf"
                )

                _, batch_output = torch.max(pred, dim=1)
                
                plot_predictions(
                    images, labels, batch_output, plt_title, file_save_name
                )

        # Stop background tracking
        train_meter.stop_background_tracking()
        
        train_meter.log_epoch(epoch)
        
        # Get training metrics for CSV logging
        train_loss = np.array(train_meter.batch_losses).mean()
        train_dice, _ = train_meter.dice_score.compute()
        train_dice = train_dice.item() if hasattr(train_dice, 'item') else train_dice
        
        logger.info(
            f"Training epoch {epoch} finished in {time.time() - epoch_start:.04f} seconds"
        )
        
        # Store training metrics for CSV (will be logged after validation)
        self._current_train_loss = train_loss
        self._current_train_dice = train_dice

    @torch.no_grad()
    def eval(
        self, val_loader: loader.DataLoader, val_meter: Meter, epoch: int
    ) -> np.ndarray:
        """
        Evaluate model and calculates stats.

        Parameters
        ----------
        val_loader : loader.DataLoader
            Value loader.
        val_meter : Meter
            Meter for the values.
        epoch : int
            Epoch to evaluate.

        Returns
        -------
        int, float, ndarray
            median miou [value].
        """
        logger.info(f"Evaluating model at epoch {epoch}")
        self.model.eval()

        # Aggregate statistics across all batches (not per scale factor)
        ints_ = np.zeros(self.num_classes - 1)
        unis_ = np.zeros(self.num_classes - 1)
        per_cls_counts_gt = np.zeros(self.num_classes - 1)
        per_cls_counts_pred = np.zeros(self.num_classes - 1)
        accs = np.zeros(self.num_classes - 1)  # -1 to exclude background (still included in val loss)

        val_start = time.time()
        # Start background dice tracking for validation
        val_meter.start_background_tracking()
        
        # Create progress bar with custom description for validation
        pbar = tqdm(enumerate(val_loader), total=len(val_loader), 
                   desc=f"Val Epoch {epoch}")
        
        for curr_iter, batch in pbar:
            images, labels, weights, scale_factors = (
                batch["image"].to(self.device),
                batch["label"].to(self.device),
                batch["weight"].float().to(self.device),
                batch["scale_factor"],
            )

            pred = self.model(images, scale_factors)
            loss_total, loss_dice, loss_ce = self.loss_func(pred, labels, weights)

            # Get predictions for metrics and plotting
            _, batch_output = torch.max(pred, dim=1)

            # Calculate iou_scores, accuracy and dice confusion matrix + sum over previous batches
            int_, uni_ = iou_score(batch_output, labels, self.num_classes)
            ints_ += int_
            unis_ += uni_

            tpos, pcc_gt, pcc_pred = precision_recall(
                batch_output, labels, self.num_classes
            )
            accs += tpos
            per_cls_counts_gt += pcc_gt
            per_cls_counts_pred += pcc_pred

            # Plot sample predictions
            if curr_iter == (len(val_loader) // 2):
                plt_title = "Validation Results Epoch " + str(epoch)

                file_save_name = os.path.join(
                    self.plot_dir,
                    "Epoch_" + str(epoch) + "_Validations_Predictions.pdf",
                )

                plot_predictions(
                    images, labels, batch_output, plt_title, file_save_name
                )

            val_meter.update_stats(pred, labels, loss_total)
            val_meter.write_summary(loss_total)
            val_meter.log_iter(curr_iter, epoch)
            
            # Update progress bar with current metrics (non-blocking background computation)
            if curr_iter % 5 == 0:  # Update more frequently since it's non-blocking
                current_dice = val_meter.get_latest_dice()
                pbar.set_postfix({'Dice': f'{current_dice:.4f}'})

        # Stop background tracking
        val_meter.stop_background_tracking()
        
        val_meter.log_epoch(epoch)
        
        # Get validation metrics for CSV logging
        val_loss = np.array(val_meter.batch_losses).mean()
        val_dice, dice_matrix = val_meter.dice_score.compute()
        val_dice = val_dice.item() if hasattr(val_dice, 'item') else val_dice
        self._current_val_loss = val_loss
        self._current_val_dice = val_dice
        
        logger.info(
            f"Validation epoch {epoch} finished in {time.time() - val_start:.04f} seconds"
        )

        # Compute overall metrics
        ious = ints_ / (unis_ + 1e-8)  # Add small epsilon to avoid division by zero
        miou = np.mean(ious)
        mean_recall = np.mean(accs / (per_cls_counts_gt + 1e-8))
        mean_precision = np.mean(accs / (per_cls_counts_pred + 1e-8))

        # Log overall statistics
        logger.info(
            f"[Epoch {epoch} stats]: Dice: {val_dice:.4f}; "
            f"MIoU: {miou:.4f}; "
            f"Mean Recall: {mean_recall:.4f}; "
            f"Mean Precision: {mean_precision:.4f}; "
            f"Avg loss total: {val_loss:.4f}"
        )

        return miou

    def run(self):
        """
        Transfer the model to devices, create a tensor board summary writer and then perform the training loop.
        """
        if self.cfg.NUM_GPUS > 1:
            assert (
                self.cfg.NUM_GPUS <= torch.cuda.device_count()
            ), "Cannot use more GPU devices than available"
            print("Using ", self.cfg.NUM_GPUS, "GPUs!")
            self.model = torch.nn.DataParallel(self.model)

        val_loader = loader.get_dataloader(self.cfg, "val")
        train_loader = loader.get_dataloader(self.cfg, "train")

        update_num_steps(train_loader, self.cfg)

        # Transfer the model to device(s)
        self.model = self.model.to(self.device)

        optimizer = get_optimizer(self.model, self.cfg)
        scheduler = get_lr_scheduler(optimizer, self.cfg)

        # Load pretrained model for transfer learning if specified
        if self.cfg.TRAIN.PRETRAINED_MODEL and self.cfg.TRAIN.FINE_TUNE:
            try:
                logger.info(f"Loading pretrained model from {self.cfg.TRAIN.PRETRAINED_MODEL}")
                
                # Check actual number of classes in the pretrained checkpoint
                from FastSurferCNN.utils.checkpoint import read_checkpoint_file
                checkpoint = read_checkpoint_file(self.cfg.TRAIN.PRETRAINED_MODEL, map_location="cpu")
                
                # Find classifier weight to determine number of classes in checkpoint
                classifier_key = None
                for key in checkpoint["model_state"].keys():
                    if "classifier" in key and "weight" in key and "conv" in key:
                        classifier_key = key
                        break
                
                if classifier_key:
                    pretrained_num_classes = checkpoint["model_state"][classifier_key].shape[0]
                    drop_classifier = (self.cfg.MODEL.NUM_CLASSES != pretrained_num_classes)
                    
                    if drop_classifier:
                        logger.info(f"Pretrained model has {pretrained_num_classes} classes, target has {self.cfg.MODEL.NUM_CLASSES}")
                        logger.info("Classifier layer will be reinitialized (transfer learning)")
                    else:
                        logger.info(f"Pretrained model has {pretrained_num_classes} classes, matching target {self.cfg.MODEL.NUM_CLASSES}")
                        logger.info("Keeping classifier layer from pretrained model")
                else:
                    logger.warning("Could not determine number of classes in pretrained model, dropping classifier")
                    drop_classifier = True
                
                # Now load the checkpoint (re-loads it, but ensures correct drop_classifier logic)
                checkpoint_epoch, best_metric = cp.restore_model_state_from_checkpoint(
                    self.cfg.TRAIN.PRETRAINED_MODEL,
                    self.model,
                    optimizer=None,  # Don't load optimizer for transfer learning
                    scheduler=None,  # Don't load scheduler for transfer learning
                    fine_tune=True,
                    drop_classifier=drop_classifier,
                )
                logger.info("Successfully loaded pretrained model for transfer learning")
                start_epoch = 0
                best_dice = 0
                best_val_loss = float('inf')
            except Exception as e:
                logger.warning(f"Failed to load pretrained model: {e}")
                logger.info("Training from scratch instead")
                start_epoch = 0
                best_dice = 0
                best_val_loss = float('inf')
        # Resume training from checkpoint
        elif self.cfg.TRAIN.RESUME:
            checkpoint_paths = cp.get_checkpoint_path(
                self.cfg.LOG_DIR, self.cfg.TRAIN.RESUME_EXPR_NUM
            )
            if checkpoint_paths:
                try:
                    checkpoint_path = checkpoint_paths.pop()
                    checkpoint_epoch, best_metric = cp.restore_model_state_from_checkpoint(
                        checkpoint_path,
                        self.model,
                        optimizer,
                        scheduler,
                        self.cfg.TRAIN.FINE_TUNE,
                    )
                    start_epoch = checkpoint_epoch
                    best_dice = best_metric
                    best_val_loss = float('inf')  # Reset when resuming
                    logger.info(f"Resume training from epoch {start_epoch}")
                except Exception as e:
                    print(
                        f"No model to restore. Resuming training from Epoch 0. {e}"
                    )
                    start_epoch = 0
                    best_dice = 0
                    best_val_loss = float('inf')
            else:
                logger.info("No checkpoint found. Training from scratch")
                start_epoch = 0
                best_dice = 0
                best_val_loss = float('inf')
        else:
            logger.info("Training from scratch")
            start_epoch = 0
            best_dice = 0
            best_val_loss = float('inf')

        logger.info(
            f"{sum(x.numel() for x in self.model.parameters())} parameters in total"
        )

        # Create tensorboard summary writer

        writer = SummaryWriter(self.cfg.SUMMARY_PATH, flush_secs=15)

        train_meter = Meter(
            self.cfg,
            mode="train",
            global_step=start_epoch * len(train_loader),
            total_iter=len(train_loader),
            total_epoch=self.cfg.TRAIN.NUM_EPOCHS,
            device=self.device,
            writer=writer,
        )

        val_meter = Meter(
            self.cfg,
            mode="val",
            global_step=start_epoch,
            total_iter=len(val_loader),
            total_epoch=self.cfg.TRAIN.NUM_EPOCHS,
            device=self.device,
            writer=writer,
        )

        logger.info(f"Summary path {self.cfg.SUMMARY_PATH}")
        
        # Initialize CSV logging
        self._init_csv_logging()
        
        # Perform the training loop.
        logger.info(f"Start epoch: {start_epoch + 1}")

        for epoch in range(start_epoch + 1, self.cfg.TRAIN.NUM_EPOCHS + 1):
            self.train(train_loader, optimizer, scheduler, train_meter, epoch=epoch)

            if epoch % 10 == 0:
                val_meter.enable_confusion_mat()
                miou = self.eval(val_loader, val_meter, epoch=epoch)
                val_meter.disable_confusion_mat()

            else:
                miou = self.eval(val_loader, val_meter, epoch=epoch)
            
            # Log metrics to CSV after each epoch
            self._log_metrics_to_csv(
                self._current_train_loss,
                self._current_train_dice,
                self._current_val_loss,
                self._current_val_dice
            )

            if (epoch + 1) % self.cfg.TRAIN.CHECKPOINT_PERIOD == 0:
                logger.info(f"Saving checkpoint at epoch {epoch+1}")
                cp.save_checkpoint(
                    self.checkpoint_dir,
                    epoch + 1,
                    best_dice,
                    self.cfg.NUM_GPUS,
                    self.cfg,
                    self.model,
                    optimizer,
                    scheduler,
                )

            # Handle NaN dice (can happen early in training when many classes aren't predicted yet)
            # Treat NaN as 0 for comparison purposes
            current_dice = 0.0 if np.isnan(self._current_val_dice) else self._current_val_dice
            current_val_loss = self._current_val_loss
            
            # Determine if this is the best model
            # Priority 1: If Dice is improving and valid (not 0), use Dice
            # Priority 2: If both current and best Dice are 0 (i.e., both NaN), use validation loss
            save_best = False
            if current_dice > 0 and current_dice > best_dice:
                # Dice is improving - this is the primary criterion
                best_dice = current_dice
                best_val_loss = current_val_loss
                save_best = True
                logger.info(
                    f"New best checkpoint reached at epoch {epoch+1} with dice of {best_dice:.4f}\nSaving new best model."
                )
            elif current_dice == 0 and best_dice == 0 and current_val_loss < best_val_loss:
                # Dice is not yet useful (still NaN), use validation loss instead
                best_val_loss = current_val_loss
                save_best = True
                logger.info(
                    f"New best checkpoint reached at epoch {epoch+1} with validation loss of {best_val_loss:.4f} (Dice still NaN)\nSaving new best model."
                )
            
            if save_best:
                # Save only the best model file (overwrites previous best)
                cp.save_best_checkpoint(
                    self.checkpoint_dir,
                    epoch + 1,
                    best_dice,
                    self.cfg.NUM_GPUS,
                    self.cfg,
                    self.model,
                    optimizer,
                    scheduler,
                )
        
        # Close CSV logging when training completes
        self._close_csv_logging()
        logger.info("Training completed. CSV metrics saved to: {}".format(self.metrics_csv_path))
