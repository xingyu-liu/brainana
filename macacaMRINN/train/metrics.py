"""
Training metrics for macacaMRINN - streamlined and unified metric computation
"""

import torch
import torch.nn.functional as F
import numpy as np
from typing import Dict, Optional, List, Tuple, Union
import logging


def prepare_tensors(pred_logits: torch.Tensor, target_classes: torch.Tensor, 
                   num_classes: int = 2, threshold: float = 0.5) -> Tuple[torch.Tensor, torch.Tensor]:
    """Unified tensor preparation for metric computation.
    
    Args:
        pred_logits: Raw logits from model
        target_classes: Class indices 
        num_classes: Number of classes
        threshold: Probability threshold for binary conversion
        
    Returns:
        Tuple of (binary_pred, target_onehot) with consistent dimensions
    """
    with torch.no_grad():
        # Ensure same device
        if pred_logits.device != target_classes.device:
            target_classes = target_classes.to(pred_logits.device)
        
        # Convert logits to probabilities and then binary
        probs = torch.softmax(pred_logits, dim=1)
        binary_pred = (probs > threshold).float()
        
        # Convert target to one-hot
        if target_classes.dtype != torch.long:
            target_classes = target_classes.long()
        
        # Handle different input dimensions
        if target_classes.dim() == 3:  # (N, H, W) -> (N, C, H, W)
            target_onehot = F.one_hot(target_classes, num_classes=num_classes).permute(0, 3, 1, 2).float()
        elif target_classes.dim() == 4:  # (N, H, W, D) -> (N, C, H, W, D)
            target_onehot = F.one_hot(target_classes, num_classes=num_classes).permute(0, 4, 1, 2, 3).float()
        else:
            raise ValueError(f"Expected 3D or 4D target tensor, got {target_classes.dim()}D")
        
        return binary_pred, target_onehot


def compute_metrics_per_class(pred_logits: torch.Tensor, target_classes: torch.Tensor,
                             metric_type: str = "dice", num_classes: int = 2, 
                             threshold: float = 0.5, 
                             compute_per_slice: bool = False) -> Tuple[List[float], float]:
    """Unified metric computation for both Dice and IoU.
    
    Args:
        pred_logits: Raw logits from model 
        target_classes: Class indices
        metric_type: "dice" or "iou"
        num_classes: Number of classes
        threshold: Probability threshold for binary conversion
        compute_per_slice: If True and input is 3D, compute metrics per 2D slice then average
        
    Returns:
        metric_scores: List of scores for each class
        mean_metric: Average metric across classes
    """
    with torch.no_grad():
        binary_pred, target_onehot = prepare_tensors(pred_logits, target_classes, num_classes, threshold)
        
        if compute_per_slice and binary_pred.dim() == 5:  # 3D volume case
            return _compute_metrics_per_slice(binary_pred, target_onehot, metric_type, num_classes)
        else:
            return _compute_metrics_volume(binary_pred, target_onehot, metric_type, num_classes)


def _compute_single_metric(pred_flat: torch.Tensor, target_flat: torch.Tensor, 
                          metric_type: str, smooth: float = 1e-5) -> float:
    """Compute a single metric (Dice or IoU) for flattened predictions and targets.
    
    Args:
        pred_flat: Flattened binary predictions
        target_flat: Flattened binary targets  
        metric_type: "dice" or "iou"
        smooth: Smoothing factor to avoid division by zero
        
    Returns:
        Computed metric value
    """
    intersection = (pred_flat * target_flat).sum()
    
    if metric_type == "dice":
        union = pred_flat.sum() + target_flat.sum()
        metric = (2.0 * intersection + smooth) / (union + smooth)
    elif metric_type == "iou":
        union = pred_flat.sum() + target_flat.sum() - intersection
        metric = (intersection + smooth) / (union + smooth)
    else:
        raise ValueError(f"Unknown metric type: {metric_type}")
    
    return metric


def _compute_metrics_volume(binary_pred: torch.Tensor, target_onehot: torch.Tensor,
                           metric_type: str, num_classes: int) -> Tuple[List[float], float]:
    """Compute metrics across entire volume."""
    metric_scores = []
    
    for class_idx in range(num_classes):
        # Handle both 2D and 3D cases properly
        if binary_pred.dim() == 4:  # (N, C, H, W)
            pred_class = binary_pred[:, class_idx]
            target_class = target_onehot[:, class_idx]
        elif binary_pred.dim() == 5:  # (N, C, H, W, D)
            pred_class = binary_pred[:, class_idx]
            target_class = target_onehot[:, class_idx]
        else:
            raise ValueError(f"Unexpected tensor dimensions: {binary_pred.dim()}")
        
        # Flatten for computation - use reshape to handle non-contiguous tensors
        pred_flat = pred_class.reshape(-1)
        target_flat = target_class.reshape(-1)
        
        # Use shared metric computation
        metric = _compute_single_metric(pred_flat, target_flat, metric_type)
        metric_scores.append(metric.item())
    
    mean_metric = np.mean(metric_scores)
    return metric_scores, mean_metric


def _compute_metrics_per_slice(binary_pred: torch.Tensor, target_onehot: torch.Tensor,
                              metric_type: str, num_classes: int) -> Tuple[List[float], float]:
    """Compute metrics per 2D slice, then average across slices - for 3D volumes."""
    # binary_pred and target_onehot are (N, C, H, W, D)
    batch_size, num_classes, height, width, depth = binary_pred.shape
    
    all_slice_metrics = []
    
    for slice_idx in range(depth):
        slice_metrics = []
        
        for class_idx in range(num_classes):
            # Extract 2D slice: (N, H, W)
            pred_slice = binary_pred[:, class_idx, :, :, slice_idx]
            target_slice = target_onehot[:, class_idx, :, :, slice_idx]
            
            # Flatten - use reshape to handle non-contiguous tensors
            pred_flat = pred_slice.reshape(-1)
            target_flat = target_slice.reshape(-1)
            
            # Use shared metric computation
            metric = _compute_single_metric(pred_flat, target_flat, metric_type)
            slice_metrics.append(metric.item())
        
        all_slice_metrics.append(slice_metrics)
    
    # Average across slices for each class
    avg_metrics_per_class = []
    for class_idx in range(num_classes):
        class_metrics = [slice_metrics[class_idx] for slice_metrics in all_slice_metrics]
        avg_metrics_per_class.append(np.mean(class_metrics))
    
    mean_metric = np.mean(avg_metrics_per_class)
    return avg_metrics_per_class, mean_metric


def compute_dice(pred_logits: torch.Tensor, target_classes: torch.Tensor,
                num_classes: int = 2, threshold: float = 0.5, 
                compute_per_slice: bool = False) -> Tuple[List[float], float]:
    """Compute Dice coefficient."""
    return compute_metrics_per_class(pred_logits, target_classes, "dice", 
                                   num_classes, threshold, compute_per_slice)


def compute_iou(pred_logits: torch.Tensor, target_classes: torch.Tensor,
               num_classes: int = 2, threshold: float = 0.5,
               compute_per_slice: bool = False) -> Tuple[List[float], float]:
    """Compute IoU (Intersection over Union)."""
    return compute_metrics_per_class(pred_logits, target_classes, "iou", 
                                   num_classes, threshold, compute_per_slice)


def compute_foreground_dice(pred_logits: torch.Tensor, target_classes: torch.Tensor, 
                           threshold: float = 0.5, compute_per_slice: bool = False) -> float:
    """Compute dice coefficient for foreground class only (class 1).
    
    Note: For multi-class segmentation, this returns the dice for class 1.
    For brain segmentation with classes {0: non-brain, 1: CSF, 2: gray, 3: subcortex, 4: white},
    this returns CSF dice. Consider using compute_dice for all class scores.
    """
    num_classes = pred_logits.shape[1] if pred_logits.dim() > 3 else 2
    dice_scores, _ = compute_dice(pred_logits, target_classes, num_classes=num_classes, 
                                threshold=threshold, compute_per_slice=compute_per_slice)
    
    if len(dice_scores) > 1:
        return dice_scores[1]  # Return class 1 dice
    else:
        return dice_scores[0]  # Fallback for single class


def compute_foreground_iou(pred_logits: torch.Tensor, target_classes: torch.Tensor, 
                          threshold: float = 0.5, compute_per_slice: bool = False) -> float:
    """Compute IoU for foreground class only (class 1).
    
    Note: For multi-class segmentation, this returns the IoU for class 1.
    For brain segmentation with classes {0: non-brain, 1: CSF, 2: gray, 3: subcortex, 4: white},
    this returns CSF IoU. Consider using compute_iou for all class scores.
    """
    num_classes = pred_logits.shape[1] if pred_logits.dim() > 3 else 2
    iou_scores, _ = compute_iou(pred_logits, target_classes, num_classes=num_classes, 
                              threshold=threshold, compute_per_slice=compute_per_slice)
    
    if len(iou_scores) > 1:
        return iou_scores[1]  # Return class 1 IoU
    else:
        return iou_scores[0]  # Fallback for single class


def compute_brain_tissue_dice(pred_logits: torch.Tensor, target_classes: torch.Tensor, 
                             threshold: float = 0.5, compute_per_slice: bool = False) -> float:
    """Compute mean dice for brain tissue classes (excluding background).
    
    For 5-class brain segmentation {0: non-brain, 1: CSF, 2: gray, 3: subcortex, 4: white},
    this computes the mean dice for classes 1-4 (all brain tissue types).
    
    Args:
        pred_logits: Model predictions
        target_classes: Ground truth labels
        threshold: Probability threshold
        compute_per_slice: Whether to compute per slice
        
    Returns:
        Mean dice across brain tissue classes (excluding background)
    """
    num_classes = pred_logits.shape[1] if pred_logits.dim() > 3 else 2
    dice_scores, _ = compute_dice(pred_logits, target_classes, num_classes=num_classes, 
                                threshold=threshold, compute_per_slice=compute_per_slice)
    
    if len(dice_scores) > 2:  # Multi-class case
        # Exclude background (class 0), compute mean of brain tissue classes
        brain_tissue_dice = dice_scores[1:]  # Classes 1, 2, 3, 4, etc.
        return np.mean(brain_tissue_dice)
    else:  # Binary case
        return dice_scores[1] if len(dice_scores) > 1 else dice_scores[0]


class MetricsTracker:
    """Unified metrics tracker for training and validation."""
    
    def __init__(self, compute_per_slice: bool = False, logger=None):
        """
        Args:
            compute_per_slice: Whether to compute metrics per slice for 3D data
            logger: Optional logger for detailed metric reporting
        """
        self.compute_per_slice = compute_per_slice
        self.logger = logger
        self.reset()
    
    def reset(self):
        """Reset all metrics."""
        self.losses = []
        self.dice_scores = []
        self.iou_scores = []
    
    def update(self, loss: Optional[float] = None, 
               pred_logits: Optional[torch.Tensor] = None,
               target_classes: Optional[torch.Tensor] = None,
               dice: Optional[float] = None, 
               iou: Optional[float] = None):
        """Update metrics with new values.
        
        Args:
            loss: Loss value to add
            pred_logits: Model predictions for automatic metric computation
            target_classes: Ground truth for automatic metric computation  
            dice: Pre-computed dice score
            iou: Pre-computed IoU score
        """
        if loss is not None:
            self.losses.append(loss)
        
        # Compute metrics automatically if logits and targets provided
        if pred_logits is not None and target_classes is not None:
            if dice is None:
                dice = compute_foreground_dice(pred_logits, target_classes, 
                                             compute_per_slice=self.compute_per_slice)
            if iou is None:
                iou = compute_foreground_iou(pred_logits, target_classes,
                                           compute_per_slice=self.compute_per_slice)
        
        if dice is not None:
            self.dice_scores.append(dice)
        if iou is not None:
            self.iou_scores.append(iou)
    
    def get_averages(self) -> Dict[str, float]:
        """Get average metrics."""
        return {
            'loss': sum(self.losses) / len(self.losses) if self.losses else 0.0,
            'dice': sum(self.dice_scores) / len(self.dice_scores) if self.dice_scores else 0.0,
            'iou': sum(self.iou_scores) / len(self.iou_scores) if self.iou_scores else 0.0
        }
    
    def get_loss(self) -> float:
        """Get average loss."""
        return sum(self.losses) / len(self.losses) if self.losses else 0.0
    
    def get_dice(self) -> float:
        """Get average dice score."""
        return sum(self.dice_scores) / len(self.dice_scores) if self.dice_scores else 0.0
    
    def get_iou(self) -> float:
        """Get average IoU score."""
        return sum(self.iou_scores) / len(self.iou_scores) if self.iou_scores else 0.0
    
    def log_metrics(self, prefix: str = ""):
        """Log current metrics if logger is available."""
        if self.logger:
            averages = self.get_averages()
            for metric_name, value in averages.items():
                self.logger.info(f"{prefix}{metric_name}: {value:.4f}")


def create_metrics_tracker(compute_per_slice: bool = False, logger=None) -> MetricsTracker:
    """Create a metrics tracker.
    
    Args:
        compute_per_slice: Whether to compute metrics per slice for 3D data
        logger: Optional logger instance
    
    Returns:
        MetricsTracker instance
    """
    return MetricsTracker(compute_per_slice=compute_per_slice, logger=logger)
