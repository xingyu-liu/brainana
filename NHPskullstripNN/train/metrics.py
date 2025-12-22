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


class DiceScore:
    """
    Accumulating dice coefficient by tracking union and intersection across batches.
    This matches FastSurferCNN's approach: accumulates statistics and computes dice
    at epoch end (ratio of sums) rather than averaging per-batch dice scores (mean of ratios).
    
    This approach properly weights by batch size and matches standard evaluation practices.
    """
    
    def __init__(
        self,
        num_classes: int,
        device: Optional[torch.device] = None,
        use_argmax: bool = True,
        threshold: float = 0.5,
    ):
        """
        Args:
            num_classes: Number of classes
            device: Device to store tensors on
            use_argmax: If True, use argmax (categorical). If False, use threshold-based binary predictions.
            threshold: Probability threshold for binary conversion (only used if use_argmax=False)
        """
        self.num_classes = num_classes
        self.device = device
        self.use_argmax = use_argmax
        self.threshold = threshold
        
        # Initialize accumulation matrices
        if device is not None:
            self.union = torch.zeros(num_classes, num_classes, device=device, dtype=torch.float32)
            self.intersection = torch.zeros(num_classes, num_classes, device=device, dtype=torch.float32)
        else:
            self.union = torch.zeros(num_classes, num_classes, dtype=torch.float32)
            self.intersection = torch.zeros(num_classes, num_classes, dtype=torch.float32)
    
    def reset(self):
        """Reset accumulated statistics."""
        if self.device is not None:
            self.union = torch.zeros(self.num_classes, self.num_classes, device=self.device, dtype=torch.float32)
            self.intersection = torch.zeros(self.num_classes, self.num_classes, device=self.device, dtype=torch.float32)
        else:
            self.union = torch.zeros(self.num_classes, self.num_classes, dtype=torch.float32)
            self.intersection = torch.zeros(self.num_classes, self.num_classes, dtype=torch.float32)
    
    def _convert_predictions(self, pred_logits: torch.Tensor) -> torch.Tensor:
        """Convert logits to class predictions (argmax or threshold-based)."""
        if self.use_argmax:
            # Use argmax: matches FastSurferCNN and standard inference
            return pred_logits.data.max(1)[1]  # [N, H, W] class indices
        else:
            # Use threshold-based: convert to binary predictions
            probs = torch.softmax(pred_logits, dim=1)
            # Get class with highest probability after thresholding
            binary_pred = (probs > self.threshold).float()
            # Convert to class indices: use argmax of probabilities
            return probs.argmax(dim=1)
    
    def update(self, pred_logits: torch.Tensor, target_classes: torch.Tensor):
        """
        Update accumulated intersection and union matrices.
        
        Args:
            pred_logits: Model predictions [N, C, H, W] or [N, C, H, W, D]
            target_classes: Ground truth class indices [N, H, W] or [N, H, W, D]
        """
        with torch.no_grad():
            # Ensure same device
            if pred_logits.device != target_classes.device:
                target_classes = target_classes.to(pred_logits.device)
            
            # Move accumulation matrices to same device as inputs
            if self.union.device != pred_logits.device:
                self.union = self.union.to(pred_logits.device)
                self.intersection = self.intersection.to(pred_logits.device)
                self.device = pred_logits.device
            
            # Convert predictions to class indices
            pred_classes = self._convert_predictions(pred_logits)  # [N, H, W] or [N, H, W, D]
            
            # Ensure target is long type
            if target_classes.dtype != torch.long:
                target_classes = target_classes.long()
            
            # Flatten spatial dimensions
            batch_size = pred_classes.shape[0]
            pred_flat = pred_classes.view(batch_size, -1)  # [N, H*W] or [N, H*W*D]
            target_flat = target_classes.view(batch_size, -1)  # [N, H*W] or [N, H*W*D]
            
            # Create one-hot encodings for all classes
            num_spatial = pred_flat.shape[1]
            pred_onehot = torch.zeros(batch_size, num_spatial, self.num_classes, 
                                     device=pred_logits.device, dtype=torch.float32)
            gt_onehot = torch.zeros(batch_size, num_spatial, self.num_classes,
                                   device=pred_logits.device, dtype=torch.float32)
            
            for class_idx in range(self.num_classes):
                pred_onehot[:, :, class_idx] = (pred_flat == class_idx).float()
                gt_onehot[:, :, class_idx] = (target_flat == class_idx).float()
            
            # Vectorized computation using einsum for efficiency
            # Intersection: sum over batch and spatial dims for each class pair
            intersection = torch.einsum('bsc,bst->ct', gt_onehot, pred_onehot)
            
            # Union: sum of gt + sum of pred for each class pair
            gt_sums = torch.sum(gt_onehot, dim=(0, 1))  # [num_classes]
            pred_sums = torch.sum(pred_onehot, dim=(0, 1))  # [num_classes]
            union = gt_sums.unsqueeze(1) + pred_sums.unsqueeze(0)  # Broadcasting to [num_classes, num_classes]
            
            # Update accumulated values
            self.intersection += intersection
            self.union += union
    
    def compute(self, per_class: bool = False, exclude_background: bool = False):
        """
        Compute dice score from accumulated statistics.
        
        Args:
            per_class: If True, return per-class dice scores. If False, return mean dice.
            exclude_background: If True, exclude background class (class 0) from mean calculation.
        
        Returns:
            If per_class=False: mean dice score (float or tensor)
            If per_class=True: (dice_per_class, dice_matrix) tuple
        """
        # Compute dice confusion matrix
        dice_union = self.union
        dice_intersection = self.intersection
        
        # Avoid division by zero: set dice to 0 where union is 0
        dice_cm_mat = torch.where(
            dice_union > 0,
            2 * dice_intersection / dice_union,
            torch.tensor(0.0, device=dice_union.device)
        )
        
        # Get per-class dice scores (diagonal of confusion matrix)
        dice_score_per_class = dice_cm_mat.diagonal()
        
        # Determine which classes to include in mean
        if exclude_background and self.num_classes > 1:
            # Exclude background (class 0), only consider classes with non-zero union
            region_dice = dice_score_per_class[1:]  # Exclude class 0
            valid_classes = dice_union.diagonal()[1:] > 0  # Exclude class 0
        else:
            # Include all classes with non-zero union
            region_dice = dice_score_per_class
            valid_classes = dice_union.diagonal() > 0
        
        # Compute mean over valid classes
        if valid_classes.any():
            dice_score = region_dice[valid_classes].mean()
        else:
            dice_score = torch.tensor(0.0, device=dice_union.device)
        
        if per_class:
            return dice_score_per_class, dice_cm_mat
        else:
            # Return as float if on CPU, tensor if on GPU (for compatibility)
            if dice_score.device.type == 'cpu':
                return dice_score.item()
            return dice_score


class MetricsTracker:
    """
    Unified metrics tracker for training and validation.
    
    Now uses FastSurferCNN's accumulated approach: accumulates intersection/union
    matrices across batches and computes dice at epoch end (ratio of sums).
    This properly weights by batch size and matches standard evaluation practices.
    """
    
    def __init__(self, compute_per_slice: bool = False, logger=None, 
                 num_classes: int = 2, device: Optional[torch.device] = None,
                 use_argmax: bool = True, threshold: float = 0.5):
        """
        Args:
            compute_per_slice: Whether to compute metrics per slice for 3D data (legacy, kept for compatibility)
            logger: Optional logger for detailed metric reporting
            num_classes: Number of classes for dice computation
            device: Device to store tensors on
            use_argmax: If True, use argmax (categorical). If False, use threshold-based.
            threshold: Probability threshold for binary conversion (only used if use_argmax=False)
        """
        self.compute_per_slice = compute_per_slice
        self.logger = logger
        self.num_classes = num_classes
        self.use_argmax = use_argmax
        self.threshold = threshold
        
        # Initialize DiceScore for accumulated computation (FastSurferCNN approach)
        self.dice_score = DiceScore(
            num_classes=num_classes,
            device=device,
            use_argmax=use_argmax,
            threshold=threshold
        )
        
        # Keep legacy lists for backward compatibility and loss tracking
        self.losses = []
        self.iou_scores = []  # Keep for backward compatibility
    
    def reset(self):
        """Reset all metrics."""
        self.losses = []
        self.iou_scores = []
        self.dice_score.reset()
    
    def update(self, loss: Optional[float] = None, 
               pred_logits: Optional[torch.Tensor] = None,
               target_classes: Optional[torch.Tensor] = None,
               dice: Optional[float] = None, 
               iou: Optional[float] = None):
        """
        Update metrics with new values.
        
        Args:
            loss: Loss value to add
            pred_logits: Model predictions for automatic metric computation (preferred)
            target_classes: Ground truth for automatic metric computation (preferred)
            dice: Pre-computed dice score (legacy, not recommended - use pred_logits/target_classes instead)
            iou: Pre-computed IoU score (legacy)
        
        Note: For accumulated dice computation (FastSurferCNN approach), pass pred_logits and target_classes.
        The dice will be computed at epoch end from accumulated statistics.
        """
        if loss is not None:
            self.losses.append(loss)
        
        # Update accumulated dice score (FastSurferCNN approach)
        if pred_logits is not None and target_classes is not None:
            self.dice_score.update(pred_logits, target_classes)
        
        # Legacy: compute IoU if needed (still uses per-batch computation)
        if pred_logits is not None and target_classes is not None and iou is None:
            iou = compute_foreground_iou(pred_logits, target_classes,
                                       compute_per_slice=self.compute_per_slice)
        
        if iou is not None:
            self.iou_scores.append(iou)
    
    def get_averages(self) -> Dict[str, float]:
        """Get average metrics."""
        # Compute dice from accumulated statistics (FastSurferCNN approach)
        dice = self.get_dice()
        
        return {
            'loss': sum(self.losses) / len(self.losses) if self.losses else 0.0,
            'dice': dice,
            'iou': sum(self.iou_scores) / len(self.iou_scores) if self.iou_scores else 0.0
        }
    
    def get_loss(self) -> float:
        """Get average loss."""
        return sum(self.losses) / len(self.losses) if self.losses else 0.0
    
    def get_dice(self) -> float:
        """
        Get dice score from accumulated statistics (FastSurferCNN approach).
        
        Returns:
            Mean dice score computed from accumulated intersection/union matrices.
            This uses ratio of sums, properly weighting by batch size.
        """
        dice = self.dice_score.compute(per_class=False, exclude_background=True)
        # Convert to float if tensor
        if isinstance(dice, torch.Tensor):
            return dice.item()
        return float(dice)
    
    def get_dice_per_class(self) -> Tuple[List[float], torch.Tensor]:
        """
        Get per-class dice scores and confusion matrix.
        
        Returns:
            Tuple of (dice_per_class list, dice_confusion_matrix tensor)
        """
        dice_per_class, dice_matrix = self.dice_score.compute(per_class=True, exclude_background=False)
        # Convert to list of floats
        if isinstance(dice_per_class, torch.Tensor):
            dice_list = dice_per_class.cpu().numpy().tolist()
        else:
            dice_list = dice_per_class
        return dice_list, dice_matrix
    
    def get_iou(self) -> float:
        """Get average IoU score (legacy per-batch computation)."""
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
