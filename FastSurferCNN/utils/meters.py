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
from typing import Any
import torch

import matplotlib.pyplot as plt

# IMPORTS
import numpy as np
import yacs.config
import threading
from queue import Queue
import time

from FastSurferCNN.utils import logging
from FastSurferCNN.utils.metrics import DiceScore
from FastSurferCNN.utils.misc import plot_confusion_matrix

logger = logging.getLogger(__name__)


class AsyncDiceTracker:
    """
    Background dice computation tracker to avoid blocking training.
    """
    
    def __init__(self, dice_score_obj, update_interval=0.5, meter=None):
        self.dice_score = dice_score_obj
        self.meter = meter  # Reference to the meter for background exclusion
        self.update_interval = update_interval
        self.latest_dice = 0.0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.compute_thread = None
        self.last_compute_time = 0
        
    def start(self):
        """Start background computation thread."""
        if self.compute_thread is None or not self.compute_thread.is_alive():
            self.stop_event.clear()
            self.compute_thread = threading.Thread(target=self._background_worker, daemon=True)
            self.compute_thread.start()
    
    def stop(self):
        """Stop background computation thread."""
        self.stop_event.set()
        if self.compute_thread and self.compute_thread.is_alive():
            self.compute_thread.join(timeout=1.0)
    
    def _background_worker(self):
        """Background worker that computes dice scores."""
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                if current_time - self.last_compute_time >= self.update_interval:
                    # Use the meter's method to exclude background
                    if self.meter and hasattr(self.meter, 'get_dice_without_background'):
                        dice_score = self.meter.get_dice_without_background()
                    else:
                        dice_score, _ = self.dice_score.compute()
                    dice_value = dice_score.item() if hasattr(dice_score, 'item') else dice_score
                    
                    with self.lock:
                        self.latest_dice = dice_value
                        self.last_compute_time = current_time
                
                time.sleep(0.1)  # Small sleep to prevent busy waiting
            except Exception:
                time.sleep(0.5)
    
    def get_latest_dice(self):
        """Get the latest computed dice score (non-blocking)."""
        with self.lock:
            return self.latest_dice


class Meter:
    """
    Meter class to keep track of the losses and scores during training and validation.
    """

    def __init__(
        self,
        cfg: yacs.config.CfgNode,
        mode: str,
        global_step: int,
        total_iter: int | None = None,
        total_epoch: int | None = None,
        class_names: Any | None = None,
        device: Any | None = None,
        writer: Any | None = None,
    ):
        """
        Construct a Meter object.

        Parameters
        ----------
        cfg
            Configuration Node.
        mode
            Meter mode (Train or Val).
        global_step
            Global step.
        total_iter
            Total iterations (Default value = None).
        total_epoch
            Total epochs (Default value = None).
        class_names
            Class names (Default value = None).
        device
            Device (Default value = None).
        writer
            Writer (Default value = None).

        """
        self._cfg = cfg
        self.mode = mode.capitalize()
        self.confusion_mat = False
        self.class_names = class_names
        if self.class_names is None:
            self.class_names = [f"{c+1}" for c in range(cfg.MODEL.NUM_CLASSES)]

        # Initialize dice score with background exclusion
        # Exclude class 0 (background) from dice calculation for more meaningful metrics
        self.dice_score = DiceScore(cfg.MODEL.NUM_CLASSES, device=device)
        self.batch_losses = []
        self.writer = writer
        self.global_iter = global_step
        self.total_iter_num = total_iter
        self.total_epochs = total_epoch
        
        # Background dice tracker for non-blocking progress updates
        self.async_dice_tracker = AsyncDiceTracker(self.dice_score, update_interval=0.5, meter=self)
    
    def get_dice_without_background(self):
        """Get dice score excluding background (class 0)."""
        dice_score, dice_matrix = self.dice_score.compute(per_class=True)
        
        # Exclude background (class 0) from the calculation
        if len(dice_score) > 1:
            # Only consider classes 1 and above (exclude background)
            region_dice = dice_score[1:]
            # Only average over classes that have non-zero union
            valid_regions = region_dice[region_dice > 0]
            if len(valid_regions) > 0:
                return valid_regions.mean()
            else:
                return torch.tensor(0.0, device=dice_score.device)
        else:
            return dice_score[0] if len(dice_score) > 0 else torch.tensor(0.0)

    def reset(self):
        """
        Reset bach losses and dice scores.
        """
        self.batch_losses = []
        self.dice_score.reset()
    
    def start_background_tracking(self):
        """Start background dice computation."""
        self.async_dice_tracker.start()
    
    def stop_background_tracking(self):
        """Stop background dice computation."""
        self.async_dice_tracker.stop()
    
    def get_latest_dice(self):
        """Get the latest dice score from background computation."""
        return self.async_dice_tracker.get_latest_dice()

    def enable_confusion_mat(self):
        """
        Enable confusion matrix.
        """
        self.confusion_mat = True

    def disable_confusion_mat(self):
        """
        Disable confusion matrix.
        """
        self.confusion_mat = False

    def update_stats(self, pred, labels, batch_loss):
        """
        Update the statistics.
        """
        self.dice_score.update((pred, labels))
        self.batch_losses.append(batch_loss.item())

    def write_summary(self, loss_total, lr=None, loss_ce=None, loss_dice=None):
        """
        Write a summary of the losses and scores.

        Parameters
        ----------
        loss_total : torch.Tensor
            Total loss.
        lr : default = None
             Learning rate (Default value = None).
        loss_ce : default = None
            Cross entropy loss (Default value = None).
        loss_dice : default = None
            Dice loss (Default value = None).
        """
        self.writer.add_scalar(
            f"{self.mode}/total_loss", loss_total.item(), self.global_iter
        )
        if self.mode == "Train":
            self.writer.add_scalar("Train/lr", lr[0], self.global_iter)
            if loss_ce:
                self.writer.add_scalar(
                    "Train/ce_loss", loss_ce.item(), self.global_iter
                )
            if loss_dice:
                self.writer.add_scalar(
                    "Train/dice_loss", loss_dice.item(), self.global_iter
                )

        self.global_iter += 1

    def log_iter(self, cur_iter: int, cur_epoch: int):
        """
        Log the current iteration.

        Parameters
        ----------
        cur_iter : int
            Current iteration.
        cur_epoch : int
            Current epoch.
        """
        if (cur_iter + 1) % self._cfg.TRAIN.LOG_INTERVAL == 0:
            logger.info(
                f"Training: {self.mode.lower()} epoch={cur_epoch}/{self.total_epochs}, "
                f"iter={cur_iter + 1}/{self.total_iter_num}, "
                f"loss={np.array(self.batch_losses).mean():.4f}"
            )

    def log_epoch(self, cur_epoch: int):
        """
        Log the current epoch.

        Parameters
        ----------
        cur_epoch : int
            Current epoch.
        """
        dice_score, dice_cm_mat = self.dice_score.compute()
        self.writer.add_scalar(f"{self.mode}/mean_dice_score", dice_score, cur_epoch)
        if self.confusion_mat:
            fig = plot_confusion_matrix(dice_cm_mat, self.class_names)
            self.writer.add_figure(f"{self.mode}/confusion_mat", fig, cur_epoch)
            plt.close("all")
