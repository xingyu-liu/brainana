#!/usr/bin/env python3
"""
Test script to verify pretrained model performance on validation set.
This helps diagnose if the issue is with data preprocessing or model loading.
"""

import argparse
import sys
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).parent.parent))

from NHPskullstripNN.config import TrainingConfig
from NHPskullstripNN.model import ModelLoader
from NHPskullstripNN.train.train_utils import prepare_data_loaders
from NHPskullstripNN.train.metrics import MetricsTracker


def test_pretrained_model(config_path: str):
    """Test pretrained model on validation set."""
    # Load config
    config = TrainingConfig.from_yaml(config_path)
    
    print(f"\n{'='*60}")
    print(f"Testing Pretrained Model on Validation Set")
    print(f"{'='*60}\n")
    
    # Load pretrained model
    if not config.pretrained_model_path or not Path(config.pretrained_model_path).exists():
        print(f"❌ Pretrained model not found: {config.pretrained_model_path}")
        return
    
    print(f"📦 Loading pretrained model: {config.pretrained_model_path}")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    if device.type == 'cuda':
        device_id = 0
    else:
        device_id = -1
    
    model = ModelLoader.load_model_from_file(
        model_path=config.pretrained_model_path,
        device_id=device_id,
        config=config,
        logger=None
    )
    
    model.eval()
    print(f"✓ Model loaded on {device}")
    
    # Prepare data loaders
    print(f"\n📊 Preparing data loaders...")
    train_loader, val_loader, test_loader, _ = prepare_data_loaders(config, logger=None)
    
    if val_loader is None:
        print("❌ No validation loader available")
        return
    
    print(f"✓ Validation loader ready ({len(val_loader)} batches)")
    
    # Initialize metrics
    val_metrics = MetricsTracker(
        num_classes=config.num_classes,
        device=device,
        metric_names=['dice', 'iou']
    )
    val_metrics.reset()
    
    # Run validation
    print(f"\n🔍 Running validation...")
    num_samples = 0
    
    with torch.no_grad():
        for batch_idx, batch in enumerate(val_loader):
            if isinstance(batch, dict) and 'image' in batch and 'label' in batch:
                images = batch['image'].to(device)  # [B, num_slices, H, W]
                labels = batch['label'].to(device)  # [B, H, W]
                
                for b in range(images.shape[0]):
                    img_block = images[b].unsqueeze(0).float()  # [1, num_slices, H, W]
                    label_block = labels[b]  # [H, W]
                    
                    # Check data range
                    img_min, img_max = img_block.min().item(), img_block.max().item()
                    if batch_idx == 0 and b == 0:
                        print(f"  Sample image range: [{img_min:.6f}, {img_max:.6f}]")
                        if img_min < -0.1 or img_max > 1.1:
                            print(f"  ⚠️  WARNING: Image values outside expected [0, 1] range!")
                    
                    # Forward pass
                    output = model(img_block)  # [1, num_classes, H, W]
                    
                    # Prepare target
                    target = label_block.unsqueeze(0).long()  # [1, H, W]
                    
                    # Update metrics
                    val_metrics.update(
                        loss=0.0,  # Not computing loss, just metrics
                        pred_logits=output,
                        target_classes=target
                    )
                    num_samples += 1
            
            if (batch_idx + 1) % 10 == 0:
                current_dice = val_metrics.get_dice()
                print(f"  Processed {batch_idx + 1} batches, current dice: {current_dice:.4f}")
    
    # Get final metrics
    avg_metrics = val_metrics.get_averages()
    dice_score = avg_metrics['dice']
    iou_score = avg_metrics.get('iou', 0.0)
    
    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Validation Dice: {dice_score:.4f}")
    print(f"  Validation IoU:  {iou_score:.4f}")
    print(f"  Samples tested: {num_samples}")
    print(f"{'='*60}\n")
    
    if dice_score < 0.8:
        print("⚠️  WARNING: Dice score is lower than expected (< 0.8)")
        print("   This suggests a data preprocessing mismatch.")
        print("   Check:")
        print("   1. Data normalization (should be per-volume, range [0, 1])")
        print("   2. Data format (should match pretrained model expectations)")
        print("   3. Label format (should be class indices, not one-hot)")
    elif dice_score >= 0.9:
        print("✓ Dice score looks good! Pretrained model is working correctly.")
    else:
        print("ℹ️  Dice score is reasonable but could be better.")
        print("   This might be due to dataset differences.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test pretrained model on validation set")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    args = parser.parse_args()
    
    test_pretrained_model(args.config)

