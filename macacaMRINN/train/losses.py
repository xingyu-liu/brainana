"""
Loss functions for training
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceLoss(nn.Module):
    """Dice loss for multi-class segmentation (supports binary and multi-class)."""
    
    def __init__(self, smooth=1e-5):
        super(DiceLoss, self).__init__()
        self.smooth = smooth
    
    def forward(self, pred, target):
        """
        Args:
            pred: Predictions (N, C, H, W) - logits
            target: Ground truth (N, H, W) - class indices
        """
        # Validate target values before processing
        target_min, target_max = target.min().item(), target.max().item()
        num_classes = pred.shape[1]
        
        if target_max >= num_classes:
            raise ValueError(f"Target contains invalid class labels: max={target_max}, expected < {num_classes}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        if target_min < 0:
            raise ValueError(f"Target contains negative class labels: min={target_min}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        # Apply softmax to get probabilities
        pred = torch.softmax(pred, dim=1)
        
        # Convert target to one-hot encoding
        target_one_hot = F.one_hot(target, num_classes=num_classes).permute(0, 3, 1, 2).float()
        
        # Calculate dice for each class
        dice_scores = []
        for i in range(num_classes):
            pred_i = pred[:, i, :, :]
            target_i = target_one_hot[:, i, :, :]
            
            intersection = (pred_i * target_i).sum()
            union = pred_i.sum() + target_i.sum()
            
            dice = (2.0 * intersection + self.smooth) / (union + self.smooth)
            dice_scores.append(dice)
        
        # Return 1 - average dice (loss should be minimized)
        return 1.0 - torch.stack(dice_scores).mean()


class CombinedLoss(nn.Module):
    """Combined Dice and Cross-Entropy loss."""
    
    def __init__(self, dice_weight=0.5, ce_weight=0.5, smooth=1e-5):
        super(CombinedLoss, self).__init__()
        self.dice_weight = dice_weight
        self.ce_weight = ce_weight
        self.dice_loss = DiceLoss(smooth=smooth)
        self.ce_loss = nn.CrossEntropyLoss()
    
    def forward(self, pred, target):
        # Validate target values before processing
        target_min, target_max = target.min().item(), target.max().item()
        num_classes = pred.shape[1]
        
        if target_max >= num_classes:
            raise ValueError(f"Target contains invalid class labels: max={target_max}, expected < {num_classes}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        if target_min < 0:
            raise ValueError(f"Target contains negative class labels: min={target_min}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        dice = self.dice_loss(pred, target)
        ce = self.ce_loss(pred, target)
        return self.dice_weight * dice + self.ce_weight * ce


class FocalLoss(nn.Module):
    """Focal loss for addressing class imbalance."""
    
    def __init__(self, alpha=0.25, gamma=2.0, reduction='mean'):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction
    
    def forward(self, pred, target):
        """
        Args:
            pred: Predictions (N, C, H, W) - logits
            target: Ground truth (N, H, W) - class indices
        """
        # Validate target values before processing
        target_min, target_max = target.min().item(), target.max().item()
        num_classes = pred.shape[1]
        
        if target_max >= num_classes:
            raise ValueError(f"Target contains invalid class labels: max={target_max}, expected < {num_classes}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        if target_min < 0:
            raise ValueError(f"Target contains negative class labels: min={target_min}. "
                           f"Target unique values: {torch.unique(target).tolist()}")
        
        ce_loss = F.cross_entropy(pred, target, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * ce_loss
        
        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        else:
            return focal_loss
